"""Run reviewed upstream modules in an isolated process, no shell or email send."""
import importlib.util
import json
import math
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
VENDOR = BASE / "vendor/agents"


def emit(agent, status, step):
    print(json.dumps({"kind": "status", "agent": agent, "status": status, "step": step}, ensure_ascii=False), flush=True)


def package(name, directory):
    spec = importlib.util.spec_from_file_location(name, directory / "src/__init__.py", submodule_search_locations=[str(directory / "src")])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def convert_for_secretary(records, raw_exceptions, models):
    """Explicit contract adapter, never invent a missing amount or confidence."""
    index = {r.get("source_ref"): r for r in records if r.get("source_ref")}
    warnings, docs, events, mapping = [], [], [], []
    for i, rec in enumerate(records):
        number = rec.get("invoice_number") or rec.get("receipt_number") or rec.get("po_number")
        dt = rec.get("invoice_date") or rec.get("receipt_date") or rec.get("po_date")
        amount = rec.get("amount") if rec.get("document_type") == "receipt" else rec.get("grand_total")
        conf = rec.get("confidence", {})
        confidence = min(conf.values()) if isinstance(conf, dict) and conf else None
        if any(v is None or v == "" for v in (number, dt, amount, confidence, rec.get("vendor_name"))):
            warnings.append(f"Secretary document skipped: required value missing for {rec.get('source_ref', i)}")
            continue
        try:
            docs.append(models.DocumentInfo(doc_id=f"DOC-{i+1:04d}", file_name=Path(rec.get("source_ref", "")).name,
                doc_type=rec.get("document_type", "unknown"), vendor_name=rec["vendor_name"], invoice_number=number,
                invoice_date=dt, grand_total=amount, currency=rec.get("currency", "MYR"),
                line_items=rec.get("line_items") or [], confidence=confidence, quality_flags=rec.get("flags") or []))
        except ValueError as e:
            warnings.append(f"Secretary document rejected: {rec.get('source_ref', i)}: {e}")
    for exc in raw_exceptions:
        rec = index.get(exc.get("source_ref"))
        if rec is None:
            warnings.append(f"Unmapped exception retained for manual review: {exc.get('exception_id')}")
            continue
        amount = rec.get("amount") if rec.get("document_type") == "receipt" else rec.get("grand_total")
        number = exc.get("document_number") or rec.get("invoice_number") or rec.get("receipt_number") or rec.get("po_number")
        if amount is None or not number or not rec.get("vendor_name"):
            warnings.append(f"Exception missing Secretary required fields: {exc.get('exception_id')}")
            continue
        kind = exc.get("type")
        event_type = "overdue" if kind == "overdue" else "duplicate" if kind in {"duplicate", "duplicate_similar_confidence"} else "escalation" if exc.get("severity") == "critical" else "flagged"
        kwargs = dict(event_type=event_type, invoice_number=number, vendor_name=rec["vendor_name"], amount=amount,
            currency=rec.get("currency", "MYR"), invoice_date=rec.get("invoice_date") or rec.get("receipt_date") or rec.get("po_date"),
            due_date=rec.get("due_date"), details=f"[{kind}] {exc.get('reason', '')}")
        if event_type == "duplicate":
            matched_ref = (exc.get("details") or {}).get("matched_with")
            matched_record = index.get(matched_ref, {})
            matched_number = matched_record.get("invoice_number") or matched_record.get("receipt_number") or matched_record.get("po_number")
            kwargs["duplicate_of"] = matched_number
            if matched_number is None:
                warnings.append(f"Duplicate match reference has no document number: {exc.get('exception_id')}")
        if event_type == "flagged":
            kwargs["flag_reason"] = exc.get("reason", "")
            kwargs["confidence"] = (exc.get("details") or {}).get("confidence_score")
        if event_type == "escalation":
            kwargs["escalation_code"] = kind
            kwargs["escalation_reason"] = exc.get("reason", "")
        try:
            events.append(models.ExceptionEvent(**kwargs))
            mapping.append({"exception_id": exc.get("exception_id"), "original_type": kind, "mapped_event_type": event_type, "source_ref": exc.get("source_ref")})
        except ValueError as e:
            warnings.append(f"Exception rejected by Secretary: {exc.get('exception_id')}: {e}")
    return docs, events, warnings, mapping


def validate_records(records):
    if not isinstance(records, list) or not 1 <= len(records) <= 100:
        raise ValueError("records must be a list of 1..100 pre-extracted records")
    seen_refs = set()
    for rec in records:
        if not isinstance(rec, dict) or rec.get("document_type") not in {"invoice", "receipt", "order", "po"}:
            raise ValueError("Each record must have a supported document_type")
        if rec.get("currency") != "MYR":
            raise ValueError("This upstream Financial demo only supports MYR. No currency conversion is performed.")
        amount = rec.get("amount") if rec.get("document_type") == "receipt" else rec.get("grand_total")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
            raise ValueError("Printed amount/grand_total is required and must be nonnegative; no invented totals")
        if not isinstance(rec.get("source_ref"), str) or not rec["source_ref"]:
            raise ValueError("source_ref is required for traceability")
        if rec["source_ref"] in seen_refs:
            raise ValueError("source_ref must be unique; split multiple records into distinct traceable references")
        seen_refs.add(rec["source_ref"])
        if not isinstance(rec.get("confidence"), dict) or not rec["confidence"]:
            raise ValueError("Per-field confidence map required; no invented confidence")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in rec["confidence"].values()):
            raise ValueError("Confidence must be a finite number between 0 and 1")


def run(request, output_dir):
    package("office_logistics", VENDOR / "logistics")
    package("office_secretary", VENDOR / "secretary")
    from office_logistics.pipeline import LogisticsPipeline
    from office_secretary.secretary import Secretary
    from office_secretary import models
    spec = importlib.util.spec_from_file_location("office_financial", VENDOR / "financial/engine.py")
    financial = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(financial)
    secretary = Secretary()
    emit("Secretary", "working", "生成执行计划（调用仓库 Planner）")
    plan = secretary.planner.generate_plan(request["goal"])
    emit("Secretary", "idle", "计划已生成，等待核对结果")
    emit("Logistics", "working", "校验已抽取的测试记录；本轮不执行 OCR")
    if request["mode"] == "fixture":
        fixture = read_json(VENDOR / "financial/test/mock_records.json")
        source_records = fixture["records"]
        period = fixture["period"]
    else:
        source_records = request["records"]
        period = request["period"]
    validate_records(source_records)
    pipeline = LogisticsPipeline(str(VENDOR / "logistics/schemas"))
    documents = []
    for rec in source_records:
        number = rec.get("invoice_number") or rec.get("receipt_number") or rec.get("po_number", "")
        # Header hints are derived from record metadata, not represented as real OCR.
        content = " ".join((rec["document_type"], rec.get("vendor_name", ""), number))
        documents.append({"content": content, "source_ref": rec["source_ref"], "extracted": rec, "filename": Path(rec["source_ref"]).name})
    raw = pipeline.process_batch(documents)
    records = json.loads(pipeline.format_output(raw))
    emit("Logistics", "done", f"完成 {len(records)} 条结构化记录校验")
    emit("Financial", "working", "运行原核对引擎：算术、税率、重复项与匹配")
    ledger, exceptions = financial.FinancialEngine({"period": period, "records": records}).run()
    emit("Financial", "done", f"生成 {len(ledger['rows'])} 行测试账本、{len(exceptions['exceptions'])} 个异常")
    emit("Secretary", "working", "转换异常字段，生成待办和邮件草稿（不发送）")
    docs, events, warnings, mapping = convert_for_secretary(records, exceptions["exceptions"], models)
    secretary_result = secretary.run(goal=request["goal"], documents=docs, exceptions=events, auto_approve_emails=False).model_dump(mode="json")
    # Preserve two incompatible reporting conventions instead of merging numbers.
    result = {"data_mode": request["mode"], "period": period, "goal": request["goal"], "records": records,
        "logistics_summary": pipeline.get_summary(raw), "ledger": ledger, "exceptions": exceptions,
        "secretary": secretary_result, "initial_plan": plan.model_dump(mode="json"), "exception_mapping": mapping,
        "warnings": warnings + [
            "仅验证代码接通：fixture为仓库样例，records为外部预抽取字段；未实现图片/PDF/OCR。",
            f"原Financial固定检查日期为 {financial.TODAY}；period标签不代表已按月过滤数据。",
            "Financial与Secretary现金流定义不同，结果分别保留；界面不合并为正式财务结论。",
            "邮件仅为草稿，无自动审批、无发送接口；任务完成不代表账务正确或异常已解决。"],
        "counts": {"records": len(records), "ledger_rows": len(ledger["rows"]), "exceptions": len(exceptions["exceptions"]),
                   "tasks": len(secretary_result["tasks"]), "email_drafts": len(secretary_result["chase_emails"])}}
    for name, payload in (("records.json", records), ("ledger.json", ledger), ("exceptions.json", exceptions), ("secretary.json", secretary_result), ("result.json", result)):
        (output_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    emit("Secretary", "done", f"生成 {len(secretary_result['tasks'])} 个待办；邮件草稿待人工检查")
    print(json.dumps({"kind": "result", "counts": result["counts"], "warnings": result["warnings"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    run(read_json(sys.argv[1]), Path(sys.argv[2]))

"""Checks for the orchestrator's LLM-record self-check. Run: python -m pytest agents/test_orchestrator.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents.orchestrator import build_chase_emails, chase_targets, normalize_extracted, report_from_ledger, split_systemic, verify_extraction


def test_verify_extraction_reports_field_mismatches():
    reference = [
        {"source_ref": "a.png", "document_type": "invoice", "vendor_name": "Kedai A", "invoice_number": "INV-1",
         "invoice_date": "2026-09-01", "grand_total": 100.0},
        {"source_ref": "b.png", "document_type": "order", "vendor_name": "B", "po_number": "PO-1", "po_date": None, "grand_total": 5.0},
    ]
    live = [
        {"source_ref": "a.png", "document_type": "invoice", "vendor_name": "kedai a ", "invoice_number": "INV-1",
         "invoice_date": "2026-09-01", "grand_total": 109.0},
        {"source_ref": "b.png", "document_type": "po", "vendor_name": "B", "po_number": "PO-1", "po_date": None, "grand_total": 5.0},
        {"source_ref": "unknown.png", "document_type": "invoice"},
    ]
    v = verify_extraction(live, reference)
    assert v["documents_compared"] == 2 and v["fields_checked"] == 10 and v["fields_matched"] == 9
    assert v["mismatches"] == [{"source_ref": "a.png", "field": "grand_total", "expected": 100.0, "extracted": 109.0}]


def test_chase_emails_one_per_vendor_document_with_template_fallback():
    exceptions = [
        {"type": "conflicting_printed_values", "document_type": "invoice", "document_number": "INV-1", "vendor_name": "A", "reason": "two totals"},
        {"type": "arithmetic_mismatch", "document_type": "invoice", "document_number": "INV-1", "vendor_name": "A", "reason": "sum off"},
        {"type": "arithmetic_mismatch", "document_type": "po", "document_number": "PO-1", "reason": "our own PO"},
        {"type": "no_due_date", "document_type": "invoice", "document_number": "INV-2", "reason": "no due date"},
        {"type": "conflicting_printed_values", "document_type": "receipt", "document_number": "RCT-1", "vendor_name": "B", "reason": "two SST"},
    ]
    targets = chase_targets(exceptions)
    assert [t["document_number"] for t in targets] == ["INV-1", "RCT-1"]
    assert targets[0]["problems"] == ["two totals", "sum off"]
    emails = build_chase_emails(targets, [{"related_invoice": "INV-1", "subject": "Hi", "body": "LLM text"}, {"related_invoice": "X"}])
    assert [(e["related_invoice"], e["source"]) for e in emails] == [("INV-1", "llm"), ("RCT-1", "template")]
    assert "two SST" in emails[1]["body"] and all(e["status"] == "draft" for e in emails)


def test_report_figures_come_from_ledger_not_llm():
    ledger = {"summary": {"total_in": 0.0, "total_out": 100.0, "total_tax": 10.0, "net_cash_flow": -110.0,
                          "by_category": [{"category": "MISC", "total_amount": 100.0, "row_count": 2}]}}
    report = report_from_ledger({"cash_out": 999.0, "top_3_actions": ["a"]}, ledger, [1, 2], [1, 2], [1])
    assert (report["cash_in"], report["cash_out"], report["net_cash"]) == (0.0, 110.0, -110.0)
    assert report["cash_in"] - report["cash_out"] == report["net_cash"]
    assert report["top_3_actions"] == ["a"] and report["tasks_generated"] == 2 and report["chase_emails_drafted"] == 1


def test_normalize_coerces_llm_formats():
    rec = normalize_extracted({
        "tax_rate": "10%", "grand_total": "RM 1,200.50", "invoice_date": "07 Oct 2026",
        "due_date": None, "line_items": [{"quantity": "30", "unit_price": 10.0}],
        "confidence": {"vendor_name": "0.9"}, "flags": "total_mismatch", "status": "clean",
    })
    assert rec["tax_rate"] == 10.0 and rec["grand_total"] == 1200.5
    assert rec["invoice_date"] == "2026-10-07" and rec["due_date"] is None
    assert rec["line_items"][0]["quantity"] == 30.0
    assert rec["confidence"] == {"vendor_name": 0.9}
    assert rec["flags"] == ["total_mismatch"] and rec["status"] == "clean"


def test_normalize_flags_instead_of_guessing():
    rec = normalize_extracted({"grand_total": "illegible", "invoice_date": "sometime", "status": "clean"})
    assert rec["grand_total"] is None and rec["invoice_date"] is None
    assert "unparseable_field" in rec["flags"] and rec["status"] == "flagged"
    assert "grand_total" in rec["notes"] and "invoice_date" in rec["notes"]


def test_systemic_exceptions_collapse_to_one_observation():
    many = [{"type": "no_due_date", "document_number": f"INV-{i}", "source_ref": f"{i}.png"} for i in range(6)]
    few = [{"type": "missing_po_match", "document_number": f"INV-{i}", "source_ref": f"{i}.png"} for i in range(2)]
    dup = [{"type": "duplicate_similar_confidence", "document_number": "INV-0", "source_ref": "0.png"}]
    actionable, obs = split_systemic(many + few + dup)
    assert [e["type"] for e in actionable] == ["missing_po_match"] * 2 + ["duplicate_similar_confidence"]  # below threshold: kept
    assert [(o["type"], o["count"]) for o in obs] == [("no_due_date", 6)] and obs[0]["text"].startswith("6 invoices")
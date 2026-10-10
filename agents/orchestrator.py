#!/usr/bin/env python
"""
Banjir Productivity — LLM Orchestration Layer
=============================================

Chains 2 LLM agents + 1 Python engine into a single pipeline:

    1. Secretary LLM  — reads goal, writes execution plan
    2. Logistics LLM   — reads document images, returns structured JSON
    3. Financial Python — validates arithmetic, SST, duplicates (deterministic)
    4. Secretary LLM   — converts exceptions to tasks, chase emails, final report

When no LLM endpoint is configured (or a call fails), it falls back to
the Python pipeline (run_pipeline.py logic) so the system always works.

Usage (standalone):
    python agents/orchestrator.py --goal "Close out September"
    python agents/orchestrator.py --goal "Close out September" --json

Usage (as library):
    from agents.orchestrator import PipelineOrchestrator
    orch = PipelineOrchestrator()
    result = orch.run(goal="Close out September")
    print(result["final_report_text"])

LLM Configuration (environment variables):
    LLM_API_URL   — OpenAI-compatible base URL (default: http://localhost:11434/v1 for Ollama)
    LLM_API_KEY   — API key (optional for local models)
    LLM_MODEL     — Model name (default: gpt-4o-mini)
    LLM_VISION_MODEL — Model for vision/extraction (default: same as LLM_MODEL)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = PROJECT_ROOT / "agents"
LOGISTICS_DIR = AGENTS_DIR / "logistics"
FINANCIAL_DIR = AGENTS_DIR / "financial"
SECRETARY_DIR = AGENTS_DIR / "secretary"

PYTHON = sys.executable

# Add Secretary to path for imports
sys.path.insert(0, str(AGENTS_DIR))
sys.path.insert(0, str(SECRETARY_DIR))

# ---------------------------------------------------------------------------
# LLM Configuration
# ---------------------------------------------------------------------------

LLM_API_URL = os.environ.get("LLM_API_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
LLM_VISION_MODEL = os.environ.get("LLM_VISION_MODEL", LLM_MODEL)

# Timeout for LLM calls (seconds)
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "120"))

# Test document images directory (optional — if missing, use pre-extracted JSON)
TEST_DOCS_DIR = PROJECT_ROOT / "test-documents"


class PipelineOrchestrator:
    """Orchestrates the 3-agent pipeline with optional LLM calls.

    Architecture:
        User goal
            |
            v
        [Secretary LLM]  -> Plan
            |
            v
        [Logistics LLM]  -> Structured records (JSON array)
            |
            v
        [Financial Python]  -> Ledger + Exceptions (deterministic)
            |
            v
        [Secretary LLM]  -> Tasks, Chase Emails, Final Report
            |
            v
        Frontend (plan panel + agent panels)

    Fallback: if any LLM call fails or no LLM is configured, the
    corresponding Python module handles that step deterministically.
    """

    def __init__(self):
        self.logistics_prompt = self._read_prompt(
            LOGISTICS_DIR / "prompts" / "system_prompt.md"
        )
        self.secretary_prompt = self._read_prompt(
            SECRETARY_DIR / "schemas" / "prompts" / "system_prompt.md"
        )
        self.extraction_template = self._read_prompt(
            LOGISTICS_DIR / "prompts" / "extraction_template.md"
        )
        self.llm_enabled = bool(LLM_API_URL)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _read_prompt(path: Path) -> str:
        """Read a system prompt file, return empty string if missing."""
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    @staticmethod
    def _llm_available() -> bool:
        """Check if an LLM endpoint is configured and reachable."""
        if not LLM_API_URL:
            return False
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{LLM_API_URL}/models",
                headers={"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {},
            )
            urllib.request.urlopen(req, timeout=3)
            return True
        except Exception:
            return False

    def call_llm(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.3,
        json_mode: bool = False,
    ) -> str:
        """Call an OpenAI-compatible chat completions endpoint.

        Args:
            messages: List of message dicts [{"role": "system", "content": "..."}, ...]
            model: Model name (defaults to LLM_MODEL)
            temperature: Sampling temperature
            json_mode: If True, request JSON response format

        Returns:
            The assistant's response text.
        """
        model = model or LLM_MODEL
        url = f"{LLM_API_URL}/chat/completions"

        headers = {"Content-Type": "application/json"}
        if LLM_API_KEY:
            headers["Authorization"] = f"Bearer {LLM_API_KEY}"

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        import urllib.request
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        resp = urllib.request.urlopen(req, timeout=LLM_TIMEOUT)
        result = json.loads(resp.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"]

    # ------------------------------------------------------------------
    # Step 1: Secretary LLM — Generate Plan
    # ------------------------------------------------------------------

    def secretary_plan_llm(self, goal: str) -> dict:
        """Secretary LLM reads the goal and writes an execution plan.

        Returns a dict with:
            - plan: list of phases [{phase, agent, action, status}]
            - goal: str
            - source: "llm" or "python_fallback"
        """
        if not self._llm_available():
            return self._secretary_plan_python(goal)

        system_prompt = self.secretary_prompt or self._fallback_secretary_prompt()
        user_prompt = (
            f"Business goal: {goal}\n\n"
            "Write a 3-phase execution plan for the month-end closing pipeline.\n"
            "Phase 1: Logistics (extract documents)\n"
            "Phase 2: Financial (validate, reconcile)\n"
            "Phase 3: Secretary (tasks, chase emails, final report)\n\n"
            "Return a JSON object with this structure:\n"
            '{"goal": "<goal>", "phases": [{"phase": 1, "agent": "Logistics", '
            '"action": "<what it does>", "status": "pending"}, ...]}\n'
            "Return ONLY the JSON, no explanation."
        )

        try:
            response = self.call_llm(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                json_mode=True,
                temperature=0.2,
            )
            plan_data = json.loads(response)
            plan_data["source"] = "llm"
            return plan_data
        except Exception as e:
            print(f"  [Orchestrator] Secretary plan LLM failed: {e}")
            return self._secretary_plan_python(goal)

    def _secretary_plan_python(self, goal: str) -> dict:
        """Fallback: use Secretary Python Planner to generate the plan."""
        try:
            from src.planner import Planner
            planner = Planner()
            plan = planner.generate_plan(goal)
            return {
                "goal": plan.goal,
                "phases": [
                    {"phase": p.phase, "agent": p.agent, "action": p.action, "status": p.status.value}
                    for p in plan.phases
                ],
                "source": "python_fallback",
            }
        except Exception as e:
            print(f"  [Orchestrator] Python planner also failed: {e}")
            return {
                "goal": goal,
                "phases": [
                    {"phase": 1, "agent": "Logistics", "action": "Extract all documents", "status": "pending"},
                    {"phase": 2, "agent": "Financial", "action": "Validate and reconcile", "status": "pending"},
                    {"phase": 3, "agent": "Secretary", "action": "Generate tasks and final report", "status": "pending"},
                ],
                "source": "static_fallback",
            }

    @staticmethod
    def _fallback_secretary_prompt() -> str:
        return (
            "You are the Secretary agent in a 3-agent month-end closing pipeline "
            "for a Malaysian micro-business. Read the goal, write a plan, dispatch "
            "to Logistics and Financial agents, then convert exceptions to tasks "
            "and generate a final report."
        )

    # ------------------------------------------------------------------
    # Step 2: Logistics LLM — Extract Documents
    # ------------------------------------------------------------------

    def logistics_extract_llm(self, document_images: list[Path] | None = None) -> list[dict]:
        """Logistics LLM reads document images and returns structured JSON records.

        Args:
            document_images: List of image file paths (PNG/JPG) to process.
                If None, falls back to pre-extracted output.json.

        Returns:
            List of structured document records.
        """
        # If no images or no LLM, use pre-extracted data
        if not self._llm_available() or not document_images:
            return self._logistics_python()

        system_prompt = self.logistics_prompt or self._fallback_logistics_prompt()
        extraction_template = self.extraction_template or ""

        all_records = []

        for img_path in document_images:
            try:
                # Read image as base64
                with open(img_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode("utf-8")

                # Determine MIME type
                ext = img_path.suffix.lower()
                mime = "image/png" if ext == ".png" else "image/jpeg"

                user_prompt = (
                    f"Extract this document into a structured record.\n"
                    f"Document source: {img_path.name}\n\n"
                    f"{extraction_template}\n\n"
                    "Rules:\n"
                    "1. Record fields exactly as printed. NEVER compute or verify any total.\n"
                    "2. Assign a confidence score (0.0-1.0) to each critical field.\n"
                    "3. If a field is unparseable, set it to null and add a flag.\n"
                    "4. If the document is bad (blurry, handwritten), do not guess. Flag it.\n"
                    "5. Malaysian SST rates: 0%, 6%, 8%.\n"
                    "6. Return a single JSON object. No explanation.\n"
                    "Output fields: document_type, vendor_name, invoice_number, "
                    "invoice_date, due_date, po_reference, line_items, subtotal, "
                    "total_tax, grand_total, tax_rate, currency, source_ref, "
                    "confidence, status, flags."
                )

                response = self.call_llm(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": [
                            {"type": "text", "text": user_prompt},
                            {"type": "image_url", "image_url": {
                                "url": f"data:{mime};base64,{img_b64}"
                            }},
                        ]},
                    ],
                    model=LLM_VISION_MODEL,
                    temperature=0.1,
                    json_mode=True,
                )

                record = json.loads(response)
                record.setdefault("source_ref", img_path.name)
                all_records.append(record)

            except Exception as e:
                print(f"  [Orchestrator] Failed to extract {img_path.name}: {e}")
                # Flag as error
                all_records.append({
                    "document_type": "unknown",
                    "source_ref": img_path.name,
                    "status": "error",
                    "flags": ["extraction_failed"],
                    "confidence": {},
                })

        # If all extractions failed, fall back
        if not all_records:
            print("  [Orchestrator] All LLM extractions failed, using Python fallback")
            return self._logistics_python()

        return all_records

    def _logistics_python(self) -> list[dict]:
        """Fallback: use pre-extracted output.json from process_test_docs.py."""
        output_file = LOGISTICS_DIR / "output.json"
        if output_file.exists():
            with open(output_file, "r", encoding="utf-8") as f:
                return json.load(f)

        # Last resort: run the logistics pipeline
        script = LOGISTICS_DIR / "process_test_docs.py"
        if script.exists():
            print("  [Orchestrator] Running Logistics pipeline...")
            result = subprocess.run(
                [PYTHON, str(script)],
                cwd=str(LOGISTICS_DIR),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0 and output_file.exists():
                with open(output_file, "r", encoding="utf-8") as f:
                    return json.load(f)

        return []

    @staticmethod
    def _fallback_logistics_prompt() -> str:
        return (
            "You are the Logistics Coordinator agent. Extract structured records "
            "from Malaysian invoices, receipts, and purchase orders. NEVER compute "
            "or verify a total. Record what is printed. Flag what is unclear."
        )

    # ------------------------------------------------------------------
    # Step 3: Financial Python Engine (deterministic, no LLM)
    # ------------------------------------------------------------------

    def financial_validate(self, logistics_records: list[dict]) -> tuple[dict, dict]:
        """Run the Financial Python engine against logistics records.

        Returns:
            (ledger_dict, exceptions_dict)
        """
        # Write records to a temp file for the engine
        temp_input = LOGISTICS_DIR / "output.json"
        with open(temp_input, "w", encoding="utf-8") as f:
            json.dump(logistics_records, f, indent=2, ensure_ascii=False)

        engine_script = FINANCIAL_DIR / "engine.py"
        result = subprocess.run(
            [PYTHON, str(engine_script), str(temp_input)],
            cwd=str(FINANCIAL_DIR),
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Financial engine failed: {result.stderr[-500:]}")

        logistics_dir = temp_input.parent
        ledger_path = logistics_dir / "ledger.json"
        exceptions_path = logistics_dir / "exceptions.json"

        with open(ledger_path, "r", encoding="utf-8") as f:
            ledger = json.load(f)
        with open(exceptions_path, "r", encoding="utf-8") as f:
            exceptions = json.load(f)

        return ledger, exceptions

    # ------------------------------------------------------------------
    # Step 4: Secretary LLM — Tasks, Chase Emails, Final Report
    # ------------------------------------------------------------------

    def secretary_report_llm(
        self,
        goal: str,
        exceptions: list[dict],
        logistics_records: list[dict],
    ) -> dict:
        """Secretary LLM converts exceptions to tasks, chase emails, and a final report.

        If LLM is not available, falls back to the Python Secretary.

        Returns a dict with:
            - plan: dict (from step 1)
            - tasks: list of task dicts
            - chase_emails: list of email dicts
            - final_report: dict
            - source: "llm" or "python_fallback"
        """
        if not self._llm_available():
            return self._secretary_report_python(goal, exceptions, logistics_records)

        system_prompt = self.secretary_prompt or self._fallback_secretary_prompt()

        # Prepare exceptions summary for the LLM
        exc_summary = json.dumps(exceptions[:50], ensure_ascii=False, indent=2)  # Cap at 50 to fit context
        doc_summary = json.dumps(
            [{"vendor": r.get("vendor_name", "?"), "amount": r.get("grand_total", r.get("amount", 0)),
              "type": r.get("document_type", "?"), "ref": r.get("source_ref", "?")}
             for r in logistics_records],
            ensure_ascii=False, indent=2
        )

        user_prompt = (
            f"Business goal: {goal}\n\n"
            f"Exceptions from Financial agent ({len(exceptions)} total):\n{exc_summary}\n\n"
            f"Document summary ({len(logistics_records)} docs):\n{doc_summary}\n\n"
            "Based on these exceptions, generate:\n"
            "1. A list of tasks (one per exception) with priority (P1-P4), plain-language title, and action required.\n"
            "2. Chase emails ONLY for overdue items (human-in-the-loop: drafts, never sent).\n"
            "3. A final report with cash flow summary, category breakdown, and top 3 actions.\n\n"
            "Return a JSON object:\n"
            '{"tasks": [{"task_id": "TASK-0001", "title": "...", "priority": "P1"|"P2"|"P3"|"P4", '
            '"invoice_number": "...", "vendor_name": "...", "amount": 0.0, "action_required": "...", '
            '"status": "pending"}], '
            '"chase_emails": [{"email_id": "EMAIL-001", "subject": "...", "body": "...", '
            '"related_invoice": "...", "status": "draft"}], '
            '"final_report": {"goal": "...", "period": "...", "cash_in": 0.0, "cash_out": 0.0, '
            '"net_cash": 0.0, "top_3_actions": ["...", "...", "..."], '
            '"total_exceptions": 0, "tasks_generated": 0, "chase_emails_drafted": 0}}\n'
            "Return ONLY the JSON, no explanation."
        )

        try:
            response = self.call_llm(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                json_mode=True,
                temperature=0.3,
            )
            report_data = json.loads(response)
            report_data["source"] = "llm"
            return report_data
        except Exception as e:
            print(f"  [Orchestrator] Secretary report LLM failed: {e}")
            return self._secretary_report_python(goal, exceptions, logistics_records)

    def _secretary_report_python(
        self,
        goal: str,
        exceptions_raw: list[dict],
        logistics_records: list[dict],
    ) -> dict:
        """Fallback: use the Python Secretary pipeline for tasks + report."""
        from src.secretary import Secretary
        from src.models import DocumentInfo, ExceptionEvent, EventType

        # Convert exceptions (same logic as run_pipeline.py)
        doc_lookup = {}
        for rec in logistics_records:
            for key in ["invoice_number", "receipt_number", "po_number", "document_number"]:
                if key in rec and rec[key]:
                    doc_lookup[rec[key]] = rec
            if "source_ref" in rec:
                doc_lookup[rec["source_ref"]] = rec

        def safe_str(val):
            if isinstance(val, str):
                return val
            if isinstance(val, dict):
                return json.dumps(val, ensure_ascii=False)
            if val is None:
                return ""
            return str(val)

        events = []
        for fin_exc in exceptions_raw:
            try:
                exc_type = fin_exc.get("type", "")
                doc_num = fin_exc.get("document_number", "")
                vendor = fin_exc.get("vendor_name", "Unknown Vendor")
                details = safe_str(fin_exc.get("details", fin_exc.get("reason", "")))
                reason = fin_exc.get("reason", exc_type)

                rec = doc_lookup.get(doc_num, {})
                amount = rec.get("grand_total", fin_exc.get("delta", 0.0))
                if not isinstance(amount, (int, float)):
                    amount = 0.0
                invoice_date = rec.get("invoice_date", rec.get("document_date", ""))
                due_date = rec.get("due_date", "")

                conf = rec.get("confidence", {})
                if isinstance(conf, dict):
                    vals = [v for v in conf.values() if isinstance(v, (int, float))]
                    confidence = min(vals) if vals else None
                elif isinstance(conf, (int, float)):
                    confidence = conf
                else:
                    confidence = None

                if "duplicate" in exc_type:
                    events.append(ExceptionEvent(
                        event_type=EventType.DUPLICATE,
                        invoice_number=doc_num, vendor_name=vendor, amount=amount,
                        invoice_date=invoice_date, details=details,
                        duplicate_of=safe_str(fin_exc.get("details", "")),
                    ))
                elif "missing_po_reference" in exc_type:
                    events.append(ExceptionEvent(
                        event_type=EventType.ESCALATION,
                        invoice_number=doc_num, vendor_name=vendor, amount=amount,
                        invoice_date=invoice_date, details=details,
                        escalation_reason=reason, escalation_code="MISSING_PO",
                    ))
                elif "tax_rate" in exc_type or "arithmetic" in exc_type or "conflicting" in exc_type:
                    events.append(ExceptionEvent(
                        event_type=EventType.ESCALATION,
                        invoice_number=doc_num, vendor_name=vendor, amount=amount,
                        invoice_date=invoice_date, details=details,
                        escalation_reason=reason, escalation_code=exc_type.upper(),
                    ))
                elif "overdue" in exc_type:
                    events.append(ExceptionEvent(
                        event_type=EventType.OVERDUE,
                        invoice_number=doc_num, vendor_name=vendor, amount=amount,
                        invoice_date=invoice_date, due_date=due_date, details=details,
                    ))
                elif "low_confidence" in exc_type:
                    events.append(ExceptionEvent(
                        event_type=EventType.FLAGGED,
                        invoice_number=doc_num, vendor_name=vendor, amount=amount,
                        invoice_date=invoice_date, details=details,
                        flag_reason="Low OCR confidence",
                        confidence=confidence,
                    ))
                else:
                    events.append(ExceptionEvent(
                        event_type=EventType.FLAGGED,
                        invoice_number=doc_num, vendor_name=vendor, amount=amount,
                        invoice_date=invoice_date, details=details,
                        flag_reason=reason, confidence=confidence,
                    ))
            except Exception as e:
                print(f"  SKIP: {fin_exc.get('type', '?')}: {e}")

        # Build DocumentInfo list
        documents = []
        for rec in logistics_records:
            try:
                doc = DocumentInfo(
                    doc_id=rec.get("source_ref", rec.get("document_number", "unknown")),
                    file_name=rec.get("source_ref", "unknown.pdf"),
                    doc_type=rec.get("document_type", "invoice"),
                    vendor_name=rec.get("vendor_name", rec.get("supplier_name", "Unknown")),
                    invoice_number=rec.get("invoice_number", rec.get("receipt_number", rec.get("po_number", ""))),
                    invoice_date=rec.get("invoice_date", rec.get("document_date", "")),
                    grand_total=rec.get("grand_total", rec.get("total", 0.0)),
                    confidence=0.9,
                    quality_flags=rec.get("flags", []),
                )
                documents.append(doc)
            except Exception:
                pass

        secretary = Secretary()
        result = secretary.run(
            goal=goal,
            exceptions=events,
            documents=documents,
        )

        # Convert to dict
        result_dict = json.loads(json.dumps(result.model_dump(), default=str, ensure_ascii=False))
        result_dict["source"] = "python_fallback"
        return result_dict

    # ------------------------------------------------------------------
    # Full Pipeline
    # ------------------------------------------------------------------

    def run(self, goal: str = "Close out September", document_images: list[Path] | None = None) -> dict:
        """Run the full 4-step pipeline.

        Args:
            goal: Business goal string (e.g., "Close out September")
            document_images: Optional list of image paths for LLM vision extraction.
                If None, uses pre-extracted output.json.

        Returns:
            A dict with all pipeline stages:
            {
                "goal": str,
                "plan": {plan phases},
                "logistics": {records: [...], count: N},
                "financial": {ledger: {...}, exceptions: {...}},
                "secretary": {tasks: [...], chase_emails: [...], final_report: {...}},
                "timings": {step1: Xs, step2: Xs, step3: Xs, step4: Xs, total: Xs},
                "sources": {plan: "llm"|"python_fallback", logistics: ..., secretary: ...}
            }
        """
        timings: dict[str, float] = {}
        sources: dict[str, str] = {}
        t_start = time.time()

        # Step 1: Secretary LLM — Generate Plan
        print("\n" + "=" * 60)
        print("  STEP 1/4: SECRETARY (PLAN)")
        print("=" * 60)
        t = time.time()
        plan_data = self.secretary_plan_llm(goal)
        timings["step1_plan"] = round(time.time() - t, 2)
        sources["plan"] = plan_data.get("source", "unknown")
        print(f"  Plan source: {sources['plan']}")
        print(f"  Phases: {len(plan_data.get('phases', []))}")
        for phase in plan_data.get("phases", []):
            print(f"    {phase.get('phase', '?')}. [{phase.get('agent', '?')}] {phase.get('action', '?')}")

        # Step 2: Logistics LLM — Extract Documents
        print("\n" + "=" * 60)
        print("  STEP 2/4: LOGISTICS (EXTRACT)")
        print("=" * 60)
        t = time.time()
        logistics_records = self.logistics_extract_llm(document_images)
        timings["step2_logistics"] = round(time.time() - t, 2)
        sources["logistics"] = "llm" if document_images and self._llm_available() else "python_fallback"
        print(f"  Logistics source: {sources['logistics']}")
        print(f"  Documents extracted: {len(logistics_records)}")
        clean = sum(1 for r in logistics_records if r.get("status") == "clean")
        flagged = sum(1 for r in logistics_records if r.get("status") == "flagged")
        error = sum(1 for r in logistics_records if r.get("status") == "error")
        print(f"  Status: {clean} clean, {flagged} flagged, {error} error")

        # Step 3: Financial Python — Validate
        print("\n" + "=" * 60)
        print("  STEP 3/4: FINANCIAL (VALIDATE)")
        print("=" * 60)
        t = time.time()
        ledger, exceptions = self.financial_validate(logistics_records)
        timings["step3_financial"] = round(time.time() - t, 2)
        sources["financial"] = "python_engine"
        exc_list = exceptions.get("exceptions", exceptions) if isinstance(exceptions, dict) else exceptions
        print(f"  Ledger rows: {len(ledger.get('rows', []))}")
        print(f"  Total out: RM {ledger.get('summary', {}).get('total_out', 0):,.2f}")
        print(f"  Exceptions: {len(exc_list)}")

        # Step 4: Secretary LLM — Tasks, Chase Emails, Final Report
        print("\n" + "=" * 60)
        print("  STEP 4/4: SECRETARY (TASKS + REPORT)")
        print("=" * 60)
        t = time.time()
        secretary_result = self.secretary_report_llm(goal, exc_list, logistics_records)
        timings["step4_secretary"] = round(time.time() - t, 2)
        sources["secretary"] = secretary_result.get("source", "unknown")
        print(f"  Secretary source: {sources['secretary']}")
        tasks = secretary_result.get("tasks", [])
        chase_emails = secretary_result.get("chase_emails", [])
        final_report = secretary_result.get("final_report", {})
        print(f"  Tasks generated: {len(tasks)}")
        print(f"  Chase emails drafted: {len(chase_emails)}")
        if final_report:
            print(f"  Cash in:  RM {final_report.get('cash_in', 0):,.2f}")
            print(f"  Cash out: RM {final_report.get('cash_out', 0):,.2f}")
            print(f"  Net cash: RM {final_report.get('net_cash', 0):,.2f}")

        timings["total"] = round(time.time() - t_start, 2)

        # Assemble full result
        return {
            "goal": goal,
            "plan": plan_data,
            "logistics": {
                "records": logistics_records,
                "count": len(logistics_records),
                "summary": {
                    "clean": clean,
                    "flagged": flagged,
                    "error": error,
                },
            },
            "financial": {
                "ledger": ledger,
                "exceptions": exceptions,
                "exception_count": len(exc_list),
            },
            "secretary": {
                "tasks": tasks,
                "chase_emails": chase_emails,
                "final_report": final_report,
                "exceptions_processed": secretary_result.get("exceptions_processed", len(exc_list)),
                "warnings": secretary_result.get("warnings", []),
            },
            "timings": timings,
            "sources": sources,
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def discover_document_images() -> list[Path]:
    """Find document images in the test-documents directory."""
    if not TEST_DOCS_DIR.exists():
        return []
    images = []
    for ext in ["*.png", "*.jpg", "*.jpeg"]:
        images.extend(TEST_DOCS_DIR.rglob(ext))
    return sorted(images)


def main():
    parser = argparse.ArgumentParser(
        description="Banjir Productivity — LLM Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--goal", type=str, default="Close out September",
        help="Business goal (default: 'Close out September')",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Write output to a file",
    )
    parser.add_argument(
        "--use-images", action="store_true",
        help="Use document images for LLM vision extraction (requires test-documents/ dir)",
    )
    parser.add_argument(
        "--llm-status", action="store_true",
        help="Check LLM endpoint status and exit",
    )
    args = parser.parse_args()

    if args.llm_status:
        orch = PipelineOrchestrator()
        available = orch._llm_available()
        print(f"LLM endpoint: {LLM_API_URL}")
        print(f"LLM model: {LLM_MODEL}")
        print(f"LLM vision model: {LLM_VISION_MODEL}")
        print(f"LLM available: {'YES' if available else 'NO'}")
        print(f"Test docs dir: {TEST_DOCS_DIR} ({'exists' if TEST_DOCS_DIR.exists() else 'missing'})")
        if available:
            images = discover_document_images()
            print(f"Document images found: {len(images)}")
        return

    orch = PipelineOrchestrator()

    # Determine if we should use LLM vision extraction
    document_images = None
    if args.use_images:
        document_images = discover_document_images()
        if document_images:
            print(f"Using {len(document_images)} document images for LLM extraction")
        else:
            print("No document images found, using pre-extracted output.json")

    result = orch.run(goal=args.goal, document_images=document_images)

    # Output
    if args.json:
        output = json.dumps(result, indent=2, default=str, ensure_ascii=False)
    else:
        output = _format_result_text(result)

    print(output)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json.dumps(result, indent=2, default=str, ensure_ascii=False))
        print(f"\n  JSON saved: {args.output}")

    # Always save to secretary_result.json
    default_save = str(LOGISTICS_DIR / "orchestrator_result.json")
    with open(default_save, "w", encoding="utf-8") as f:
        f.write(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    print(f"  Also saved: {default_save}")


def _format_result_text(result: dict) -> str:
    """Format the full pipeline result as human-readable text."""
    lines: list[str] = []

    lines.append("=" * 60)
    lines.append("  BANJIR PRODUCTIVITY — PIPELINE RESULT")
    lines.append(f"  Goal: {result['goal']}")
    lines.append("=" * 60)

    # Plan
    plan = result.get("plan", {})
    lines.append(f"\n  PLAN ({plan.get('source', '?')})")
    lines.append("  " + "-" * 40)
    for phase in plan.get("phases", []):
        lines.append(
            f"  {phase.get('phase', '?')}. [{phase.get('agent', '?')}] "
            f"{phase.get('action', '?')} ({phase.get('status', '?')})"
        )

    # Logistics
    logistics = result.get("logistics", {})
    lines.append(f"\n  LOGISTICS ({result.get('sources', {}).get('logistics', '?')})")
    lines.append("  " + "-" * 40)
    lines.append(f"  Documents: {logistics.get('count', 0)}")
    summary = logistics.get("summary", {})
    lines.append(f"  Clean: {summary.get('clean', 0)}, Flagged: {summary.get('flagged', 0)}, Error: {summary.get('error', 0)}")

    # Financial
    financial = result.get("financial", {})
    ledger = financial.get("ledger", {})
    lines.append(f"\n  FINANCIAL (python_engine)")
    lines.append("  " + "-" * 40)
    lines.append(f"  Ledger rows: {len(ledger.get('rows', []))}")
    led_summary = ledger.get("summary", {})
    lines.append(f"  Total in:  RM {led_summary.get('total_in', 0):,.2f}")
    lines.append(f"  Total out: RM {led_summary.get('total_out', 0):,.2f}")
    lines.append(f"  Net cash:  RM {led_summary.get('net_cash_flow', 0):,.2f}")
    lines.append(f"  Exceptions: {financial.get('exception_count', 0)}")

    # Secretary
    secretary = result.get("secretary", {})
    lines.append(f"\n  SECRETARY ({result.get('sources', {}).get('secretary', '?')})")
    lines.append("  " + "-" * 40)
    lines.append(f"  Tasks: {len(secretary.get('tasks', []))}")
    lines.append(f"  Chase emails: {len(secretary.get('chase_emails', []))}")

    final_report = secretary.get("final_report", {})
    if final_report:
        lines.append("")
        lines.append("  CASH FLOW SUMMARY")
        lines.append(f"    Cash In:   RM {final_report.get('cash_in', 0):,.2f}")
        lines.append(f"    Cash Out:  RM {final_report.get('cash_out', 0):,.2f}")
        lines.append(f"    Net Cash:  RM {final_report.get('net_cash', 0):,.2f}")

        top3 = final_report.get("top_3_actions", [])
        if top3:
            lines.append("")
            lines.append("  TOP 3 RECOMMENDED ACTIONS")
            for i, action in enumerate(top3, 1):
                lines.append(f"    {i}. {action}")

    # Timings
    timings = result.get("timings", {})
    lines.append("")
    lines.append("=" * 60)
    lines.append("  TIMINGS")
    lines.append("=" * 60)
    for step, dur in timings.items():
        lines.append(f"  {step}: {dur}s")

    # Sources
    sources = result.get("sources", {})
    lines.append("")
    lines.append("  AGENT SOURCES")
    lines.append("  " + "-" * 40)
    for agent, src in sources.items():
        lines.append(f"  {agent}: {src}")

    return "\n".join(lines)


if __name__ == "__main__":
    main()

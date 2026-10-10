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
import mimetypes
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
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

# Load KEY=value lines from repo-root .env (gitignored); real env vars take precedence
_ENV_FILE = PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _key, _sep, _value = _line.strip().partition("=")
        if _sep and _key and not _key.startswith("#"):
            os.environ.setdefault(_key.strip(), _value.strip())

LLM_API_URL = os.environ.get("LLM_API_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
LLM_VISION_MODEL = os.environ.get("LLM_VISION_MODEL", LLM_MODEL)

# Timeout for LLM calls (seconds)
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "120"))
# Parallel vision calls when reading documents live (free tiers rate-limit bursts)
LLM_CONCURRENCY = int(os.environ.get("LLM_CONCURRENCY", "4"))

# Test document images directory (optional — if missing, use pre-extracted JSON)
TEST_DOCS_DIR = PROJECT_ROOT / "test-documents"


# ---------------------------------------------------------------------------
# Self-check for LLM-extracted records
# ---------------------------------------------------------------------------

_NUMBER_FIELDS = ("subtotal", "total_tax", "grand_total", "tax_rate", "amount", "tax_amount")
_LINE_NUMBER_FIELDS = ("quantity", "unit_price", "amount", "tax_amount", "tax_rate")
_DATE_FORMATS = ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%b %d, %Y")


def _to_number(value):
    """'10%' -> 10.0, 'RM 1,200.00' -> 1200.0. Returns (value, ok)."""
    if value is None or isinstance(value, (int, float)):
        return value, True
    try:
        return float(re.sub(r"(?i)rm|myr|%|,|\s", "", str(value))), True
    except ValueError:
        return None, False


def _to_iso_date(value):
    """'07 Oct 2026' -> '2026-10-07'. Returns (value, ok)."""
    if not value:
        return value, True
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(str(value).strip(), fmt).date().isoformat(), True
        except ValueError:
            pass
    return None, False


def normalize_extracted(rec: dict) -> dict:
    """Coerce an LLM-extracted record to the types the Financial engine expects.

    Anything that can't be parsed becomes null and the record is flagged
    'unparseable_field' -- never guessed, so Financial raises it as an exception.
    """
    bad: list[str] = []

    def fix(obj: dict, key: str, convert, label: str) -> None:
        if key in obj:
            obj[key], ok = convert(obj[key])
            if not ok:
                bad.append(label)

    for key in _NUMBER_FIELDS:
        fix(rec, key, _to_number, key)
    for key in [k for k in rec if k == "date" or k.endswith("_date")]:
        fix(rec, key, _to_iso_date, key)
    for i, line in enumerate(rec.get("line_items") or []):
        if isinstance(line, dict):
            for key in _LINE_NUMBER_FIELDS:
                fix(line, key, _to_number, f"line_items[{i}].{key}")
    if isinstance(rec.get("confidence"), dict):
        rec["confidence"] = {k: (_to_number(v)[0] or 0.0) for k, v in rec["confidence"].items()}

    flags = rec.get("flags") or []
    rec["flags"] = [flags] if isinstance(flags, str) else list(flags)
    if bad:
        rec["flags"].append("unparseable_field")
        if rec.get("status") != "error":
            rec["status"] = "flagged"
        rec["notes"] = f"{rec.get('notes') or ''} Unparseable from extraction: {', '.join(bad)}.".strip()
    return rec


_CHECK_FIELDS = {  # per document type: number, dates, references, every printed amount
    "invoice": ("invoice_number", "invoice_date", "due_date", "po_reference", "subtotal", "total_tax", "grand_total"),
    "receipt": ("receipt_number", "receipt_date", "invoice_reference", "subtotal", "tax_amount", "amount"),
    "order": ("po_number", "po_date", "subtotal", "total_tax", "grand_total"),
    "po": ("po_number", "po_date", "subtotal", "total_tax", "grand_total"),
}
_CONFLICT_FLAG = "conflicting_values"  # Financial raises conflicting_printed_values from this flag


def verify_extraction(records: list[dict], reference: list[dict]) -> dict:
    """Self-check live extraction against the hand-checked records (same source_ref).

    Compares document type, vendor, number, dates, references, every printed amount,
    and whether both flagged conflicting printed figures. Returns field accuracy, a
    per-field breakdown and every mismatch, so a wrong read is visible instead of silent.
    """
    ref_by_src = {r.get("source_ref"): r for r in reference}
    checked = matched = compared = 0
    by_field: dict[str, list[int]] = {}
    mismatches = []
    for rec in records:
        ref = ref_by_src.get(rec.get("source_ref"))
        if not ref:
            continue
        compared += 1
        doc_type = ref.get("document_type", "invoice")
        fields = ("document_type", "vendor_name") + _CHECK_FIELDS.get(doc_type, _CHECK_FIELDS["invoice"]) + (_CONFLICT_FLAG,)
        for field in fields:
            if field == _CONFLICT_FLAG:
                want, got = _CONFLICT_FLAG in (ref.get("flags") or []), _CONFLICT_FLAG in (rec.get("flags") or [])
            else:
                want, got = ref.get(field), rec.get(field)
            if isinstance(want, bool) or isinstance(got, bool):
                ok = want == got
            elif isinstance(want, (int, float)) and isinstance(got, (int, float)):
                ok = abs(want - got) <= 0.01
            else:
                ok = str(want or "").strip().lower() == str(got or "").strip().lower()
            if field == "document_type":
                ok = ok or {str(want), str(got)} == {"order", "po"}
            checked += 1
            matched += ok
            tally = by_field.setdefault(field, [0, 0])
            tally[0] += ok
            tally[1] += 1
            if not ok:
                mismatches.append({"source_ref": rec.get("source_ref"), "field": field, "expected": want, "extracted": got})
    return {
        "documents_compared": compared,
        "fields_checked": checked,
        "fields_matched": matched,
        "accuracy": round(matched / checked, 3) if checked else None,
        "by_field": {f: {"matched": m, "checked": c} for f, (m, c) in by_field.items()},
        "mismatches": mismatches,
    }


# ---------------------------------------------------------------------------
# Secretary output helpers
# ---------------------------------------------------------------------------

# Problems only the vendor can fix (they must confirm or re-issue the document).
# The Python Secretary drafts emails for overdue invoices only, and this data set
# has no due dates, so without this it never drafts any.
VENDOR_FIX_TYPES = {"conflicting_printed_values", "arithmetic_mismatch"}


def chase_targets(exceptions: list[dict]) -> list[dict]:
    """One chase-email target per vendor document (invoice/receipt) with a vendor-fixable problem."""
    targets: dict[str, dict] = {}
    for exc in exceptions:
        if exc.get("type") not in VENDOR_FIX_TYPES or exc.get("document_type") not in ("invoice", "receipt"):
            continue
        doc = exc.get("document_number") or exc.get("source_ref", "?")
        target = targets.setdefault(doc, {
            "document_number": doc, "vendor_name": exc.get("vendor_name") or "Vendor",
            "source_ref": exc.get("source_ref", ""), "problems": [],
        })
        target["problems"].append(exc.get("reason", exc.get("type")))
    return list(targets.values())


def template_chase_email(target: dict, n: int) -> dict:
    """Plain draft used when the LLM is unavailable or skipped a target."""
    problems = "\n".join(f"- {p}" for p in target["problems"])
    return {
        "email_id": f"EMAIL-{n:03d}",
        "related_invoice": target["document_number"],
        "vendor_name": target["vendor_name"],
        "source_ref": target["source_ref"],
        "subject": f"Please confirm {target['document_number']}",
        "body": (f"Dear {target['vendor_name']},\n\n"
                 f"While closing our books we found the following on {target['document_number']}:\n"
                 f"{problems}\n\nCould you confirm the correct figures or send a corrected copy?\n\n"
                 "Thank you."),
        "status": "draft",
        "source": "template",
    }


def build_chase_emails(targets: list[dict], llm_emails: list) -> list[dict]:
    """One draft per target: the LLM's text when it wrote a usable one, else the template."""
    by_doc = {e.get("related_invoice"): e for e in llm_emails or []
              if isinstance(e, dict) and e.get("subject") and e.get("body")}
    emails = []
    for n, target in enumerate(targets, 1):
        email = template_chase_email(target, n)
        llm = by_doc.get(target["document_number"])
        if llm:
            email.update(subject=str(llm["subject"]), body=str(llm["body"]), source="llm")
        emails.append(email)
    return emails


# Exception types that, when they hit many documents, describe the document set
# rather than one document: one observation each instead of a task per document.
# Financial still raises every one (Exceptions tab); only tasks/checklist collapse.
SYSTEMIC_TYPES = {
    "no_due_date": "{n} invoices carry no payment terms (no due date), so overdue status can't be checked",
    "missing_po_match": "{n} invoices have no matching purchase order among the documents on file",
}
SYSTEMIC_MIN_DOCS = 5


def split_systemic(exceptions: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (actionable exceptions, one observation per systemic type)."""
    docs: dict[str, set] = {}
    for exc in exceptions:
        if exc.get("type") in SYSTEMIC_TYPES:
            docs.setdefault(exc["type"], set()).add(exc.get("source_ref") or exc.get("document_number"))
    systemic = {t for t, refs in docs.items() if len(refs) >= SYSTEMIC_MIN_DOCS}
    observations = [
        {"type": t, "count": len(docs[t]), "text": SYSTEMIC_TYPES[t].format(n=len(docs[t])),
         "documents": sorted({e.get("document_number") for e in exceptions if e.get("type") == t} - {None})}
        for t in SYSTEMIC_TYPES if t in systemic
    ]
    return [e for e in exceptions if e.get("type") not in systemic], observations


def report_from_ledger(report: dict, ledger: dict, exceptions: list, tasks: list, emails: list) -> dict:
    """Overwrite every figure in the report with the Financial ledger's numbers.

    An LLM-written report invented cash figures (RM 21,875.70 out vs RM 11,974.00
    in the ledger); the report must never disagree with the ledger.
    """
    s = ledger.get("summary", {})
    report = dict(report or {})
    report.update(
        cash_in=s.get("total_in", 0.0),
        cash_out=round(s.get("total_out", 0.0) + s.get("total_tax", 0.0), 2),  # incl. SST, so in - out = net
        net_cash=s.get("net_cash_flow", 0.0),
        total_tax=s.get("total_tax", 0.0),
        categories=[{"category": c["category"], "total": round(c["total_amount"], 2), "count": c["row_count"]}
                    for c in s.get("by_category", [])],
        reconciliation_rate=s.get("reconciliation_rate", 0.0),
        total_exceptions=len(exceptions),
        tasks_generated=len(tasks),
        chase_emails_drafted=len(emails),
        figures_source="financial_ledger",
    )
    return report


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

        all_records = self.extract_documents(document_images)

        # If all extractions failed, fall back
        if not all_records:
            print("  [Orchestrator] All LLM extractions failed, using Python fallback")
            return self._logistics_python()

        return all_records

    def extract_documents(self, document_paths: list[Path]) -> list[dict]:
        """Vision-extract each document (image or PDF), LLM_CONCURRENCY at a time.

        No fallback: a failed document comes back as an error record so
        Financial flags it. Output order matches document_paths.
        """
        with ThreadPoolExecutor(max_workers=max(1, LLM_CONCURRENCY)) as pool:
            return list(pool.map(self._extract_one, document_paths))

    def _extract_one(self, img_path: Path) -> dict:
        system_prompt = self.logistics_prompt or self._fallback_logistics_prompt()
        try:
            source_ref = img_path.resolve().relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            source_ref = img_path.name
        try:
            img_b64 = base64.b64encode(img_path.read_bytes()).decode("utf-8")
            mime = mimetypes.guess_type(img_path.name)[0] or "image/jpeg"
            user_prompt = (
                "Extract this document into one structured JSON record.\n"
                f"Document source: {img_path.name}\n\n"
                f"{self.extraction_template or ''}\n\n"
                "Rules:\n"
                "1. Record fields exactly as printed. NEVER compute or verify any total.\n"
                "2. Assign a confidence score (0.0-1.0) to each critical field, in a 'confidence' object.\n"
                "3. If a field is unparseable, set it to null and add a flag.\n"
                "4. If the document is bad (blurry, handwritten), do not guess. Flag it.\n"
                "4a. If the document prints two DIFFERENT figures for the same thing (two totals, two SST "
                "amounts, a stray unlabelled number next to a total), add the flag 'conflicting_values' and put "
                "both figures in a 'notes' string, e.g. "
                "\"Two totals printed: 'TOTAL AMOUNT: RM 425.00' and 'RM45.70' below it.\" "
                "The same value printed twice (e.g. 'TOTAL: RM 352.00' and 'RM 352.00' below it) is NOT a "
                "conflict: no flag. Record the LABELLED figure, i.e. the number next to its label "
                "('SST 10%: 9.50' -> total_tax 9.50), not a number from the amount column.\n"
                "4b. Confidence measures how sure the VALUE is, not how sharp the print is: a field with two "
                "printed values, garbled characters (e.g. '120ping', '12.0ai'), or a value you had to infer "
                "gets confidence 0.5-0.65. Use the same flags as the source: conflicting_values, "
                "unreadable_field, handwritten, blurry_image, no_po_reference, possible_duplicate.\n"
                "5. Record the SST rate and amount as printed; do not correct them.\n"
                "6. Numbers are JSON numbers (tax_rate 10, not '10%'; 1200.0, not 'RM 1,200'). Dates are YYYY-MM-DD.\n"
                "7. Return a single JSON object, no explanation.\n\n"
                "document_type is one of invoice, receipt, order. Use the fields for that type:\n"
                "- invoice: vendor_name, invoice_number, invoice_date, due_date, po_reference, "
                "line_items [{description, quantity, unit_price}], subtotal, total_tax, tax_rate, grand_total\n"
                "- receipt: vendor_name, receipt_number, receipt_date, payment_method, "
                "line_items [{description, amount}], subtotal, tax_amount, tax_rate, amount, invoice_reference\n"
                "- order (purchase order): vendor_name, po_number, po_date, buyer_name, delivery_date, "
                "line_items [{description, quantity, unit_price}], subtotal, total_tax, tax_rate, grand_total\n"
                "Always include: document_type, currency, confidence, status (clean|flagged|error), flags, "
                "and notes (empty string if nothing unusual)."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                ]},
            ]
            for attempt in range(3):
                try:
                    response = self.call_llm(messages, model=LLM_VISION_MODEL, temperature=0.1, json_mode=True)
                    break
                except urllib.error.HTTPError as e:
                    if e.code != 429 or attempt == 2:  # only rate limits are worth retrying
                        raise
                    time.sleep(2 * (attempt + 1))
            record = normalize_extracted(json.loads(response))
            record["source_ref"] = source_ref
            return record
        except Exception as e:
            print(f"  [Orchestrator] Failed to extract {img_path.name}: {e}")
            return {
                "document_type": "unknown",
                "source_ref": source_ref,
                "status": "error",
                "flags": ["extraction_failed"],
                "confidence": {},
            }

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
        # Engine writes ledger.json + exceptions.json next to its input, so run it
        # in a temp dir: keeps agents/logistics/output.json intact (and works on
        # read-only hosts like Vercel, where only the temp dir is writable).
        with tempfile.TemporaryDirectory() as run_dir:
            temp_input = Path(run_dir) / "records.json"
            temp_input.write_text(json.dumps(logistics_records, indent=2, ensure_ascii=False), encoding="utf-8")

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

            ledger = json.loads((Path(run_dir) / "ledger.json").read_text(encoding="utf-8"))
            exceptions = json.loads((Path(run_dir) / "exceptions.json").read_text(encoding="utf-8"))

        return ledger, exceptions

    # ------------------------------------------------------------------
    # Step 1b: Secretary — fetch new documents from Gmail
    # ------------------------------------------------------------------

    def gmail_fetch(self) -> dict:
        """Pull invoice/receipt/PO attachments from Gmail (TAO's GmailCrawler).

        Runs only with a real, already-authorised account: credentials.json AND
        token.json in agents/secretary/ (create the token once with
        `cd agents/secretary && python -m src.cli --gmail`). A web request never
        opens the OAuth browser flow, and mock-mode attachments are placeholder
        PDFs, so they are never sent to extraction.

        Returns {"status", "emails": [...], "files": [(path, email), ...]}.
        """
        from src.config import GMAIL_CREDENTIALS_FILE, GMAIL_TOKEN_FILE

        if not (GMAIL_CREDENTIALS_FILE.exists() and GMAIL_TOKEN_FILE.exists()):
            status = "needs_login" if GMAIL_CREDENTIALS_FILE.exists() else "not_configured"
            return {"status": status, "emails": [], "files": []}

        from src.gmail_crawler import GmailCrawler
        crawler = GmailCrawler()
        crawler.authenticate()
        if crawler.mock:  # Google libraries missing -> crawler fell back to mock
            return {"status": "libraries_missing", "emails": [], "files": []}

        # Month-end close needs every matching email, not just unseen ones
        emails = crawler.fetch_invoice_emails(skip_processed=False)
        files = [(Path(f), e) for e in emails for f in e.downloaded_files]
        return {
            "status": "ok",
            "emails": [
                {"message_id": e.message_id, "sender": e.sender, "subject": e.subject,
                 "date": e.date, "vendor_name": e.vendor_name,
                 "attachments": [Path(f).name for f in e.downloaded_files]}
                for e in emails
            ],
            "files": files,
        }

    # ------------------------------------------------------------------
    # Step 4: Secretary — tasks (Python), chase emails + report (LLM)
    # ------------------------------------------------------------------

    def secretary_report_llm(self, goal: str, exceptions: list[dict], targets: list[dict]) -> dict | None:
        """LLM writes the chase emails for `targets` and the report narrative.

        Tasks are NOT asked of the LLM: the Python task generator makes one per
        exception, which the LLM never reliably did. Returns None when the LLM is
        unavailable or fails, so callers fall back to templates.
        """
        if not self._llm_available():
            return None

        system_prompt = self.secretary_prompt or self._fallback_secretary_prompt()
        counts: dict[str, int] = {}
        for exc in exceptions:
            counts[exc.get("type", "unknown")] = counts.get(exc.get("type", "unknown"), 0) + 1
        critical = [
            {k: exc.get(k) for k in ("type", "document_number", "vendor_name", "reason")}
            for exc in exceptions if exc.get("severity") == "critical"
        ][:30]

        user_prompt = (
            f"Business goal: {goal}\n\n"
            f"Exception counts from the Financial agent ({len(exceptions)} total): {json.dumps(counts)}\n"
            f"Critical exceptions:\n{json.dumps(critical, ensure_ascii=False, indent=2)}\n\n"
            f"Vendor documents that need a chase email ({len(targets)}):\n"
            f"{json.dumps(targets, ensure_ascii=False, indent=2)}\n\n"
            "Write:\n"
            "1. Exactly one polite chase email per vendor document above, asking the vendor to confirm or "
            "re-issue the document and explaining each problem in plain language. Drafts only, never sent. "
            "Do not invent amounts or dates beyond what is given.\n"
            "2. The top 3 actions for the business owner, in plain language.\n\n"
            "Return a JSON object:\n"
            '{"chase_emails": [{"related_invoice": "<document_number>", "subject": "...", "body": "..."}], '
            '"top_3_actions": ["...", "...", "..."]}\n'
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
            data = json.loads(response)
            return data if isinstance(data, dict) else None
        except Exception as e:
            print(f"  [Orchestrator] Secretary LLM failed: {e}")
            return None

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

    def run(self, goal: str = "Close out September", document_images: list[Path] | None = None,
            on_event=None) -> dict:
        """Run the full 4-step pipeline.

        Args:
            goal: Business goal string (e.g., "Close out September")
            document_images: Optional list of image paths for LLM vision extraction.
                If None, uses pre-extracted output.json.
            on_event: Optional callback, called with {"agent", "status", "step"} as each
                agent starts and finishes (app.py streams these to the web page).

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

        def emit(agent: str, status: str, step: str) -> None:
            if on_event:
                on_event({"kind": "status", "agent": agent, "status": status, "step": step})

        def set_phase(agent: str, status: str) -> None:
            """Mark the plan phase(s) owned by `agent` and stream the updated plan."""
            for phase in plan_data.get("phases", []):
                if str(phase.get("agent", "")).lower() == agent.lower():
                    phase["status"] = status
            if on_event:  # copy: the stream serialises on another thread
                on_event({"kind": "plan", "plan": json.loads(json.dumps(plan_data, default=str))})

        emit("Secretary", "working", "Writing the plan")

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
        emit("Secretary", "done", f"Plan ready ({len(plan_data.get('phases', []))} phases)")
        set_phase("Logistics", "in_progress")
        emit("Logistics", "working",
             f"Reading {len(document_images)} scans with Gemini" if document_images else "Loading extracted documents")
        t = time.time()
        logistics_records = self.logistics_extract_llm(document_images)
        # Live reading is opt-in; without it Logistics loads the hand-checked records by design
        if not document_images:
            sources["logistics"] = "hand_checked"
        else:
            sources["logistics"] = "llm" if self._llm_available() else "python_fallback"
        # Live reads are checked against the hand-checked extraction of the same scans
        verification = (verify_extraction(logistics_records, self._logistics_python())
                        if sources["logistics"] == "llm" else None)

        # Gmail: new documents from the inbox join the ones already on file
        gmail = self.gmail_fetch()
        sources["gmail"] = gmail["status"]
        gmail_records: list[dict] = []
        if gmail["files"] and not self._llm_available():
            gmail["status"] = sources["gmail"] = "skipped_no_llm"  # attachments need vision extraction
        elif gmail["files"]:
            gmail_records = self.extract_documents([path for path, _ in gmail["files"]])
            for rec, (path, email) in zip(gmail_records, gmail["files"]):
                rec["source_ref"] = f"gmail:{email.message_id}/{path.name}"
                rec["source_email"] = {"sender": email.sender, "subject": email.subject, "date": email.date}
            logistics_records = logistics_records + gmail_records
        timings["step2_logistics"] = round(time.time() - t, 2)
        print(f"  Logistics source: {sources['logistics']}")
        print(f"  Gmail: {gmail['status']} ({len(gmail['emails'])} emails, {len(gmail_records)} documents extracted)")
        print(f"  Documents extracted: {len(logistics_records)}")
        clean = sum(1 for r in logistics_records if r.get("status") == "clean")
        flagged = sum(1 for r in logistics_records if r.get("status") == "flagged")
        error = sum(1 for r in logistics_records if r.get("status") == "error")
        print(f"  Status: {clean} clean, {flagged} flagged, {error} error")
        emit("Logistics", "done", f"{len(logistics_records)} records ({clean} clean, {flagged} flagged, {error} error)")
        set_phase("Logistics", "done")
        set_phase("Financial", "in_progress")
        emit("Financial", "working", "Building the ledger and checking every document")

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
        emit("Financial", "done", f"{len(ledger.get('rows', []))} ledger rows, {len(exc_list)} exceptions")
        set_phase("Financial", "done")
        set_phase("Secretary", "in_progress")
        emit("Secretary", "working", "Turning exceptions into tasks, emails and the report")

        # Step 4: Secretary — one task per exception (Python), chase emails +
        # report narrative (LLM, template fallback), figures from the ledger
        print("\n" + "=" * 60)
        print("  STEP 4/4: SECRETARY (TASKS + REPORT)")
        print("=" * 60)
        t = time.time()
        actionable, observations = split_systemic(exc_list)
        secretary_result = self._secretary_report_python(goal, actionable, logistics_records)
        tasks = secretary_result.get("tasks", [])
        targets = chase_targets(exc_list)
        llm = self.secretary_report_llm(goal, exc_list, targets)
        chase_emails = build_chase_emails(targets, (llm or {}).get("chase_emails"))
        final_report = secretary_result.get("final_report", {})
        if llm and isinstance(llm.get("top_3_actions"), list) and llm["top_3_actions"]:
            final_report["top_3_actions"] = [str(a) for a in llm["top_3_actions"][:3]]
        final_report = report_from_ledger(final_report, ledger, exc_list, tasks, chase_emails)
        final_report["observations"] = [o["text"] for o in observations]
        timings["step4_secretary"] = round(time.time() - t, 2)
        sources["secretary"] = "llm" if llm else "python_fallback"
        sources["tasks"] = "python_task_generator"
        print(f"  Secretary source: {sources['secretary']}")
        print(f"  Tasks generated: {len(tasks)}")
        print(f"  Chase emails drafted: {len(chase_emails)}")
        if final_report:
            print(f"  Cash in:  RM {final_report.get('cash_in', 0):,.2f}")
            print(f"  Cash out: RM {final_report.get('cash_out', 0):,.2f}")
            print(f"  Net cash: RM {final_report.get('net_cash', 0):,.2f}")

        set_phase("Secretary", "done")
        emit("Secretary", "done", f"{len(tasks)} tasks, {len(chase_emails)} draft emails")
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
                "verification": verification,
            },
            "gmail": {
                "status": gmail["status"],
                "emails": gmail["emails"],
                "document_count": len(gmail_records),
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
                "chase_targets": targets,
                "observations": observations,
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
    # test-documents/extracted/ holds the 4 full-page scans the per-document crops
    # were cut from; reading both would double every document
    return sorted(p for p in images if "extracted" not in p.relative_to(TEST_DOCS_DIR).parts)


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
        # Every document in the test set is a purchase, so there is no cash in to report
        lines.append("  CASH FLOW SUMMARY" if final_report.get("cash_in") else
                     "  PAYABLES CLOSE (every document is a purchase; no sales documents, so cash in is RM 0)")
        lines.append(f"    Cash In:   RM {final_report.get('cash_in', 0):,.2f}")
        lines.append(f"    Cash Out:  RM {final_report.get('cash_out', 0):,.2f}")
        lines.append(f"    Net Cash:  RM {final_report.get('net_cash', 0):,.2f}")

        for note in final_report.get("observations", []):
            lines.append(f"    Note: {note}")

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

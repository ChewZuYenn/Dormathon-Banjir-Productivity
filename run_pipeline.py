#!/usr/bin/env python
"""
Banjir Productivity — Full Month-End Pipeline
=============================================

Runs all three agents in sequence from a single command:

    Logistics (extract)  ->  Financial (validate)  ->  Secretary (plan, tasks, report)

No WorkBuddy required. Clone, install, run.

Usage:
    python run_pipeline.py                              # Full pipeline with test docs
    python run_pipeline.py --goal "Close out September" # Custom goal
    python run_pipeline.py --json                        # JSON output
    python run_pipeline.py --output result.json          # Save to file
    python run_pipeline.py --skip-logistics              # Reuse existing output.json
    python run_pipeline.py --help                        # Full options

Requirements:
    pip install pydantic>=2.0.0

What it does:
    1. Logistics:    Extracts 36 test documents -> agents/logistics/output.json
    2. Financial:    Validates arithmetic, SST, duplicates -> ledger.json + exceptions.json
    3. Converter:    Converts Financial exceptions to Secretary ExceptionEvents
    4. Secretary:    Generates plan, tasks, chase emails, final report

Output:
    Formatted text (default) or JSON (--json flag)
    Also saves full JSON to agents/logistics/secretary_result.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
AGENTS_DIR = PROJECT_ROOT / "agents"
LOGISTICS_DIR = AGENTS_DIR / "logistics"
FINANCIAL_DIR = AGENTS_DIR / "financial"
SECRETARY_DIR = AGENTS_DIR / "secretary"

PYTHON = sys.executable

# Add Secretary to path for imports
sys.path.insert(0, str(SECRETARY_DIR))


# ---------------------------------------------------------------------------
# Step 1: Logistics
# ---------------------------------------------------------------------------

def run_logistics() -> str:
    """Run the Logistics pipeline to extract documents.

    Returns:
        Path to output.json
    """
    print("\n" + "=" * 60)
    print("  STEP 1/4: LOGISTICS AGENT")
    print("  Extracting documents...")
    print("=" * 60)

    script = LOGISTICS_DIR / "process_test_docs.py"
    output_file = LOGISTICS_DIR / "output.json"

    result = subprocess.run(
        [PYTHON, str(script)],
        cwd=str(LOGISTICS_DIR),
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        print(f"  ERROR: Logistics failed (exit {result.returncode})")
        print(result.stderr[-500:])
        sys.exit(1)

    # Print last 10 lines of output
    lines = result.stdout.strip().split("\n")
    for line in lines[-15:]:
        print(f"  {line}")

    print(f"\n  Output: {output_file}")
    return str(output_file)


# ---------------------------------------------------------------------------
# Step 2: Financial
# ---------------------------------------------------------------------------

def run_financial(logistics_output: str) -> tuple[str, str]:
    """Run the Financial engine against Logistics output.

    Returns:
        (ledger_path, exceptions_path)
    """
    print("\n" + "=" * 60)
    print("  STEP 2/4: FINANCIAL AGENT")
    print("  Validating arithmetic, SST, duplicates...")
    print("=" * 60)

    engine = FINANCIAL_DIR / "engine.py"
    result = subprocess.run(
        [PYTHON, str(engine), logistics_output],
        cwd=str(FINANCIAL_DIR),
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        print(f"  ERROR: Financial failed (exit {result.returncode})")
        print(result.stderr[-500:])
        sys.exit(1)

    lines = result.stdout.strip().split("\n")
    for line in lines[-20:]:
        print(f"  {line}")

    # Financial writes outputs next to the input file
    logistics_dir = Path(logistics_output).parent
    ledger_path = str(logistics_dir / "ledger.json")
    exceptions_path = str(logistics_dir / "exceptions.json")

    return ledger_path, exceptions_path


# ---------------------------------------------------------------------------
# Step 3: Convert Financial exceptions -> Secretary ExceptionEvents
# ---------------------------------------------------------------------------

def convert_exceptions(exceptions_path: str, logistics_output: str) -> list:
    """Convert Financial engine exceptions to Secretary ExceptionEvent objects.

    Financial outputs exceptions with `type`, `details` (may be dict), `severity`.
    Secretary expects `event_type` (enum), `details` (string), plus amount/vendor lookup.

    Mapping:
        duplicate_*             -> DUPLICATE
        missing_po_reference_*  -> ESCALATION (MISSING_PO)
        tax_rate_*               -> ESCALATION (TAX_RATE_ANOMALY)
        arithmetic_*             -> ESCALATION (ARITHMETIC_MISMATCH)
        conflicting_*            -> ESCALATION (CONFLICTING_VALUES)
        quantity_*               -> FLAGGED
        low_confidence           -> FLAGGED (with confidence)
        no_due_date              -> FLAGGED
        missing_po_match         -> FLAGGED
        overdue                  -> OVERDUE
        * (fallback)             -> FLAGGED
    """
    from src.models import ExceptionEvent, EventType

    # Load Financial exceptions
    with open(exceptions_path, "r", encoding="utf-8") as f:
        fin_data = json.load(f)
    fin_exceptions = fin_data.get("exceptions", fin_data) if isinstance(fin_data, dict) else fin_data

    # Load Logistics records for amount/vendor lookup
    with open(logistics_output, "r", encoding="utf-8") as f:
        logistics_records = json.load(f)

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

    def convert(fin_exc):
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

        # Map Financial types to Secretary event types
        if "duplicate" in exc_type:
            return ExceptionEvent(
                event_type=EventType.DUPLICATE,
                invoice_number=doc_num, vendor_name=vendor, amount=amount,
                invoice_date=invoice_date, details=details,
                duplicate_of=safe_str(fin_exc.get("details", "")),
            )
        elif "missing_po_reference" in exc_type:
            return ExceptionEvent(
                event_type=EventType.ESCALATION,
                invoice_number=doc_num, vendor_name=vendor, amount=amount,
                invoice_date=invoice_date, details=details,
                escalation_reason=reason, escalation_code="MISSING_PO",
            )
        elif "tax_rate" in exc_type or "arithmetic" in exc_type or "conflicting" in exc_type:
            return ExceptionEvent(
                event_type=EventType.ESCALATION,
                invoice_number=doc_num, vendor_name=vendor, amount=amount,
                invoice_date=invoice_date, details=details,
                escalation_reason=reason, escalation_code=exc_type.upper(),
            )
        elif "overdue" in exc_type:
            return ExceptionEvent(
                event_type=EventType.OVERDUE,
                invoice_number=doc_num, vendor_name=vendor, amount=amount,
                invoice_date=invoice_date, due_date=due_date, details=details,
            )
        elif "low_confidence" in exc_type:
            return ExceptionEvent(
                event_type=EventType.FLAGGED,
                invoice_number=doc_num, vendor_name=vendor, amount=amount,
                invoice_date=invoice_date, details=details,
                flag_reason="Low OCR confidence",
                confidence=confidence,
            )
        else:
            return ExceptionEvent(
                event_type=EventType.FLAGGED,
                invoice_number=doc_num, vendor_name=vendor, amount=amount,
                invoice_date=invoice_date, details=details,
                flag_reason=reason, confidence=confidence,
            )

    events = []
    for fin_exc in fin_exceptions:
        try:
            events.append(convert(fin_exc))
        except Exception as e:
            print(f"  SKIP: {fin_exc.get('type', '?')} on {fin_exc.get('document_number', '?')}: {e}")

    type_counts = {
        "overdue": sum(1 for e in events if e.event_type == EventType.OVERDUE),
        "duplicate": sum(1 for e in events if e.event_type == EventType.DUPLICATE),
        "escalation": sum(1 for e in events if e.event_type == EventType.ESCALATION),
        "flagged": sum(1 for e in events if e.event_type == EventType.FLAGGED),
    }
    print(f"\n  Converted {len(events)}/{len(fin_exceptions)} exceptions")
    print(f"  By type: {type_counts}")

    return events


def load_documents(logistics_output: str) -> list:
    """Load Logistics records as Secretary DocumentInfo objects."""
    from src.models import DocumentInfo

    with open(logistics_output, "r", encoding="utf-8") as f:
        records = json.load(f)

    documents = []
    for rec in records:
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

    return documents


# ---------------------------------------------------------------------------
# Step 4: Secretary
# ---------------------------------------------------------------------------

def run_secretary(goal: str, events: list, documents: list) -> object:
    """Run the Secretary pipeline with converted exceptions and documents."""
    from src.secretary import Secretary

    print("\n" + "=" * 60)
    print("  STEP 4/4: SECRETARY AGENT")
    print("  Generating plan, tasks, chase emails, final report...")
    print("=" * 60)

    secretary = Secretary()
    result = secretary.run(
        goal=goal,
        exceptions=events,
        documents=documents,
    )

    return secretary, result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Banjir Productivity — Full Month-End Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py                                    # Full pipeline
  python run_pipeline.py --goal "Close out September"       # Custom goal
  python run_pipeline.py --json                             # JSON output
  python run_pipeline.py --skip-logistics                   # Reuse existing output
  python run_pipeline.py --output result.json --json        # Save JSON
        """,
    )

    parser.add_argument(
        "--goal", type=str, default="Close out September",
        help="Business goal for the run (default: 'Close out September')",
    )
    parser.add_argument(
        "--skip-logistics", action="store_true",
        help="Skip Logistics, reuse existing agents/logistics/output.json",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON instead of formatted text",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Write output to a file",
    )
    parser.add_argument(
        "--auto-approve", action="store_true",
        help="Auto-approve chase emails (TESTING ONLY)",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  BANJIR PRODUCTIVITY — FULL PIPELINE")
    print(f"  Goal: {args.goal}")
    print("=" * 60)

    # Step 1: Logistics
    logistics_output = str(LOGISTICS_DIR / "output.json")
    if args.skip_logistics and os.path.exists(logistics_output):
        print(f"\n  Skipping Logistics — using existing {logistics_output}")
    else:
        logistics_output = run_logistics()

    # Step 2: Financial
    print("\n  STEP 3/4: CONVERTING EXCEPTIONS...")
    ledger_path, exceptions_path = run_financial(logistics_output)

    # Step 3: Convert
    print("\n" + "=" * 60)
    print("  STEP 3/4: CONVERTING EXCEPTIONS...")
    print("=" * 60)
    events = convert_exceptions(exceptions_path, logistics_output)
    documents = load_documents(logistics_output)
    print(f"  Loaded {len(documents)} documents from Logistics")

    # Step 4: Secretary
    secretary, result = run_secretary(args.goal, events, documents)

    # Output
    if args.json:
        output = secretary.result_to_json(result)
    else:
        output = secretary.format_result(result)

    # Always save JSON
    json_output = secretary.result_to_json(result)
    default_save = str(LOGISTICS_DIR / "secretary_result.json")
    with open(default_save, "w", encoding="utf-8") as f:
        f.write(json_output)

    # Print
    print()
    print(output)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  PIPELINE COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Logistics:  {len(documents)} documents extracted")
    print(f"  Financial:  {len(events)} exceptions, ledger saved")
    print(f"  Secretary:  {len(result.tasks)} tasks, {len(result.chase_emails)} chase emails")
    print(f"  Report:     Cash in RM {result.final_report.cash_in:.2f}, "
          f"Cash out RM {result.final_report.cash_out:.2f}, "
          f"Net RM {result.final_report.net_cash:.2f}")
    print(f"  JSON saved: {default_save}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_output)
        print(f"  Also saved: {args.output}")


if __name__ == "__main__":
    main()

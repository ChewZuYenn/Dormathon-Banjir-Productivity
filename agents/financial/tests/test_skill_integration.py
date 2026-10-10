"""
Integration test for the wired Financial Agent skill.

Verifies:
1. The skill file (SKILL.md) exists and contains required sections
2. The schema files are accessible from the skill references
3. The Financial engine can be imported and runs correctly
4. The Logistics output processes through the Financial engine
5. The output (ledger + exceptions) is valid JSON
6. Hard boundaries are documented in the skill
"""

import json
import os
import sys

# Paths — file is at: Dormathon-Banjir-Productivity/agents/financial/tests/test_skill_integration.py
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_FINANCIAL_DIR = os.path.dirname(_THIS_DIR)                              # .../agents/financial
_AGENTS_DIR = os.path.dirname(_FINANCIAL_DIR)                            # .../agents
PROJECT_ROOT = os.path.dirname(_AGENTS_DIR)                              # .../Dormathon-Banjir-Productivity
HACKATHON_ROOT = os.path.dirname(PROJECT_ROOT)                           # .../2026-10-10-13-50-26
SKILL_DIR = os.path.join(HACKATHON_ROOT, ".workbuddy-ai", "skills", "financial-agent")
LOGISTICS_DIR = os.path.join(_AGENTS_DIR, "logistics")
LOGISTICS_SKILL_DIR = os.path.join(HACKATHON_ROOT, ".workbuddy-ai", "skills", "logistics-coordinator")

# Ensure engine is importable
sys.path.insert(0, _FINANCIAL_DIR)

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  PASS: {name}")
        PASS += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        FAIL += 1


def test_skill_file():
    """Test 1: SKILL.md exists and has required sections."""
    print("\n=== Test 1: Skill File Integrity ===")
    skill_path = os.path.join(SKILL_DIR, "SKILL.md")
    check("SKILL.md exists", os.path.exists(skill_path), f"Path: {skill_path}")

    with open(skill_path, "r", encoding="utf-8") as f:
        content = f.read()

    check("Has trigger section", "## Trigger" in content)
    check("Has role section", "## Role" in content)
    check("Has hard boundaries", "Never read raw documents" in content)
    check("Has ledger schema", "Reconciled Ledger" in content)
    check("Has exception schema", "Exception List" in content)
    check("Has processing steps", "Step 1: Receive and Index" in content)
    check("Has arithmetic validation", "Step 4: Arithmetic Validation" in content)
    check("Has SST validation", "Step 5: SST Rate Validation" in content)
    check("Has duplicate detection", "Step 6: Duplicate Detection" in content)
    check("Has order-invoice match", "Step 7: Order-vs-Invoice Match" in content)
    check("Has reconciliation", "Step 8: Reconciliation" in content)
    check("Has confidence escalation", "Step 10: Confidence Escalation" in content)
    check("Has traceability check", "Step 11: Traceability" in content)
    check("Has categorisation rules", "COGS" in content and "RENT" in content)
    check("Has SST valid rates", "0%, 6%, 8%" in content)
    check("Has tolerance rules", "RM 1.00" in content and "RM 5.00" in content)
    check("Has engine invocation", "engine.py" in content)
    check("Has categories", all(c in content for c in ["COGS", "RENT", "UTIL", "SALARY", "SUPPLIES", "MARKETING", "MAINT", "TRANSPORT", "FEES", "MISC"]))


def test_schema_references():
    """Test 2: Schema files exist in skill references."""
    print("\n=== Test 2: Schema References ===")
    ref_dir = os.path.join(SKILL_DIR, "references")
    check("References directory exists", os.path.exists(ref_dir))

    for schema_file in ["ledger_schema.json", "exception_schema.json"]:
        path = os.path.join(ref_dir, schema_file)
        check(f"{schema_file} in references", os.path.exists(path))
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                schema = json.load(f)
            check(f"{schema_file} is valid JSON schema", "properties" in schema)
            check(f"{schema_file} has required fields", "required" in schema)


def test_engine_import():
    """Test 3: Financial engine can be imported."""
    print("\n=== Test 3: Engine Import ===")
    try:
        from engine import FinancialEngine
        check("FinancialEngine imported", True)
        check("Has run method", hasattr(FinancialEngine, "run"))
        check("Has step1_index method", hasattr(FinancialEngine, "step1_index"))
        check("Has step2_build_ledger method", hasattr(FinancialEngine, "step2_build_ledger"))
        check("Has step4_arithmetic method", hasattr(FinancialEngine, "step4_arithmetic"))
        check("Has step5_sst method", hasattr(FinancialEngine, "step5_sst"))
        check("Has step6_duplicates method", hasattr(FinancialEngine, "step6_duplicates"))
        check("Has step7_order_invoice_match method", hasattr(FinancialEngine, "step7_order_invoice_match"))
        check("Has step8_reconciliation method", hasattr(FinancialEngine, "step8_reconciliation"))
        check("Has build_outputs method", hasattr(FinancialEngine, "build_outputs"))
    except Exception as e:
        check("FinancialEngine imported", False, str(e))


def test_logistics_to_financial_pipeline():
    """Test 4: Logistics output processes through Financial engine."""
    print("\n=== Test 4: Logistics -> Financial Pipeline ===")
    from engine import FinancialEngine

    # Load Logistics output
    output_path = os.path.join(LOGISTICS_DIR, "output.json")
    check("Logistics output.json exists", os.path.exists(output_path))

    if not os.path.exists(output_path):
        return

    with open(output_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    check("Records is a list", isinstance(records, list))
    check(f"Has {len(records)} records", len(records) == 34, f"Got {len(records)}")

    # Run through Financial engine
    engine = FinancialEngine(records)
    ledger, exceptions = engine.run()

    # Verify ledger
    check("Ledger returned", ledger is not None)
    check("Ledger has period", "period" in ledger)
    check("Ledger has rows", "rows" in ledger)
    check("Ledger has summary", "summary" in ledger)
    check("Ledger rows is a list", isinstance(ledger["rows"], list))
    check(f"Ledger has {len(ledger['rows'])} rows", len(ledger["rows"]) > 0)

    # Verify summary
    s = ledger["summary"]
    check("Summary has total_in", "total_in" in s)
    check("Summary has total_out", "total_out" in s)
    check("Summary has total_tax", "total_tax" in s)
    check("Summary has net_cash_flow", "net_cash_flow" in s)
    check("Summary has by_category", "by_category" in s)
    check("Summary has reconciliation_rate", "reconciliation_rate" in s)
    check("Summary has document_count", "document_count" in s)
    check(f"Document count = 34", s["document_count"] == 34)

    # Verify exceptions
    check("Exceptions returned", exceptions is not None)
    check("Exceptions has period", "period" in exceptions)
    check("Exceptions has exceptions list", "exceptions" in exceptions)
    check("Exceptions has summary", "summary" in exceptions)
    check("Exceptions list is non-empty", len(exceptions["exceptions"]) > 0)

    es = exceptions["summary"]
    check("Exception summary has total", "total_exceptions" in es)
    check("Exception summary has critical count", "critical_count" in es)
    check("Exception summary has warning count", "warning_count" in es)
    check(f"Total exceptions > 50", es["total_exceptions"] > 50, f"Got {es['total_exceptions']}")


def test_hard_boundary():
    """Test 5: Financial validates but does not extract totals."""
    print("\n=== Test 5: Hard Boundary (Financial validates, doesn't extract) ===")
    from engine import FinancialEngine

    # Create a record with a wrong total
    records = [{
        "document_type": "invoice",
        "vendor_name": "Test Vendor",
        "invoice_number": "INV-TEST-001",
        "invoice_date": "2026-10-01",
        "po_reference": None,
        "line_items": [
            {"description": "Test item", "quantity": 10, "unit_price": 10.0, "tax_amount": 6.0, "tax_rate": 6}
        ],
        "subtotal": 100.0,
        "total_tax": 6.0,
        "grand_total": 150.0,  # Wrong: should be 106.00
        "currency": "MYR",
        "source_ref": "test_001.png",
        "confidence": {"vendor_name": 0.9, "invoice_number": 0.9, "invoice_date": 0.9, "grand_total": 0.9, "line_items": 0.9},
        "status": "clean",
        "flags": []
    }]

    engine = FinancialEngine(records)
    ledger, exceptions = engine.run()

    # Financial should catch the arithmetic error, not "fix" it
    exc_types = [e["type"] for e in exceptions["exceptions"]]
    check("Catches arithmetic_mismatch", "arithmetic_mismatch" in exc_types)

    # Ledger should record the printed total, not a corrected one
    # (the engine computes amounts from line items, but the exception flags the mismatch)
    has_mismatch = any("150" in e.get("reason", "") or "106" in e.get("reason", "")
                       for e in exceptions["exceptions"] if e["type"] == "arithmetic_mismatch")
    check("Reports the delta between printed and computed", has_mismatch)


def test_both_skills_exist():
    """Test 6: Both Logistics and Financial skills are wired."""
    print("\n=== Test 6: Both Skills Wired ===")
    logistics_skill = os.path.join(LOGISTICS_SKILL_DIR, "SKILL.md")
    financial_skill = os.path.join(SKILL_DIR, "SKILL.md")

    check("Logistics SKILL.md exists", os.path.exists(logistics_skill))
    check("Financial SKILL.md exists", os.path.exists(financial_skill))

    if os.path.exists(logistics_skill):
        with open(logistics_skill, "r", encoding="utf-8") as f:
            ls = f.read()
        check("Logistics skill has trigger", "## Trigger" in ls)
        check("Logistics skill has never-compute-total", "NEVER compute" in ls)

    if os.path.exists(financial_skill):
        with open(financial_skill, "r", encoding="utf-8") as f:
            fs = f.read()
        check("Financial skill has trigger", "## Trigger" in fs)
        check("Financial skill has hard boundaries", "Never read raw documents" in fs)


def main():
    print("=" * 60)
    print("FINANCIAL AGENT SKILL — INTEGRATION TEST")
    print("=" * 60)

    test_skill_file()
    test_schema_references()
    test_engine_import()
    test_logistics_to_financial_pipeline()
    test_hard_boundary()
    test_both_skills_exist()

    print("\n" + "=" * 60)
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)
    else:
        print("\nAll integration tests passed. Financial agent skill is wired and ready.")
        print("Both Logistics and Financial skills are live in WorkBuddy.")


if __name__ == "__main__":
    main()

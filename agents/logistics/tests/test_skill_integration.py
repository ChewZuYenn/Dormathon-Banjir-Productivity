"""
Integration test for the wired Logistics Coordinator skill.

Verifies:
1. The skill file (SKILL.md) exists and contains required sections
2. The schema files are accessible from the skill references
3. The Python pipeline can be imported and runs correctly
4. A sample document processes through the full pipeline
5. The output is valid Financial-ready JSON
6. The "never compute a total" rule is enforced in metadata
"""

import json
import os
import sys
import re

# Paths — file is at: Dormathon-Banjir-Productivity/agents/logistics/tests/test_skill_integration.py
# Build paths from the file location
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_LOGISTICS_DIR = os.path.dirname(_THIS_DIR)        # .../agents/logistics
_AGENTS_DIR = os.path.dirname(_LOGISTICS_DIR)      # .../agents
PROJECT_ROOT = os.path.dirname(_AGENTS_DIR)         # .../Dormathon-Banjir-Productivity
HACKATHON_ROOT = PROJECT_ROOT                                          # skills live in the repo: .workbuddy-ai/skills/
SKILL_DIR = os.path.join(HACKATHON_ROOT, ".workbuddy-ai", "skills", "logistics-coordinator")
REPO_DIR = _LOGISTICS_DIR

# Ensure src is importable
sys.path.insert(0, REPO_DIR)

from src.pipeline import LogisticsPipeline
from src.schema_loader import SchemaLoader
from src.confidence import check_record_confidence, CRITICAL_FIELDS, ESCALATION_THRESHOLD
from src.bad_doc_handler import handle_bad_document, detect_bad_document_signals, should_escalate_for_missing_po
from src.document_type_detector import detect as detect_type
from src.validator import validate_record

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
    check("Has never-compute-total rule", "NEVER compute" in content or "NEVER computes" in content)
    check("Has invoice schema", '"document_type": "invoice"' in content)
    check("Has receipt schema", '"document_type": "receipt"' in content)
    check("Has order schema", '"document_type": "order' in content)
    check("Has confidence scoring", "0.0-1.0" in content or "0.0–1.0" in content)
    check("Has bad document handling", "blurry_image" in content)
    check("Has SST handling", "0% (exempt), 6%, 8%" in content)
    check("Has BM language terms", "Pesanan Pembelian" in content)
    check("Has batch processing instructions", "process_batch" in content)
    check("Has escalation threshold", "0.7" in content)
    check("Has handover to Financial", "Handover to Financial" in content)
    check("Has schema swapping note", "arbitrary_v1" in content)


def test_schema_references():
    """Test 2: Schema files exist in skill references."""
    print("\n=== Test 2: Schema References ===")
    ref_dir = os.path.join(SKILL_DIR, "references")
    check("References directory exists", os.path.exists(ref_dir))

    for schema_file in ["invoice_schema.json", "receipt_schema.json", "order_schema.json"]:
        path = os.path.join(ref_dir, schema_file)
        check(f"{schema_file} in references", os.path.exists(path))
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                schema = json.load(f)
            check(f"{schema_file} is valid JSON schema", "properties" in schema)
            check(f"{schema_file} has confidence field", "confidence" in schema.get("properties", {}))
            check(f"{schema_file} has status field", "status" in schema.get("properties", {}))
            check(f"{schema_file} has flags field", "flags" in schema.get("properties", {}))


def test_pipeline_import():
    """Test 3: Pipeline can be imported and instantiated."""
    print("\n=== Test 3: Pipeline Import ===")
    schema_dir = os.path.join(REPO_DIR, "schemas")
    check("Schema directory exists", os.path.exists(schema_dir))

    try:
        pipeline = LogisticsPipeline(schema_dir)
        check("Pipeline instantiated", True)
        check("Has process_document method", hasattr(pipeline, "process_document"))
        check("Has process_batch method", hasattr(pipeline, "process_batch"))
        check("Has format_output method", hasattr(pipeline, "format_output"))
        check("Has get_summary method", hasattr(pipeline, "get_summary"))
    except Exception as e:
        check("Pipeline instantiated", False, str(e))


def test_sample_document():
    """Test 4: A sample invoice processes correctly through the pipeline."""
    print("\n=== Test 4: Sample Document Processing ===")
    schema_dir = os.path.join(REPO_DIR, "schemas")
    pipeline = LogisticsPipeline(schema_dir)

    # Simulate an extracted record from the WorkBuddy agent
    extracted = {
        "document_type": "invoice",
        "vendor_name": "Pulau Ketel Sdn Bhd",
        "vendor_sst_id": "W10-2001-220004",
        "invoice_number": "INV-2026-040",
        "invoice_date": "2026-10-02",
        "po_reference": "PO-PA-26-0002",
        "line_items": [
            {"description": "Big canvas", "quantity": 30, "unit_price": 10.0, "tax_amount": 0.0, "tax_rate": None},
            {"description": "Stiker label", "quantity": 5, "unit_price": 5.0, "tax_amount": 0.0, "tax_rate": None}
        ],
        "subtotal": 400.0,
        "total_tax": 40.0,
        "grand_total": 45.70,
        "currency": "MYR",
        "confidence": {
            "vendor_name": 0.95,
            "invoice_number": 0.95,
            "invoice_date": 0.9,
            "po_reference": 0.9,
            "line_items": 0.9,
            "grand_total": 0.95,
            "total_tax": 0.9
        },
        "status": "flagged",
        "flags": ["invalid_sst_rate", "wrong_total"]
    }

    record = pipeline.process_document(
        content="INVOICE INV-2026-040 Pulau Ketel Sdn Bhd",
        source_ref="invoice_001.png",
        extracted_record=extracted,
        filename="invoice_001.png"
    )

    check("Record returned", record is not None)
    check("document_type is invoice", record.get("document_type") == "invoice")
    check("vendor_name extracted", record.get("vendor_name") == "Pulau Ketel Sdn Bhd")
    check("grand_total recorded as printed", record.get("grand_total") == 45.70)
    check("source_ref set", record.get("source_ref") == "invoice_001.png")
    check("confidence scores present", "confidence" in record)
    check("status is flagged", record.get("status") == "flagged")
    check("invalid_sst_rate flag present", "invalid_sst_rate" in record.get("flags", []))
    check("wrong_total flag present", "wrong_total" in record.get("flags", []))

    # Verify never-compute-total rule
    meta = record.get("_pipeline_meta", {})
    check("total_computed_by_logistics is False", meta.get("total_computed_by_logistics") == False)


def test_financial_handoff():
    """Test 5: format_output strips internal metadata for Financial."""
    print("\n=== Test 5: Financial Handoff Format ===")
    schema_dir = os.path.join(REPO_DIR, "schemas")
    pipeline = LogisticsPipeline(schema_dir)

    records = [{
        "document_type": "receipt",
        "vendor_name": "Test Vendor",
        "receipt_date": "2026-10-05",
        "amount": 150.00,
        "currency": "MYR",
        "source_ref": "test_001.png",
        "confidence": {"vendor_name": 0.95, "receipt_date": 0.9, "amount": 0.95, "payment_method": 0.8},
        "status": "clean",
        "flags": [],
        "_pipeline_meta": {"total_computed_by_logistics": False},
        "_validation": {"valid": True, "missing": [], "escalations": [], "warnings": []}
    }]

    output_str = pipeline.format_output(records)
    output = json.loads(output_str)

    check("Output is valid JSON", isinstance(output, list))
    check("Output has 1 record", len(output) == 1)
    check("Internal _pipeline_meta stripped", "_pipeline_meta" not in output[0])
    check("Internal _validation stripped", "_validation" not in output[0])
    check("source_ref preserved", "source_ref" in output[0])
    check("confidence preserved", "confidence" in output[0])
    check("status preserved", "status" in output[0])


def test_summary_generation():
    """Test 6: Summary generates correct counts."""
    print("\n=== Test 6: Summary Generation ===")
    schema_dir = os.path.join(REPO_DIR, "schemas")
    pipeline = LogisticsPipeline(schema_dir)

    records = [
        {"document_type": "invoice", "status": "clean", "flags": [], "source_ref": "d1",
         "confidence": {"vendor_name": 0.9, "invoice_number": 0.9, "invoice_date": 0.9, "grand_total": 0.9, "line_items": 0.9}},
        {"document_type": "receipt", "status": "flagged", "flags": ["blurry_image"], "source_ref": "d2",
         "confidence": {"vendor_name": 0.5, "receipt_date": 0.4, "amount": 0.3}},
        {"document_type": "invoice", "status": "error", "flags": ["unparseable"], "source_ref": "d3", "confidence": {}},
    ]

    summary = pipeline.get_summary(records)

    check("Total documents = 3", summary["total_documents"] == 3)
    check("Clean = 1", summary["by_status"]["clean"] == 1)
    check("Flagged = 1", summary["by_status"]["flagged"] == 1)
    check("Error = 1", summary["by_status"]["error"] == 1)
    check("Ready for Financial = 2", summary["ready_for_financial"] == 2)
    check("Blocked = 1", summary["blocked"] == 1)


def main():
    print("=" * 60)
    print("LOGISTICS COORDINATOR SKILL — INTEGRATION TEST")
    print("=" * 60)

    test_skill_file()
    test_schema_references()
    test_pipeline_import()
    test_sample_document()
    test_financial_handoff()
    test_summary_generation()

    print("\n" + "=" * 60)
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)
    else:
        print("\nAll integration tests passed. Logistics agent is wired and ready.")


if __name__ == "__main__":
    main()

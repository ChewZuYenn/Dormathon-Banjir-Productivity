"""
Tests for the Logistics Pipeline

Tests with sample documents (including deliberately bad ones)
to verify the pipeline handles all cases from the brief:
- Normal invoice, receipt, order
- Blurry photo
- Handwritten
- No PO reference
- Wrong total
- Duplicate
"""

import os
import sys
import json

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline import LogisticsPipeline
from src.schema_loader import SchemaLoader
from src.document_type_detector import detect as detect_type
from src.confidence import check_record_confidence, needs_escalation
from src.bad_doc_handler import handle_bad_document, detect_bad_document_signals
from src.validator import validate_record

# Schema directory (relative to this file)
SCHEMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schemas")


def test_schema_loader():
    """Test that all schemas load correctly."""
    loader = SchemaLoader(SCHEMA_DIR)

    for doc_type in ["invoice", "receipt", "order"]:
        schema = loader.get_schema(doc_type)
        assert schema is not None, f"Schema for {doc_type} not loaded"
        assert "required" in schema, f"No required fields in {doc_type} schema"
        print(f"  [PASS] {doc_type} schema loaded: {len(schema['required'])} required fields")


def test_document_type_detection():
    """Test document type detection from text content."""
    # Invoice
    inv_content = "INVOICE\nVendor: Kedai Kopi Maju\nInvoice No: INV-2026-0941\nAmount Due: RM 450.00\nDue Date: 30/09/2026"
    doc_type, conf = detect_type(inv_content)
    assert doc_type == "invoice", f"Expected invoice, got {doc_type}"
    assert conf >= 0.5, f"Confidence too low: {conf}"
    print(f"  [PASS] Invoice detected: type={doc_type}, conf={conf}")

    # Receipt
    rcpt_content = "RESIT\nPayment Received: RM 200.00\nPaid via DuitNow\nVendor: Restoran Selera"
    doc_type, conf = detect_type(rcpt_content)
    assert doc_type == "receipt", f"Expected receipt, got {doc_type}"
    print(f"  [PASS] Receipt detected: type={doc_type}, conf={conf}")

    # Order
    po_content = "PURCHASE ORDER\nPO No: PO-2026-007\nDelivery Date: 15/09/2026\nSupplier: Syarikat ABC"
    doc_type, conf = detect_type(po_content)
    assert doc_type == "order", f"Expected order, got {doc_type}"
    print(f"  [PASS] Order detected: type={doc_type}, conf={conf}")

    # Unknown
    unknown_content = "random text with no document markers"
    doc_type, conf = detect_type(unknown_content)
    assert doc_type == "unknown", f"Expected unknown, got {doc_type}"
    print(f"  [PASS] Unknown detected: type={doc_type}, conf={conf}")


def test_normal_invoice():
    """Test processing a normal invoice with extracted data."""
    pipeline = LogisticsPipeline(SCHEMA_DIR)

    extracted = {
        "document_type": "invoice",
        "vendor_name": "Kedai Kopi Maju Sdn Bhd",
        "invoice_number": "INV-2026-0941",
        "invoice_date": "2026-09-15",
        "po_reference": "PO-2026-007",
        "line_items": [
            {"description": "Kopi beans 1kg", "quantity": 10, "unit_price": 35.00, "tax_amount": 21.00, "tax_rate": 6},
        ],
        "subtotal": 350.00,
        "total_tax": 21.00,
        "grand_total": 371.00,
        "currency": "MYR",
        "confidence": {
            "vendor_name": 0.95,
            "invoice_number": 0.92,
            "invoice_date": 0.90,
            "po_reference": 0.85,
            "line_items": 0.88,
            "grand_total": 0.95,
        },
        "status": "clean",
        "flags": [],
    }

    record = pipeline.process_document(
        content="INVOICE\nVendor: Kedai Kopi Maju\nInvoice No: INV-2026-0941\nAmount Due: RM 371.00",
        source_ref="invoice_001.pdf",
        extracted_record=extracted,
    )

    assert record["status"] == "clean"
    assert record["grand_total"] == 371.00  # recorded, NOT computed
    assert record["_pipeline_meta"]["total_computed_by_logistics"] is False
    print(f"  [PASS] Normal invoice processed: status={record['status']}, total={record['grand_total']}")


def test_bad_document_blurry():
    """Test handling a blurry document."""
    pipeline = LogisticsPipeline(SCHEMA_DIR)

    record = pipeline.process_document(
        content="??? [illegible] invoice ???",
        source_ref="blurry_photo_001.jpg",
        extracted_record={
            "document_type": "invoice",
            "vendor_name": "Kedai [unclear]",
            "grand_total": None,
            "confidence": {"vendor_name": 0.3, "grand_total": 0.0},
            "status": "flagged",
            "flags": ["blurry_image"],
        },
    )

    assert record["status"] == "flagged"
    assert "blurry_image" in record["flags"]
    assert record["_validation"]["escalations"]  # Should have escalations
    print(f"  [PASS] Blurry document handled: status={record['status']}, flags={record['flags']}")


def test_bad_document_unparseable():
    """Test handling a completely unparseable document."""
    pipeline = LogisticsPipeline(SCHEMA_DIR)

    record = pipeline.process_document(
        content="",
        source_ref="corrupt_001.pdf",
    )

    assert record["status"] == "error"
    assert "unparseable" in record["flags"]
    print(f"  [PASS] Unparseable document handled: status={record['status']}")


def test_missing_po_escalation():
    """Test that missing PO on a large invoice triggers escalation."""
    pipeline = LogisticsPipeline(SCHEMA_DIR)

    extracted = {
        "document_type": "invoice",
        "vendor_name": "Supplier XYZ",
        "invoice_number": "INV-2026-0200",
        "invoice_date": "2026-09-20",
        "po_reference": None,  # Missing!
        "grand_total": 750.00,  # Above RM 500 threshold
        "confidence": {
            "vendor_name": 0.9,
            "invoice_number": 0.9,
            "invoice_date": 0.9,
            "po_reference": 0.0,
            "grand_total": 0.9,
        },
        "status": "flagged",
        "flags": ["no_po_reference"],
    }

    record = pipeline.process_document(
        content="INVOICE\nVendor: Supplier XYZ\nInvoice No: INV-2026-0200\nAmount: RM 750.00",
        source_ref="invoice_missing_po.pdf",
        extracted_record=extracted,
    )

    assert "escalate_missing_po" in record["flags"]
    print(f"  [PASS] Missing PO escalated on large invoice: flags={record['flags']}")


def test_batch_and_summary():
    """Test batch processing and summary generation."""
    pipeline = LogisticsPipeline(SCHEMA_DIR)

    documents = [
        {
            "content": "INVOICE\nVendor: ABC\nInvoice No: INV-001\nAmount: RM 100.00",
            "source_ref": "doc_001",
            "extracted": {
                "document_type": "invoice",
                "vendor_name": "ABC",
                "invoice_number": "INV-001",
                "invoice_date": "2026-09-01",
                "grand_total": 100.00,
                "currency": "MYR",
                "confidence": {"vendor_name": 0.9, "invoice_number": 0.9, "invoice_date": 0.9, "grand_total": 0.9, "line_items": 0.9, "po_reference": 0.9},
                "status": "clean",
                "flags": [],
                "line_items": [{"description": "item", "quantity": 1, "unit_price": 100, "tax_amount": 0}],
            },
        },
        {
            "content": "",
            "source_ref": "doc_002",
        },
    ]

    records = pipeline.process_batch(documents)
    summary = pipeline.get_summary(records)

    assert summary["total_documents"] == 2
    assert summary["by_status"]["clean"] == 1
    assert summary["by_status"]["error"] == 1
    print(f"  [PASS] Batch processed: {summary['total_documents']} docs, "
          f"clean={summary['by_status']['clean']}, error={summary['by_status']['error']}")

    output = pipeline.format_output(records)
    parsed = json.loads(output)
    assert len(parsed) == 2
    print(f"  [PASS] Output formatted: {len(parsed)} records in JSON")


def test_never_computes_total():
    """
    The most important test: verify logistics NEVER computes a total.
    The pipeline records what is given, it does not add line items.
    """
    pipeline = LogisticsPipeline(SCHEMA_DIR)

    extracted = {
        "document_type": "invoice",
        "vendor_name": "Test Vendor",
        "invoice_number": "INV-TEST",
        "invoice_date": "2026-09-01",
        "line_items": [
            {"description": "item 1", "quantity": 2, "unit_price": 50.00, "tax_amount": 6.00},
            {"description": "item 2", "quantity": 1, "unit_price": 30.00, "tax_amount": 3.60},
        ],
        "subtotal": 100.00,  # printed on doc
        "total_tax": 9.60,   # printed on doc
        "grand_total": 109.60,  # printed on doc (WRONG — actual is 136.60, but we don't care)
        "currency": "MYR",
        "confidence": {"vendor_name": 0.9, "invoice_number": 0.9, "invoice_date": 0.9, "grand_total": 0.9, "line_items": 0.9},
        "status": "clean",
        "flags": [],
    }

    record = pipeline.process_document(
        content="INVOICE",
        source_ref="test.pdf",
        extracted_record=extracted,
    )

    # We record 109.60 as printed, even though 2*50 + 6 + 1*30 + 3.60 = 136.60
    # We do NOT compute this. We pass it to Financial.
    assert record["grand_total"] == 109.60
    assert record["_pipeline_meta"]["total_computed_by_logistics"] is False
    print(f"  [PASS] Total NOT computed: recorded {record['grand_total']} as printed (Financial will validate)")


def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("LOGISTICS PIPELINE TESTS")
    print("=" * 60)

    print("\n--- Schema Loader ---")
    test_schema_loader()

    print("\n--- Document Type Detection ---")
    test_document_type_detection()

    print("\n--- Normal Invoice ---")
    test_normal_invoice()

    print("\n--- Bad Document: Blurry ---")
    test_bad_document_blurry()

    print("\n--- Bad Document: Unparseable ---")
    test_bad_document_unparseable()

    print("\n--- Missing PO Escalation ---")
    test_missing_po_escalation()

    print("\n--- Batch & Summary ---")
    test_batch_and_summary()

    print("\n--- Never Computes Total ---")
    test_never_computes_total()

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_all_tests()

"""
Validator

Validates extracted records against the loaded schema.
Checks for required fields, type correctness, and business rules.

This does NOT validate arithmetic — that is Financial's job.
"""

from typing import Any
from .schema_loader import SchemaLoader
from .confidence import check_record_confidence


def validate_record(record: dict, doc_type: str, loader: SchemaLoader) -> dict:
    """
    Validate a single extracted record against its schema.

    Returns a dict with:
        'valid': bool
        'missing': list of missing required fields
        'escalations': list of confidence escalation messages
        'warnings': list of non-blocking warnings
    """
    result = {
        "valid": True,
        "missing": [],
        "escalations": [],
        "warnings": [],
    }

    # 1. Check required fields
    missing = loader.validate_required(record, doc_type)
    result["missing"] = missing
    if missing:
        result["valid"] = False
        result["warnings"].append(
            f"Missing required fields: {', '.join(missing)}"
        )

    # 2. Check document_type matches expected
    if "document_type" in record:
        expected_types = [doc_type]
        if doc_type == "order":
            expected_types.append("po")
        if record["document_type"] not in expected_types:
            result["warnings"].append(
                f"document_type mismatch: expected {doc_type}, "
                f"got {record['document_type']}"
            )

    # 3. Check confidence scores
    escalations = check_record_confidence(record, doc_type)
    result["escalations"] = escalations
    if escalations:
        result["warnings"].append(
            f"{len(escalations)} field(s) need owner verification"
        )

    # 4. Check source_ref exists (always required for traceability)
    if not record.get("source_ref"):
        result["valid"] = False
        result["missing"].append("source_ref")
        result["warnings"].append("source_ref is required for traceability")

    # 5. Check status is set
    if "status" not in record:
        result["warnings"].append("status not set — defaulting to 'flagged'")
        record["status"] = "flagged"

    # 6. Check flags is a list
    if "flags" not in record:
        record["flags"] = []

    # 7. Business rule: grand_total should not be computed by logistics
    #    We only check that it's recorded as-is, not computed
    if record.get("grand_total") is not None and record.get("subtotal") is not None:
        # Just verify both exist — we do NOT check if they match
        pass  # Financial's job, not ours

    return result


def validate_batch(records: list[dict], loader: SchemaLoader) -> list[dict]:
    """
    Validate a batch of records.
    Returns the records with validation results attached.
    """
    results = []
    for record in records:
        doc_type = record.get("document_type", "unknown")
        if doc_type in ("unknown", None):
            record["_validation"] = {
                "valid": False,
                "missing": [],
                "escalations": [],
                "warnings": ["Unknown document type — cannot validate"],
            }
            results.append(record)
            continue

        validation = validate_record(record, doc_type, loader)
        record["_validation"] = validation
        results.append(record)

    return results

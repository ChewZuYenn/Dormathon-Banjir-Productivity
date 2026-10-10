"""
Confidence Scoring

Assigns and validates confidence scores for extracted fields.
Confidence is 0.0–1.0 and determines whether a field needs escalation.

Escalation rules (from rules/rules.md):
- Any critical field with confidence < 0.7 → flag for owner review
- Handwritten document with OCR confidence < 0.6 → escalate
- Grand total blank or unparseable → escalate
"""

from typing import Any

# Fields that are considered "critical" — low confidence on these escalates
CRITICAL_FIELDS = {
    "invoice": ["vendor_name", "invoice_number", "invoice_date", "grand_total", "line_items"],
    "receipt": ["vendor_name", "receipt_date", "amount"],
    "order": ["po_number", "po_date", "vendor_name", "grand_total", "line_items"],
    "po": ["po_number", "po_date", "vendor_name", "grand_total", "line_items"],
}

# Escalation threshold
ESCALATION_THRESHOLD = 0.7
HANDWRITTEN_THRESHOLD = 0.6


def get_critical_fields(doc_type: str) -> list[str]:
    """Return the list of critical fields for a document type."""
    return CRITICAL_FIELDS.get(doc_type.lower(), [])


def needs_escalation(field: str, confidence: float, doc_type: str,
                     is_handwritten: bool = False) -> bool:
    """Check if a field's confidence is low enough to warrant escalation."""
    critical = get_critical_fields(doc_type)

    if field not in critical:
        return False

    if is_handwritten and confidence < HANDWRITTEN_THRESHOLD:
        return True

    if confidence < ESCALATION_THRESHOLD:
        return True

    return False


def check_record_confidence(record: dict, doc_type: str) -> list[str]:
    """
    Check all critical fields in a record for low confidence.
    Returns a list of escalation messages for fields that need owner review.
    """
    escalations = []
    confidence = record.get("confidence", {})
    flags = record.get("flags", [])
    is_handwritten = "handwritten" in flags

    critical = get_critical_fields(doc_type)

    for field in critical:
        score = confidence.get(field)
        if score is None:
            # If confidence isn't recorded for a critical field, escalate
            escalations.append(
                f"No confidence score recorded for '{field}' on "
                f"{doc_type} {record.get('source_ref', 'unknown')}"
            )
            continue

        if needs_escalation(field, score, doc_type, is_handwritten):
            escalations.append(
                f"Low confidence ({score:.2f}) on '{field}' for "
                f"{doc_type} {record.get('source_ref', 'unknown')} — "
                f"needs owner verification"
            )

    return escalations


def merge_confidence(existing: dict, updates: dict) -> dict:
    """Merge confidence updates into an existing confidence dict."""
    result = existing.copy()
    result.update(updates)
    return result

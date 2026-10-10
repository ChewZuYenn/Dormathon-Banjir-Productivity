"""
Bad Document Handler

Handles documents that are difficult or impossible to parse.
Core principle: FLAG, DO NOT GUESS.

Bad document types from the brief:
1. Blurry photo
2. Handwritten
3. No PO reference
4. Wrong total
5. Duplicate
"""

from typing import Any, Optional

# Flag constants
FLAG_BLURRY = "blurry_image"
FLAG_HANDWRITTEN = "handwritten"
FLAG_NO_PO = "no_po_reference"
FLAG_WRONG_TOTAL = "total_mismatch"
FLAG_DUPLICATE = "possible_duplicate"
FLAG_UNPARSEABLE = "unparseable"
FLAG_UNKNOWN_TYPE = "unknown_document_type"
FLAG_MISSING_VENDOR = "missing_vendor_name"
FLAG_MISSING_DATE = "missing_date"
FLAG_MISSING_TOTAL = "missing_grand_total"


def handle_bad_document(
    source_ref: str,
    raw_content: Optional[str] = None,
    detected_flags: Optional[list[str]] = None,
    partial_record: Optional[dict] = None,
) -> dict:
    """
    Create a minimal record for a bad document that couldn't be fully extracted.

    The record has:
    - source_ref (always)
    - status: 'error' if completely unparseable, 'flagged' if partially extracted
    - All flags that were detected
    - Any fields that could be extracted (from partial_record)
    - Confidence scores of 0.0 for unextractable fields
    """
    flags = detected_flags or []
    partial = partial_record or {}

    if FLAG_UNPARSEABLE in flags:
        # Completely unparseable — minimal record
        return {
            "source_ref": source_ref,
            "status": "error",
            "flags": flags,
            "confidence": {},
            "document_type": partial.get("document_type", "unknown"),
            "raw_content_preview": (raw_content or "")[:200] if raw_content else None,
        }

    # Partially extracted — merge what we have
    record = {
        "source_ref": source_ref,
        "status": "flagged",
        "flags": flags,
    }

    # Merge any partially extracted fields
    for key, value in partial.items():
        if key not in ("source_ref", "status", "flags"):
            record[key] = value

    # Ensure confidence dict exists
    if "confidence" not in record:
        record["confidence"] = {}

    # Set confidence to 0.0 for fields that couldn't be extracted
    # (only for fields we know should exist but don't)
    critical_fields = ["vendor_name", "invoice_number", "invoice_date",
                       "po_number", "receipt_date", "amount", "grand_total"]
    for field in critical_fields:
        if field not in record or record.get(field) is None:
            if field not in record.get("confidence", {}):
                record["confidence"][field] = 0.0

    return record


def detect_bad_document_signals(content: str) -> list[str]:
    """
    Heuristic detection of bad document signals from extracted text.
    Used as a pre-check before full extraction.
    """
    flags = []
    content_lower = content.lower() if content else ""

    if not content or len(content.strip()) < 10:
        flags.append(FLAG_UNPARSEABLE)
        return flags

    # Check for common bad signals (these are heuristics — the agent prompt
    # does the real detection, this is a fallback)
    if "???" in content or "[illegible]" in content.lower():
        flags.append(FLAG_BLURRY)

    if any(word in content_lower for word in ["tangan", "handwritten", "ditulis tangan"]):
        flags.append(FLAG_HANDWRITTEN)

    if "po" not in content_lower and "purchase order" not in content_lower and "pesanan" not in content_lower:
        # Might be missing PO reference — only a signal, not definitive
        pass  # Let the agent decide based on document type

    return flags


def should_escalate_for_missing_po(record: dict, threshold_rm: float = 500.0) -> bool:
    """
    Check if a missing PO reference should be escalated to the owner.
    Per rules: escalate if PO missing AND invoice amount > RM 500.
    """
    if record.get("po_reference") is not None:
        return False

    grand_total = record.get("grand_total")
    if grand_total is None:
        return True  # Can't determine amount — escalate

    return grand_total > threshold_rm

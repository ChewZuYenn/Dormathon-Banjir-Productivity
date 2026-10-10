"""
Document Type Detector

Detects whether a document is an invoice, receipt, or purchase order.
Uses keyword matching as a fallback — the primary detection is done by the
WorkBuddy agent using the system prompt.
"""

import re
from typing import Optional

# Keyword patterns for document type detection
# Supports both English and Bahasa Malaysia
TYPE_PATTERNS = {
    "invoice": [
        r"\binvoice\b", r"\binvois\b", r"\bbil\b",
        r"\bamount due\b", r"\bjumlah tertunggak\b",
        r"\bdue date\b", r"\btarikh tamat\b",
        r"\bsst\b.*\binvoice\b", r"\btax invoice\b",
    ],
    "receipt": [
        r"\breceipt\b", r"\bresit\b",
        r"\bpayment received\b", r"\bpembayaran diterima\b",
        r"\bpaid\b", r"\btelah dibayar\b",
        r"\bcash\b.*\breceipt\b", r"\bduitnow\b",
    ],
    "order": [
        r"\bpurchase order\b", r"\bpesanan pembelian\b",
        r"\bpo\s*no\b", r"\bpo\s*number\b",
        r"\border\s*no\b", r"\bp\.o\.\s",
        r"\bdelivery date\b", r"\btarikh penghantaran\b",
    ],
}


def detect_document_type(content: str) -> tuple[str, float]:
    """
    Detect the document type from text content.
    Returns (document_type, confidence).

    The confidence is based on how many patterns matched:
    - 3+ matches: 0.9
    - 2 matches: 0.7
    - 1 match: 0.5
    - 0 matches: 0.0 (unknown)
    """
    if not content:
        return ("unknown", 0.0)

    content_lower = content.lower()
    scores = {}

    for doc_type, patterns in TYPE_PATTERNS.items():
        matches = 0
        for pattern in patterns:
            if re.search(pattern, content_lower):
                matches += 1
        scores[doc_type] = matches

    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]

    if best_score == 0:
        return ("unknown", 0.0)
    elif best_score >= 3:
        return (best_type, 0.9)
    elif best_score == 2:
        return (best_type, 0.7)
    else:
        return (best_type, 0.5)


def detect_from_filename(filename: str) -> tuple[str, float]:
    """
    Detect document type from filename as a hint.
    """
    name_lower = filename.lower()
    if any(kw in name_lower for kw in ["inv", "invoice", "invois"]):
        return ("invoice", 0.6)
    if any(kw in name_lower for kw in ["rcpt", "receipt", "resit"]):
        return ("receipt", 0.6)
    if any(kw in name_lower for kw in ["po", "order", "pesanan"]):
        return ("order", 0.6)
    return ("unknown", 0.0)


def detect(content: str, filename: str = "") -> tuple[str, float]:
    """
    Combined detection from both content and filename.
    Content takes priority.
    """
    type_from_content, conf_content = detect_document_type(content)
    type_from_name, conf_name = detect_from_filename(filename) if filename else ("unknown", 0.0)

    # Content detection is more reliable
    if conf_content >= 0.5:
        return (type_from_content, conf_content)

    # Fall back to filename hint
    if conf_name >= 0.5:
        return (type_from_name, conf_name)

    return ("unknown", 0.0)

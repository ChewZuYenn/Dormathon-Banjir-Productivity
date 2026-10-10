"""Checks for the orchestrator's LLM-record self-check. Run: python -m pytest agents/test_orchestrator.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents.orchestrator import normalize_extracted


def test_normalize_coerces_llm_formats():
    rec = normalize_extracted({
        "tax_rate": "10%", "grand_total": "RM 1,200.50", "invoice_date": "07 Oct 2026",
        "due_date": None, "line_items": [{"quantity": "30", "unit_price": 10.0}],
        "confidence": {"vendor_name": "0.9"}, "flags": "total_mismatch", "status": "clean",
    })
    assert rec["tax_rate"] == 10.0 and rec["grand_total"] == 1200.5
    assert rec["invoice_date"] == "2026-10-07" and rec["due_date"] is None
    assert rec["line_items"][0]["quantity"] == 30.0
    assert rec["confidence"] == {"vendor_name": 0.9}
    assert rec["flags"] == ["total_mismatch"] and rec["status"] == "clean"


def test_normalize_flags_instead_of_guessing():
    rec = normalize_extracted({"grand_total": "illegible", "invoice_date": "sometime", "status": "clean"})
    assert rec["grand_total"] is None and rec["invoice_date"] is None
    assert "unparseable_field" in rec["flags"] and rec["status"] == "flagged"
    assert "grand_total" in rec["notes"] and "invoice_date" in rec["notes"]

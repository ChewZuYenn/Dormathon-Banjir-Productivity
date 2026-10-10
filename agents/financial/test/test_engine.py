"""
End-to-end check: Logistics output.json -> Financial engine.

Run: python agents/financial/test/test_engine.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from engine import FinancialEngine, categorise

with open(os.path.join(HERE, "..", "..", "logistics", "output.json"), encoding="utf-8") as f:
    records = json.load(f)

ledger, exceptions = FinancialEngine(records).run()  # bare list, exactly as Logistics hands it over

by_type = {}
for e in exceptions["exceptions"]:
    by_type.setdefault(e["type"], set()).add(e.get("document_number"))

# Ledger reconciles to the printed subtotals and SST, each document counted once (INV-2026-020 is in the set twice)
printed = {}
for r in records:
    if r["document_type"] != "order":
        num = r.get("invoice_number") or r.get("receipt_number")
        printed[(num, r["vendor_name"])] = (r["subtotal"], r.get("total_tax", r.get("tax_amount")))
assert ledger["summary"]["total_out"] == round(sum(s for s, _ in printed.values()), 2), ledger["summary"]["total_out"]
assert ledger["summary"]["total_tax"] == round(sum(t for _, t in printed.values()), 2), ledger["summary"]["total_tax"]
assert all(r["direction"] == "out" for r in ledger["rows"]), "every receipt in this set is a purchase"

assert by_type["duplicate_similar_confidence"] == {"INV-2026-020"}
assert by_type["quantity_mismatch"] == {"INV-2026-032", "INV-2026-033"}
assert by_type["arithmetic_mismatch"] == {"INV-2026-016", "PO-2026-A05"}
assert by_type["conflicting_printed_values"] == {"INV-2026-016", "INV-2026-033", "PO-2026-A04", "PO-2026-A05", "PO-2026-A06"}
assert "INV-2026-026" not in by_type["missing_po_match"], "should match PO-2026-A04 despite 'Gunting' vs 'Cunting'"
assert categorise("Pembaikan injap / Valve repair") == "MAINT"

print(f"OK — {len(ledger['rows'])} ledger rows, {len(exceptions['exceptions'])} exceptions")

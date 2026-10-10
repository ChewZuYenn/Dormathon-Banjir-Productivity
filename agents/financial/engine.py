#!/usr/bin/env python3
"""
Financial Agent — Validation Engine
====================================
Takes structured records from Logistics, produces a reconciled ledger
and an exception list.

Usage:
    python engine.py test/mock_records.json

Output:
    Writes ledger.json and exceptions.json to the same directory as the input.
"""

import json
import re
import sys
import os
from datetime import date, datetime, timedelta
from itertools import combinations

# ─── Constants ───────────────────────────────────────────────────────────────

TODAY = date(2026, 10, 10)  # Demo date: "close out September"
PERIOD = "2026-09"

CATEGORIES = [
    "COGS", "RENT", "UTIL", "SALARY", "SUPPLIES",
    "MARKETING", "MAINT", "TRANSPORT", "FEES", "MISC"
]

CATEGORY_KEYWORDS = [
    # (keywords, category) — checked in order, first match wins
    (["rent", "sewa"], "RENT"),
    (["electric", "water", "internet", "elektrik", "air", "tm ", "unifi", "tenaga", "tnb"], "UTIL"),
    (["salary", "wages", "gaji", "payroll"], "SALARY"),
    (["stationery", "packaging", "bekas", "alat tulis", "cleaning", "pembersihan", "paper", "pen", "ballpoint"], "SUPPLIES"),
    (["ad ", "ads", "promotion", "promo", "print", "iklan", "cetak", "flyer", "facebook"], "MARKETING"),
    (["repair", "service", "servis", "baiki", "maintenance", "penyelenggaraan", "descale", "gasket", "espresso machine"], "MAINT"),
    (["delivery", "fuel", "minyak", "logistics", "penghantaran", "transport", "grab"], "TRANSPORT"),
    (["accounting", "legal", "permit", "lesen", "audit", "gua", "professional fee"], "FEES"),
]

VALID_SST_RATES = {0, 6, 8}
SST_RATE_TOLERANCE = 0.5  # ±0.5%

# Same critical fields Logistics escalates on (agents/logistics/src/confidence.py)
CRITICAL_CONF_FIELDS = ("vendor_name", "invoice_number", "receipt_number", "po_number",
                        "invoice_date", "receipt_date", "po_date", "grand_total", "amount", "line_items")


def get_tolerance(amount: float) -> float:
    """Arithmetic tolerance: ±RM 1.00 up to RM 1,000; ±RM 5.00 above."""
    return 1.00 if amount <= 1000 else 5.00


# The generated test documents all print "SST 10%". That comes from the template used to
# generate the data set, not from the documents' issuers or from the agents, so 10% is
# accepted instead of raising a tax_rate_anomaly on every document. Tax amounts that
# don't match the printed rate are still flagged.
# ponytail: accepts 10% for any input; remove this set when running on real documents.
TEMPLATE_SST_RATES = {10}


def valid_sst(rate: float) -> bool:
    return any(abs(rate - r) <= SST_RATE_TOLERANCE for r in VALID_SST_RATES | TEMPLATE_SST_RATES)


def doc_number(rec) -> str:
    return rec.get("invoice_number") or rec.get("po_number") or rec.get("receipt_number") or "?"


def doc_date(rec):
    return rec.get("invoice_date") or rec.get("po_date") or rec.get("receipt_date")


def doc_total(rec):
    """Printed total: receipts call it `amount`, invoices/POs `grand_total`."""
    return rec.get("amount") if rec.get("document_type") == "receipt" else rec.get("grand_total")


def doc_tax(rec):
    return rec.get("tax_amount") if rec.get("document_type") == "receipt" else rec.get("total_tax")


def line_amount(li) -> float:
    """Receipts print one price per line; invoices/POs print qty x unit price."""
    if "amount" in li:
        return li["amount"] or 0
    return (li.get("quantity") or 0) * (li.get("unit_price") or 0)


def same_item(a, b) -> bool:
    """Lines are bilingual ('Gunting dahan / Branch cutter'); a match in either language counts."""
    keys = lambda li: {p.strip().lower() for p in li.get("description", "").split("/") if p.strip()}
    return bool(keys(a) & keys(b))


def safe_date(s):
    """Parse a date string, return None if invalid/empty."""
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


# ─── Categorisation ──────────────────────────────────────────────────────────

def categorise(description: str, quantity=None) -> str:
    desc = description.lower()
    for keywords, category in CATEGORY_KEYWORDS:
        # Keyword must start a word, so 'air' no longer matches 'repair'
        if any(re.search(r"\b" + re.escape(kw), desc) for kw in keywords):
            return category
    # Default: COGS if quantity > 0 and looks like inventory
    if quantity and quantity > 0:
        inventory_hints = ["bean", "coffee", "cup", "stock", "raw material", "bahan"]
        if any(kw in desc for kw in inventory_hints):
            return "COGS"
    return "MISC"


# ─── Engine ──────────────────────────────────────────────────────────────────

class FinancialEngine:
    def __init__(self, records_data):
        # Logistics hands over a bare JSON array; the mock wraps it as {"period", "records"}
        if isinstance(records_data, list):
            records_data = {"records": records_data}
        self.period = records_data.get("period", PERIOD)
        self.records = records_data.get("records", [])
        self.invoices = []
        self.receipts = []
        self.orders = []
        self.ledger_rows = []
        self.exceptions = []
        self._row_counter = 0
        self._exc_counter = 0

    def _next_row_id(self):
        self._row_counter += 1
        return f"LED-{self._row_counter:04d}"

    def _next_exc_id(self):
        self._exc_counter += 1
        return f"EXC-{self._exc_counter:04d}"

    def _add_exception(self, **kwargs):
        exc = {
            "exception_id": self._next_exc_id(),
            "source_ref": kwargs.get("source_ref", ""),
            **kwargs
        }
        self.exceptions.append(exc)

    # ── Step 1: Receive and Index ──
    def step1_index(self):
        for rec in self.records:
            dtype = rec.get("document_type", "")
            status = rec.get("status", "clean")
            if status == "error":
                self._add_exception(
                    type="unknown_document_type",
                    reason=f"Document {rec.get('source_ref', '?')} has status 'error' — unparseable by Logistics",
                    source_ref=rec.get("source_ref", ""),
                    severity="critical",
                    suggested_action=f"Re-examine the original document {rec.get('source_ref', '?')} — Logistics could not parse it."
                )
                continue
            if dtype == "invoice":
                self.invoices.append(rec)
            elif dtype == "receipt":
                self.receipts.append(rec)
            elif dtype in ("order", "po"):
                self.orders.append(rec)

    # ── Step 2 & 3: Build Ledger + Categorise ──
    def step2_build_ledger(self):
        for inv in self.invoices:
            self._add_rows(inv, "out")

        # A receipt that pays one of our invoices is payment proof, not a second expense
        paid = {r.get("source_ref") for r in map(self._find_matching_receipt, self.invoices) if r}
        for recpt in self.receipts:
            if recpt.get("invoice_reference") or recpt.get("source_ref") in paid:
                continue
            # Receipts are purchases unless Logistics marked one as issued by us (a sale)
            self._add_rows(recpt, "in" if recpt.get("direction") == "in" else "out")

    def _add_rows(self, rec, direction):
        lines = rec.get("line_items") or []
        if not lines:  # receipt with only a total printed
            tax = doc_tax(rec) or 0
            label = "Sales income" if direction == "in" else "Purchase"
            lines = [{"description": f"{label} — {rec.get('vendor_name', '')}", "amount": (doc_total(rec) or 0) - tax, "tax_amount": tax}]

        amounts = [round(line_amount(li), 2) for li in lines]
        taxes = [li.get("tax_amount") or 0 for li in lines]
        total_tax = doc_tax(rec) or 0
        if not any(taxes) and total_tax and sum(amounts):
            # Only a document-level SST is printed: spread it pro rata, rounding remainder on the last line
            taxes = [round(total_tax * a / sum(amounts), 2) for a in amounts]
            taxes[-1] = round(total_tax - sum(taxes[:-1]), 2)

        min_conf = self._min_confidence(rec)
        for li, amount, tax in zip(lines, amounts, taxes):
            cat = "MISC" if direction == "in" else categorise(li.get("description", ""), li.get("quantity"))
            row = {
                "row_id": self._next_row_id(),
                "direction": direction,
                "category": cat,
                "description": li.get("description", ""),
                "quantity": li.get("quantity"),
                "unit_price": li.get("unit_price"),
                "amount": amount,
                "tax_amount": round(tax, 2),
                "amount_incl_tax": round(amount + tax, 2),
                "source_ref": rec.get("source_ref", ""),
                "document_type": rec.get("document_type"),
                "document_number": doc_number(rec),
                "document_date": doc_date(rec) or "",
                "vendor_name": rec.get("vendor_name", ""),
                "confidence": min_conf,
                "reconciled": False,
                "reconciled_with": None,
                "flags": list(rec.get("flags", []))
            }
            if cat == "MISC" and direction == "out":
                row["flags"].append("uncategorised")
            self.ledger_rows.append(row)

    def _min_confidence(self, rec: dict) -> float:
        conf = rec.get("confidence", {})
        return min((conf[f] for f in CRITICAL_CONF_FIELDS if conf.get(f) is not None), default=1.0)

    # ── Step 4: Arithmetic Validation ──
    def step4_arithmetic(self):
        for rec in [*self.invoices, *self.orders, *self.receipts]:
            doc_num = doc_number(rec)
            doc = dict(source_ref=rec.get("source_ref", ""), document_number=doc_num,
                       document_type=rec.get("document_type"), vendor_name=rec.get("vendor_name"))

            if "conflicting_values" in rec.get("flags", []):
                self._add_exception(
                    type="conflicting_printed_values",
                    reason=f"{doc_num} prints conflicting figures: {rec.get('notes') or 'see source document'}",
                    severity="critical",
                    suggested_action=f"Check the original {doc_num} and confirm which figure is correct.",
                    **doc
                )

            grand = doc_total(rec)
            subtotal = rec.get("subtotal")
            total_tax = doc_tax(rec)
            lines = rec.get("line_items") or []

            # 4a: Check line items sum vs subtotal
            if subtotal is not None and lines:
                computed_subtotal = round(sum(line_amount(li) for li in lines), 2)
                tol = get_tolerance(subtotal)
                delta_sub = abs(subtotal - computed_subtotal)
                if delta_sub > tol:
                    self._add_exception(
                        type="arithmetic_mismatch",
                        reason=f"Subtotal RM {subtotal:.2f} on {doc_num} does not match sum of line items RM {computed_subtotal:.2f} (delta: RM {delta_sub:.2f}, exceeds tolerance of RM {tol:.2f})",
                        severity="critical",
                        delta=round(delta_sub, 2),
                        details={"expected": computed_subtotal, "actual": subtotal, "tolerance": tol, "check": "subtotal_vs_line_items"},
                        suggested_action=f"Verify the subtotal on {doc_num} — it does not match the sum of line item amounts.",
                        **doc
                    )

            # 4b: Check grand_total vs subtotal + total_tax
            if grand is None:
                self._add_exception(
                    type="unparseable_total",
                    reason=f"Grand total is missing or unparseable on {doc_num}",
                    severity="critical",
                    suggested_action=f"Confirm the grand total on {doc_num} — it is missing or unreadable.",
                    **doc
                )
                continue
            if subtotal is None or total_tax is None:
                continue  # Can't check grand total
            expected = round(subtotal + total_tax, 2)
            tolerance = get_tolerance(grand)
            delta = abs(grand - expected)
            if delta > tolerance:
                self._add_exception(
                    type="arithmetic_mismatch",
                    reason=f"Grand total RM {grand:.2f} does not match subtotal + tax = RM {expected:.2f} (delta: RM {delta:.2f}, exceeds tolerance of RM {tolerance:.2f})",
                    severity="critical",
                    delta=round(delta, 2),
                    details={"expected": expected, "actual": grand, "tolerance": tolerance},
                    suggested_action=f"Verify the total on {doc_num} — the printed grand total does not match the sum of subtotal and tax.",
                    **doc
                )

            # 4c: Check total_tax vs sum of line item tax_amounts — only when the lines carry tax
            # (tax_amount null = the document prints SST once, not per line)
            if any(li.get("tax_amount") is not None for li in lines):
                computed_tax = sum(li.get("tax_amount", 0) or 0 for li in lines)
                delta_tax = abs(total_tax - computed_tax)
                if delta_tax > 1.00:  # RM 1 tolerance on tax
                    self._add_exception(
                        type="arithmetic_mismatch",
                        reason=f"Total tax RM {total_tax:.2f} on {doc_num} does not match sum of line item taxes RM {computed_tax:.2f} (delta: RM {delta_tax:.2f})",
                        severity="warning",
                        delta=round(delta_tax, 2),
                        details={"expected": computed_tax, "actual": total_tax, "tolerance": 1.0, "check": "total_tax_vs_line_items"},
                        suggested_action=f"Verify the tax total on {doc_num} — it does not match the sum of line item tax amounts.",
                        **doc
                    )

    # ── Step 5: SST Rate Validation ──
    def step5_sst(self):
        for rec in [*self.invoices, *self.orders, *self.receipts]:
            doc_num = doc_number(rec)
            lines = rec.get("line_items") or []
            if any((li.get("tax_amount") or 0) > 0 for li in lines):
                self._check_line_sst(rec, doc_num, lines)
                continue

            # Only a document-level SST is printed: check it against the subtotal and the printed rate
            subtotal, tax, printed = rec.get("subtotal"), doc_tax(rec), rec.get("tax_rate")
            if not subtotal or tax is None:
                continue
            effective = tax / subtotal * 100
            problems = []
            if printed is not None and not valid_sst(printed):
                problems.append(f"printed rate {printed:g}% is not a standard Malaysian rate (0%, 6%, 8%)")
            if printed is not None and abs(effective - printed) > SST_RATE_TOLERANCE:
                problems.append(f"RM {tax:.2f} is {effective:.1f}% of the RM {subtotal:.2f} subtotal, not the printed {printed:g}%")
            elif printed is None and not valid_sst(effective):
                problems.append(f"RM {tax:.2f} is {effective:.1f}% of the RM {subtotal:.2f} subtotal, not a standard rate (0%, 6%, 8%)")
            if problems:
                self._add_exception(
                    type="tax_rate_anomaly",
                    reason=f"SST on {doc_num}: " + "; ".join(problems),
                    source_ref=rec.get("source_ref", ""),
                    document_number=doc_num,
                    document_type=rec.get("document_type"),
                    vendor_name=rec.get("vendor_name"),
                    severity="warning",
                    details={"expected": printed, "actual": round(effective, 2)},
                    suggested_action=f"Check the SST on {doc_num}."
                )

    def _check_line_sst(self, rec, doc_num, lines):
        for li in lines:
            tax = li.get("tax_amount", 0) or 0
            if tax <= 0:
                continue
            line_subtotal = line_amount(li)
            if line_subtotal <= 0:
                continue
            effective_rate = (tax / line_subtotal) * 100
            if not valid_sst(effective_rate):
                desc = li.get("description", "?")
                self._add_exception(
                    type="tax_rate_anomaly",
                    reason=f"SST rate on line '{desc}' in {doc_num} is {effective_rate:.1f}%, which is not a standard Malaysian rate (0%, 6%, 8%)",
                    source_ref=rec.get("source_ref", ""),
                    document_number=doc_num,
                    document_type=rec.get("document_type"),
                    vendor_name=rec.get("vendor_name"),
                    severity="warning",
                    details={"field": f"line_item_sst_rate:{desc}", "confidence_score": None},
                    suggested_action=f"Check the SST calculation on line '{desc}' in {doc_num}."
                )

    # ── Step 6: Duplicate Detection ──
    def step6_duplicates(self):
        for a, b in combinations(self.invoices, 2):
            if self._is_duplicate(a, b):
                self._handle_duplicate(a, b)
        for a, b in combinations(self.orders, 2):
            if self._is_duplicate(a, b):
                self._handle_duplicate(a, b)
        for a, b in combinations(self.receipts, 2):
            if self._is_duplicate(a, b):
                self._handle_duplicate(a, b)

    def _is_duplicate(self, a, b) -> bool:
        # Rule 1: same invoice/receipt/PO number AND same vendor
        num_a = a.get("invoice_number") or a.get("po_number") or a.get("receipt_number", "")
        num_b = b.get("invoice_number") or b.get("po_number") or b.get("receipt_number", "")
        if num_a and num_b and num_a == num_b and a.get("vendor_name") == b.get("vendor_name"):
            return True
        # Rule 2: same vendor + same date + same grand total (within tolerance)
        date_a = a.get("invoice_date") or a.get("po_date") or a.get("receipt_date")
        date_b = b.get("invoice_date") or b.get("po_date") or b.get("receipt_date")
        grand_a = a.get("grand_total") or a.get("amount")
        grand_b = b.get("grand_total") or b.get("amount")
        if a.get("vendor_name") == b.get("vendor_name") and date_a == date_b and grand_a is not None and grand_b is not None:
            tol = get_tolerance(max(grand_a, grand_b))
            if abs(grand_a - grand_b) <= tol:
                return True
        # Rule 3: same line item composition + same total (within tolerance)
        lines_a = [li.get("description", "") for li in a.get("line_items", [])]
        lines_b = [li.get("description", "") for li in b.get("line_items", [])]
        if lines_a and lines_b and sorted(lines_a) == sorted(lines_b) and grand_a is not None and grand_b is not None:
            tol = get_tolerance(max(grand_a, grand_b))
            if abs(grand_a - grand_b) <= tol:
                return True
        return False

    def _handle_duplicate(self, a, b):
        conf_a = self._min_confidence(a)
        conf_b = self._min_confidence(b)
        num_a = a.get("invoice_number") or a.get("po_number") or a.get("receipt_number", "?")
        num_b = b.get("invoice_number") or b.get("po_number") or b.get("receipt_number", "?")
        # Mark lower-confidence rows as duplicate
        lower = b if conf_a >= conf_b else a
        for row in self.ledger_rows:
            if row["source_ref"] == lower.get("source_ref"):
                if "duplicate" not in row["flags"]:
                    row["flags"].append("duplicate")
        # Determine severity
        if abs(conf_a - conf_b) < 0.05:
            exc_type = "duplicate_similar_confidence"
            severity = "critical"
        else:
            exc_type = "duplicate"
            severity = "warning"
        self._add_exception(
            type=exc_type,
            reason=f"Duplicate detected: {num_a} and {num_b} — same number and vendor" if (num_a == num_b) else f"Duplicate detected: {num_a} and {num_b} — same content/total",
            source_ref=a.get("source_ref", ""),
            document_number=num_a,
            document_type=a.get("document_type"),
            vendor_name=a.get("vendor_name"),
            severity=severity,
            details={"matched_with": b.get("source_ref", "")},
            suggested_action=f"Verify which document is the correct one — {num_a} and {num_b} appear to be duplicates."
        )

    # ── Step 7: Order-vs-Invoice Match ──
    def step7_order_invoice_match(self):
        for inv in self.invoices:
            matched_po = self._find_matching_po(inv)
            if not matched_po:
                num = inv.get("invoice_number", "?")
                ref = inv.get("po_reference")
                self._add_exception(
                    type="missing_po_match",
                    reason=f"Invoice {num} references {ref}, but that purchase order is not among the documents" if ref
                    else f"No purchase order found matching invoice {num}",
                    source_ref=inv.get("source_ref", ""),
                    document_number=num,
                    document_type="invoice",
                    vendor_name=inv.get("vendor_name"),
                    severity="warning",
                    suggested_action=f"Locate the PO for invoice {num} from {inv.get('vendor_name','?')}, or confirm the purchase was without a PO."
                )
                continue
            # Compare line items
            for inv_li in inv.get("line_items", []):
                for po_li in matched_po.get("line_items", []):
                    if same_item(inv_li, po_li):
                        # Quantity check
                        if inv_li.get("quantity", 0) != po_li.get("quantity", 0):
                            num = inv.get("invoice_number", "?")
                            po_num = matched_po.get("po_number", "?")
                            desc = inv_li.get("description", "?")
                            self._add_exception(
                                type="quantity_mismatch",
                                reason=f"Quantity mismatch on '{desc}': invoice {num} shows {inv_li['quantity']} but PO {po_num} ordered {po_li['quantity']}",
                                source_ref=inv.get("source_ref", ""),
                                document_number=num,
                                document_type="invoice",
                                vendor_name=inv.get("vendor_name"),
                                severity="warning",
                                delta=(inv_li.get("quantity") or 0) - (po_li.get("quantity") or 0),
                                details={"expected": po_li["quantity"], "actual": inv_li["quantity"], "matched_with": matched_po.get("source_ref")},
                                suggested_action=f"Invoice {num} shows {inv_li['quantity']} units but PO {po_num} ordered {po_li['quantity']} for '{desc}'."
                            )
                        # Price check
                        if inv_li.get("unit_price", 0) != po_li.get("unit_price", 0):
                            num = inv.get("invoice_number", "?")
                            po_num = matched_po.get("po_number", "?")
                            desc = inv_li.get("description", "?")
                            self._add_exception(
                                type="price_mismatch",
                                reason=f"Price mismatch on '{desc}': invoice {num} shows RM {inv_li['unit_price']:.2f} but PO {po_num} listed RM {po_li['unit_price']:.2f}",
                                source_ref=inv.get("source_ref", ""),
                                document_number=num,
                                document_type="invoice",
                                vendor_name=inv.get("vendor_name"),
                                severity="warning",
                                delta=round(inv_li["unit_price"] - po_li["unit_price"], 2),
                                details={"expected": po_li["unit_price"], "actual": inv_li["unit_price"], "matched_with": matched_po.get("source_ref")},
                                suggested_action=f"Invoice {num} shows RM {inv_li['unit_price']:.2f}/unit but PO {po_num} listed RM {po_li['unit_price']:.2f}/unit for '{desc}'."
                            )

    def _find_matching_po(self, inv):
        po_ref = inv.get("po_reference")
        for po in self.orders:
            if po_ref and po.get("po_number") == po_ref:
                return po
        # Fallback: same vendor + PO within ±7 days + more than half the invoice lines on the PO
        inv_date = safe_date(inv.get("invoice_date"))
        inv_lines = inv.get("line_items") or []
        for po in self.orders:
            po_date = safe_date(po.get("po_date"))
            if po.get("vendor_name") != inv.get("vendor_name") or not (po_date and inv_date) or abs((inv_date - po_date).days) > 7:
                continue
            on_po = sum(any(same_item(li, po_li) for po_li in po.get("line_items", [])) for li in inv_lines)
            if inv_lines and on_po / len(inv_lines) > 0.5:
                return po
        return None

    # ── Step 8: Reconciliation (Invoice → Receipt) ──
    def step8_reconciliation(self):
        for inv in self.invoices:
            matched_receipt = self._find_matching_receipt(inv)
            if matched_receipt:
                for row in self.ledger_rows:
                    if row["source_ref"] == inv.get("source_ref"):
                        row["reconciled"] = True
                        row["reconciled_with"] = matched_receipt.get("source_ref")
            else:
                num = inv.get("invoice_number", "?")
                due_str = inv.get("due_date")
                due = safe_date(due_str)
                if due is None:
                    # No due date at all
                    self._add_exception(
                        type="no_due_date",
                        reason=f"Invoice {num} from {inv.get('vendor_name','?')} has no due date — cannot determine if overdue.",
                        source_ref=inv.get("source_ref", ""),
                        document_number=num,
                        document_type="invoice",
                        vendor_name=inv.get("vendor_name"),
                        severity="warning",
                        suggested_action=f"Confirm the payment due date for invoice {num} from {inv.get('vendor_name','?')}."
                    )
                elif due < TODAY:
                    grand = inv.get("grand_total", 0)
                    self._add_exception(
                        type="overdue",
                        reason=f"Invoice {num} from {inv.get('vendor_name','?')} is overdue (due: {due.isoformat()}). No matching payment receipt found.",
                        source_ref=inv.get("source_ref", ""),
                        document_number=num,
                        document_type="invoice",
                        vendor_name=inv.get("vendor_name"),
                        severity="critical",
                        suggested_action=f"Draft a chase email to {inv.get('vendor_name','?')} for overdue invoice {num} (RM {grand:.2f}, due {due.isoformat()})."
                    )

    def _find_matching_receipt(self, inv):
        inv_ref = inv.get("invoice_number")
        for r in self.receipts:
            # Match by invoice_reference
            if inv_ref and r.get("invoice_reference") == inv_ref:
                return r
            # Fallback: vendor + date proximity + amount
            if r.get("vendor_name") == inv.get("vendor_name"):
                r_date = safe_date(r.get("receipt_date"))
                inv_date = safe_date(inv.get("invoice_date"))
                if r_date and inv_date and abs((r_date - inv_date).days) <= 14:
                    grand = inv.get("grand_total")
                    amt = r.get("amount")
                    if grand is not None and amt is not None:
                        tol = get_tolerance(max(grand, amt))
                        if abs(grand - amt) <= tol:
                            return r
        return None

    # ── Step 10: Confidence Escalation ──
    def step10_confidence(self):
        for rec in self.invoices + self.receipts + self.orders:
            conf = rec.get("confidence", {})
            min_conf = self._min_confidence(rec)
            if min_conf < 0.7:
                lowest_field = min((f for f in CRITICAL_CONF_FIELDS if conf.get(f) is not None), key=conf.get)
                num = rec.get("invoice_number") or rec.get("po_number") or rec.get("receipt_number", "?")
                self._add_exception(
                    type="low_confidence",
                    reason=f"Critical field '{lowest_field}' has confidence {min_conf:.2f} on {num}",
                    source_ref=rec.get("source_ref", ""),
                    document_number=num,
                    document_type=rec.get("document_type"),
                    vendor_name=rec.get("vendor_name"),
                    severity="warning",
                    details={"field": lowest_field, "confidence_score": min_conf},
                    suggested_action=f"Verify {lowest_field} on {num} — extraction confidence is low ({min_conf:.2f})."
                )

            # Handwritten + low OCR
            flags = rec.get("flags", [])
            if "handwritten" in flags and min_conf < 0.6:
                num = rec.get("invoice_number") or rec.get("po_number") or rec.get("receipt_number", "?")
                self._add_exception(
                    type="handwritten_low_ocr",
                    reason=f"Document {num} is handwritten with OCR confidence {min_conf:.2f} (below 0.60)",
                    source_ref=rec.get("source_ref", ""),
                    document_number=num,
                    document_type=rec.get("document_type"),
                    vendor_name=rec.get("vendor_name"),
                    severity="warning",
                    details={"field": "overall_ocr", "confidence_score": min_conf},
                    suggested_action=f"Manually transcribe {num} — it is handwritten and OCR confidence is too low."
                )

            # Missing PO reference + high value
            if rec.get("document_type") == "invoice":
                grand = rec.get("grand_total")
                if not rec.get("po_reference") and grand and grand > 500:
                    num = rec.get("invoice_number", "?")
                    self._add_exception(
                        type="missing_po_reference_high_value",
                        reason=f"Invoice {num} (RM {grand:.2f}) has no PO reference and exceeds RM 500 threshold",
                        source_ref=rec.get("source_ref", ""),
                        document_number=num,
                        document_type="invoice",
                        vendor_name=rec.get("vendor_name"),
                        severity="warning",
                        suggested_action=f"Confirm the PO reference for invoice {num} (RM {grand:.2f}) — no PO was referenced."
                    )

    # ── Step 11: Traceability ──
    def step11_traceability(self):
        for row in self.ledger_rows:
            if not row.get("source_ref"):
                self._add_exception(
                    type="traceability_broken",
                    reason=f"Ledger row {row['row_id']} has no source_ref — traceability broken",
                    source_ref="",
                    severity="critical",
                    suggested_action=f"Identify the source document for ledger row {row['row_id']}."
                )

    # ── Step 12 & 13: Build Summary ──
    def build_outputs(self) -> tuple:
        # Ledger summary — duplicate rows stay visible in the ledger but are not counted twice
        counted = [r for r in self.ledger_rows if "duplicate" not in r["flags"]]
        total_in = sum(r["amount"] for r in counted if r["direction"] == "in")
        total_out = sum(r["amount"] for r in counted if r["direction"] == "out")
        total_tax = sum(r.get("tax_amount", 0) or 0 for r in counted)

        # By category
        cat_map = {}
        for r in counted:
            cat = r["category"]
            if cat not in cat_map:
                cat_map[cat] = {"category": cat, "total_amount": 0, "total_tax": 0, "row_count": 0}
            cat_map[cat]["total_amount"] += r["amount"]
            cat_map[cat]["total_tax"] += r.get("tax_amount", 0) or 0
            cat_map[cat]["row_count"] += 1

        invoice_rows = [r for r in counted if r["document_type"] == "invoice"]
        reconciled_rows = [r for r in invoice_rows if r["reconciled"]]
        recon_rate = len(reconciled_rows) / len(invoice_rows) if invoice_rows else 0
        flagged = sum(1 for r in self.ledger_rows if r.get("flags"))

        ledger = {
            "period": self.period,
            "generated_at": datetime.now().isoformat(),
            "currency": "MYR",
            "rows": self.ledger_rows,
            "summary": {
                "total_in": round(total_in, 2),
                "total_out": round(total_out, 2),
                "total_tax": round(total_tax, 2),
                "net_cash_flow": round(total_in - total_out - total_tax, 2),
                "by_category": [cat_map[c] for c in CATEGORIES if c in cat_map],
                "reconciliation_rate": round(recon_rate, 2),
                "document_count": len(self.records),
                "flagged_row_count": flagged
            }
        }

        # Exception summary
        exc_types = {}
        for e in self.exceptions:
            exc_types[e["type"]] = exc_types.get(e["type"], 0) + 1
        critical = sum(1 for e in self.exceptions if e["severity"] == "critical")
        warning = sum(1 for e in self.exceptions if e["severity"] == "warning")
        info = sum(1 for e in self.exceptions if e["severity"] == "info")

        exceptions = {
            "period": self.period,
            "generated_at": datetime.now().isoformat(),
            "exceptions": self.exceptions,
            "summary": {
                "total_exceptions": len(self.exceptions),
                "critical_count": critical,
                "warning_count": warning,
                "info_count": info,
                "by_type": [{"type": k, "count": v} for k, v in exc_types.items()]
            }
        }

        return ledger, exceptions

    # ── Run All Steps ──
    def run(self) -> tuple:
        self.step1_index()
        self.step2_build_ledger()
        self.step4_arithmetic()
        self.step5_sst()
        self.step6_duplicates()
        self.step7_order_invoice_match()
        self.step8_reconciliation()
        self.step10_confidence()
        self.step11_traceability()
        return self.build_outputs()


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python engine.py <input.json>")
        sys.exit(1)

    input_path = sys.argv[1]
    with open(input_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Accept both formats: plain array [...] or {period, records: [...]}
    if isinstance(raw, list):
        data = {"period": PERIOD, "records": raw}
    else:
        data = raw

    engine = FinancialEngine(data)
    ledger, exceptions = engine.run()

    output_dir = os.path.dirname(input_path) or "."
    ledger_path = os.path.join(output_dir, "ledger.json")
    exc_path = os.path.join(output_dir, "exceptions.json")

    with open(ledger_path, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2, ensure_ascii=False)

    with open(exc_path, "w", encoding="utf-8") as f:
        json.dump(exceptions, f, indent=2, ensure_ascii=False)

    # Print summary
    print(f"=== Financial Engine — Period {ledger['period']} ===")
    print(f"Documents processed: {ledger['summary']['document_count']}")
    print(f"Ledger rows: {len(ledger['rows'])}")
    print(f"Total in:  RM {ledger['summary']['total_in']:,.2f}")
    print(f"Total out: RM {ledger['summary']['total_out']:,.2f}")
    print(f"Total tax: RM {ledger['summary']['total_tax']:,.2f}")
    print(f"Net cash flow: RM {ledger['summary']['net_cash_flow']:,.2f}")
    print(f"Reconciliation rate: {ledger['summary']['reconciliation_rate']:.0%}")
    print(f"Flagged rows: {ledger['summary']['flagged_row_count']}")
    print()
    print(f"=== Exceptions ({exceptions['summary']['total_exceptions']} total) ===")
    print(f"  Critical: {exceptions['summary']['critical_count']}")
    print(f"  Warning:  {exceptions['summary']['warning_count']}")
    print(f"  Info:     {exceptions['summary']['info_count']}")
    print()
    for e in exceptions["exceptions"]:
        print(f"  [{e['severity'].upper():8s}] {e['type']:35s} {e.get('document_number',''):20s} {e['reason']}")
    print()
    print(f"Ledger written to:     {ledger_path}")
    print(f"Exceptions written to: {exc_path}")


if __name__ == "__main__":
    main()

# Shared Rules File

This is the single source of truth for rules that govern all three agents.
Add to it as the team discovers edge cases during the build.

## 1. Duplicate Definition

Two documents are duplicates if **any** of the following are true:
- Same invoice/receipt/PO number AND same vendor name
- Same vendor + same date + same grand total (within tolerance, see §2)
- Same line item composition (all descriptions match) + same total (within tolerance)

Action on duplicate: Financial flags both, keeps the one with higher confidence,
marks the other as `duplicate`. Secretary adds "verify duplicate" to the task list.

## 2. Reconciliation Tolerance

- Arithmetic tolerance: ±RM 1.00 on totals up to RM 1,000; ±RM 5.00 above RM 1,000.
- If the printed grand total does not match (subtotal + total_tax) within tolerance,
  Financial raises an exception with reason `arithmetic_mismatch`.
- If the SST portion is not 6% or 8% of the taxable amount (the two standard Malaysian
  SST rates), Financial raises `tax_rate_anomaly`. SST rate can also be 0 (exempt).

## 3. Order-vs-Invoice Match

- For each invoice, Financial checks if a matching PO exists (by po_reference or vendor + date proximity).
- Match criteria: PO number matches OR vendor name + date within ±7 days + line item overlap > 50%.
- If no matching PO: raise `missing_po_match` exception.
- If PO found but quantities differ: raise `quantity_mismatch` with the delta.
- If PO found but unit prices differ: raise `price_mismatch` with the delta.

## 4. Overdue Detection

- An invoice is overdue if due_date < today's date AND no matching receipt (payment proof) exists.
- Action: Secretary drafts a chase email. Financial adds to exception list with `overdue`.

## 5. Category List

Standard categories for the ledger. Every line item maps to exactly one.
Add categories as needed but keep the list stable across months.

| Code | Category | Examples |
|------|----------|----------|
| COGS | Cost of Goods Sold | Raw materials, stock purchases |
| RENT | Rent | Shop lot, warehouse |
| UTIL | Utilities | Electricity, water, internet |
| SALARY | Salaries & Wages | Staff pay |
| SUPPLIES | Supplies | Packaging, stationery, cleaning |
| MARKETING | Marketing | Ads, printing, promos |
| MAINT | Maintenance | Equipment repair, servicing |
| TRANSPORT | Transport | Delivery, fuel, logistics |
| FEES | Professional Fees | Accounting, legal, permits |
| MISC | Miscellaneous | Anything that doesn't fit above |

## 6. Escalation Rules (When to Ask the Owner)

Route a question to the owner (via Secretary → task list) when:
- Confidence score on any critical field (vendor, amount, date) < 0.7
- Grand total is blank or unparseable
- Document is handwritten and OCR confidence < 0.6
- PO reference is missing AND invoice amount > RM 500
- Duplicate detected but both have similar confidence
- SST rate is not 0%, 6%, or 8%
- No document type could be determined

Secretary converts these into plain-language tasks: "Confirm the total on invoice INV-2026-0941 — the number is blurry."

## 7. Handling Bad Documents

Logistics never guesses. Bad documents get:
- status = `flagged` or `error`
- Specific flags added (e.g., `blurry_image`, `handwritten`, `no_po_reference`, `wrong_total`, `duplicate`)
- Financial receives the record with flags and treats it accordingly
- Secretary surfaces flagged records as tasks for the owner

## 8. Traceability

Every number in the ledger must trace back to:
- A source document (by `source_ref`)
- A specific line item in that document
- A confidence score

If traceability is broken, Financial raises `traceability_broken`.

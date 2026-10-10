# Financial Agent — Handoff Package from Logistics

**Date**: 2026-10-10
**From**: Logistics Coordinator (Colt)
**To**: Financial Agent Teammate
**Output file**: `agents/logistics/output.json` (also on `colt` branch: https://github.com/ChewZuYenn/Dormathon-Banjir-Productivity/tree/colt)

---

## What You're Getting

34 structured JSON records extracted from the test document set. Each record is a self-contained document extraction with:
- All printed fields (vendor, date, line items, totals, tax)
- Per-field confidence scores (0.0–1.0)
- Status: `clean`, `flagged`, or `error`
- Flags describing specific issues
- `source_ref` linking back to the original document image

**Logistics recorded every total as printed. Logistics NEVER computed or validated any total. That is your job.**

---

## Summary

| Metric | Value |
|--------|-------|
| Total records | 34 |
| Clean | 26 |
| Flagged | 8 |
| Error | 0 |
| Invoices | 19 |
| Receipts | 10 |
| Purchase Orders | 5 |
| Clean total | RM 15,381.50 |
| Flagged total | RM 5,885.20 |
| Combined | RM 21,266.70 |

---

## Flagged Records — Need Your Attention

### 1. Wrong Total + Invalid SST Rate
**INV-2026-040 — Pulau Ketel Sdn Bhd — RM 45.70**
- Flags: `wrong_total`, `invalid_sst_rate`
- Subtotal: RM 400.00, Total tax: RM 40.00, Grand total (as printed): RM 45.70
- SST rate on the document: 10% (invalid — valid rates are 0%, 6%, 8%)
- **Your job**: Confirm the arithmetic error (400 + 40 = 440, not 45.70). Flag the invalid SST rate. This is a deliberately bad test document.

### 2. Missing PO References (6 invoices, 5 escalated)

| Invoice | Vendor | Amount | Escalated? |
|---------|--------|--------|------------|
| INV-2026-026 | Syarikat Makmal Sdn Bhd | RM 957.00 | Yes (> RM 500) |
| INV-2026-025 | Kedai Tanda Maju Mulia Sdn Bhd | RM 1,111.00 | Yes (> RM 500) |
| INV-2026-022 | Car Wipers Sdn Bhd | RM 1,534.50 | Yes (> RM 500) |
| INV-2026-024 | Rumahku Harum Sdn Bhd | RM 1,293.00 | Yes (> RM 500) |
| INV-2026-013 | Cermin Tuanku MY Sdn Bhd | RM 627.00 | Yes (> RM 500) |
| INV-2026-003 | Kasut Tentera Malaysia Sdn Bhd | RM 111.00 | No (< RM 500) |

**Your job**: These invoices have no PO reference. The 5 escalated ones (> RM 500) need owner approval to process without a PO. INV-2026-003 is under the RM 500 threshold so it can proceed but should still be noted.

### 3. Blurry Image
**INV-2026-036 — Lapop Tuning Sdn Bhd — RM 206.00**
- Flags: `blurry_image`
- 3 escalations from low confidence: vendor_name (0.60), invoice_date (0.65), line_items (0.60)
- **Your job**: This record was extracted from a blurry image. Confidence is below the 0.7 threshold on critical fields. Treat the numbers with caution — verify against the source image if possible.

---

## What You Need to Do

Per the shared rules (`rules/rules.md`) and your agent config (`agents/financial/agent_config.md`):

### Arithmetic Validation
For every invoice and order:
1. Sum line items (quantity x unit_price) → should match `subtotal`
2. Sum tax_amount across line items → should match `total_tax`
3. `subtotal + total_tax` → should match `grand_total`
4. Tolerance: ±RM 1 up to RM 1,000; ±RM 5 above RM 1,000

### SST Rate Validation
- Valid rates: **0%, 6%, 8%**
- If `tax_rate` is anything else → flag `invalid_sst_rate`
- Verify `tax_amount` = `unit_price * quantity * tax_rate / 100` per line item

### Order-vs-Invoice Matching
- Match invoices to purchase orders by `po_reference` ↔ `po_number`
- Check that line items, quantities, and prices match
- Flag mismatches

### Duplicate Detection
- Two records with same vendor + same amount (within tolerance) → `possible_duplicate`
- Check across all 34 records

### Overdue Detection
- If `due_date` is present and < today → flag `overdue`
- If no `due_date` on invoice → flag `no_due_date`

### Categorisation
Assign each record to one of:
`COGS, RENT, UTIL, SALARY, SUPPLIES, MARKETING, MAINT, TRANSPORT, FEES, MISC`

### Ledger Output
Build a ledger with one row per record:
- Date, vendor, document number, category, amount, tax, status, flags
- Include a reconciliation summary at the bottom

---

## Output Format (What You Receive)

The `output.json` file is a JSON array. Each record has this shape:

### Invoice
```json
{
  "document_type": "invoice",
  "vendor_name": "Pulau Ketel Sdn Bhd",
  "vendor_sst_id": "W10-2001-220004",
  "invoice_number": "INV-2026-040",
  "invoice_date": "2026-10-02",
  "due_date": "2026-10-17",
  "po_reference": "PO-PA-26-0002",
  "line_items": [
    {"description": "Big canvas", "quantity": 30, "unit_price": 10.0, "tax_amount": 0.0, "tax_rate": null},
    {"description": "Stiker label", "quantity": 5, "unit_price": 5.0, "tax_amount": 0.0, "tax_rate": null}
  ],
  "subtotal": 400.0,
  "total_tax": 40.0,
  "grand_total": 45.70,
  "currency": "MYR",
  "source_ref": "invoice_001.png",
  "confidence": {"vendor_name": 0.95, "invoice_number": 0.95, ...},
  "status": "flagged",
  "flags": ["invalid_sst_rate", "wrong_total"]
}
```

### Receipt
```json
{
  "document_type": "receipt",
  "vendor_name": "...",
  "receipt_number": "...",
  "receipt_date": "2026-10-05",
  "payment_method": "cash|bank_transfer|card|...",
  "amount": 150.00,
  "invoice_reference": "INV-2026-001",
  "currency": "MYR",
  "source_ref": "receipt_001.png",
  "confidence": {...},
  "status": "clean",
  "flags": []
}
```

### Purchase Order
```json
{
  "document_type": "order",
  "po_number": "PO-PA-26-0002",
  "po_date": "2026-09-28",
  "vendor_name": "...",
  "line_items": [...],
  "grand_total": 440.00,
  "currency": "MYR",
  "source_ref": "order_001.png",
  "confidence": {...},
  "status": "clean",
  "flags": []
}
```

---

## Schema Version

Current schemas are labeled `arbitrary_v1`. If the exact schema is delivered, the JSON files in `agents/logistics/schemas/` will be swapped. The output format will stay the same — only field names or required fields may change.

---

## Test Document Images

The 4 PNG pages from the original PDF are at:
- `test-documents/extracted/page_01.png`
- `test-documents/extracted/page_02.png`
- `test-documents/extracted/page_03.png`
- `test-documents/extracted/page_04.png`

Use these to visually verify any flagged records if needed.

---

## Contact

Questions about specific extractions? Check `agents/logistics/process_test_docs.py` — it contains the full transcription of all 34 documents with extraction data. The `source_ref` field in each record maps to the document image filename.

**Hard boundary reminder**: Logistics owns documents. Financial owns numbers. Don't ask Logistics to recompute a total — ask them to re-read a document if a field looks wrong.

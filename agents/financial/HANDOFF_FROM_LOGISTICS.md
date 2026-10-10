# Financial Agent — Handoff Package from Logistics

**Date**: 2026-10-10 (re-extracted from the source images the same day)
**From**: Logistics Coordinator (Colt)
**To**: Financial Agent Teammate
**Output file**: `agents/logistics/output.json`

---

## What You're Getting

36 structured JSON records, one per document on the 4 pages in `test-documents/extracted/`. Each record has:
- All printed fields (vendor, date, line items, subtotal, SST, total)
- Per-field confidence scores (0.0–1.0)
- Status: `clean`, `flagged`, or `error`
- Flags describing specific issues, plus a `notes` line when the page itself is contradictory or unreadable
- `source_ref` — the path of that document's own image, e.g. `test-documents/invoices/p01_01.png` (page 1, document 1)

**Logistics recorded every figure as printed. Logistics NEVER computed or validated any total. That is your job.**

`output.json` is a bare JSON array — `engine.py` accepts it directly:

```bash
cp agents/logistics/output.json agents/financial/test/logistics_output.json
python agents/financial/engine.py agents/financial/test/logistics_output.json   # writes test/ledger.json + test/exceptions.json
python agents/financial/test/test_engine.py                                     # end-to-end check
```

---

## Summary

| Metric | Value |
|--------|-------|
| Total records | 36 |
| Invoices | 20 (INV-2026-020 appears twice) |
| Receipts | 11 (all purchases — none references an invoice) |
| Purchase Orders | 5 |
| Clean | 26 |
| Flagged | 10 |
| Error | 0 |

Things that hold for the whole set:
- **Every document prints `SST 10%`.** SST is printed once per document, not per line, so line `tax_amount` is `null` and the document carries `tax_rate: 10`.
- **No invoice prints a due date** (`due_date: null`).
- **Every document is dated October 2026** (02–26 Oct). PO delivery dates run to Nov 2026.

---

## Flagged Records — Need Your Attention

| Record | Flag | What is on the page |
|--------|------|---------------------|
| INV-2026-016 (Puteri Kraf) | `conflicting_values` | 400.00 + SST 40.00, but prints `TOTAL AMOUNT: RM 425.00` **and** a large `RM45.70` |
| PO-2026-A05 (Peralatan Keselamatan) | `conflicting_values` | Subtotal 2100.00, `SST 10%: RM21.00`, `Grand Total: RM2310.00`, then a large `RM2100.00` |
| PO-2026-A04 (Taman Hijau) | `conflicting_values` | `Grand Total: RM1309.00`, then a large `RM1390.00` |
| PO-2026-A06 (Tekno Supply) | `conflicting_values` | An unlabelled `49.00` under the subtotal |
| INV-2026-033 (Buku Nusa) | `conflicting_values` | SST printed as both `9.50` and `9.00` |
| INV-2026-029 (Warisan Supply) | `handwritten` | Number, vendor, date and PO ref handwritten (legible) |
| INV-2026-028 (Seri Murni) | `no_po_reference`, `unreadable_field` | PO ref `TIADA / NOT PROVIDED`; unit price printed `12.0ai`. RM 957.00, so escalated (> RM 500) |
| INV-2026-024 (Rumah Kaca) | `unreadable_field` | Unit prices printed `120ping` and `18.tiub` |
| INV-2026-012 (Sri Jaya) | `blurry_image` | Tel and SSM blurred; critical fields readable |
| INV-2026-036 (Lampu Terang) | `blurry_image` | Low-res scan; `Mentol LED / LED bulb` printed twice, second line blank qty / RM 0.00 |

Not flagged by Logistics, for you to catch:
- **Duplicate:** INV-2026-020 (Mesin Teknik, RM 1111.00) is on page 2 and page 3.
- **Invoice vs PO quantities:** INV-2026-032 vs PO-2026-A06 (Tekno Supply) and INV-2026-033 vs PO-2026-A07 (Buku Nusa). The invoices' PO refs (`PO-TS-1301`, `PO-BN-1302`) don't match the PO numbers, so these pair up by vendor + date.
- INV-2026-026 pairs with PO-2026-A04 the same way (`Gunting dahan` on the invoice, `Cunting dahan` on the PO).

---

## What You Need to Do

Per the shared rules (`rules/rules.md`) and your agent config (`agents/financial/agent_config.md`):

### Arithmetic Validation
For every invoice, order and receipt:
1. Sum line items (quantity x unit_price; receipt lines carry `amount`) → should match `subtotal`
2. `subtotal + total_tax` → should match `grand_total` (receipts: `subtotal + tax_amount` → `amount`)
3. Tolerance: ±RM 1 up to RM 1,000; ±RM 5 above RM 1,000

### SST Rate Validation
- Valid rates per `rules/rules.md`: **0%, 6%, 8%**
- Check the printed `tax_rate` and `total_tax / subtotal` against each other and against the valid rates

### Order-vs-Invoice Matching
- Match invoices to purchase orders by `po_reference` ↔ `po_number`, else vendor + date + line overlap
- Check that line items, quantities, and prices match
- Flag mismatches

### Duplicate Detection
- Same document number + vendor, or same vendor + date + amount (within tolerance)

### Overdue Detection
- If `due_date` is present and < today → flag `overdue`
- No invoice in this set has a due date

### Categorisation
Assign each line to one of:
`COGS, RENT, UTIL, SALARY, SUPPLIES, MARKETING, MAINT, TRANSPORT, FEES, MISC`

---

## Output Format (What You Receive)

### Invoice
```json
{
  "document_type": "invoice",
  "vendor_name": "Puteri Kraf Sdn Bhd",
  "invoice_number": "INV-2026-016",
  "invoice_date": "2026-10-07",
  "due_date": null,
  "po_reference": "PO-PK-9900",
  "line_items": [
    {"description": "Beg canvas / Canvas bag", "quantity": 30, "unit_price": 10.0, "tax_amount": null, "tax_rate": null},
    {"description": "Stiker label / Label sticker", "quantity": 20, "unit_price": 5.0, "tax_amount": null, "tax_rate": null}
  ],
  "subtotal": 400.0,
  "total_tax": 40.0,
  "tax_rate": 10,
  "grand_total": 425.0,
  "currency": "MYR",
  "source_ref": "test-documents/invoices/p01_01.png",
  "confidence": {"vendor_name": 0.95, "invoice_number": 0.95, "invoice_date": 0.95, "po_reference": 0.95, "line_items": 0.92, "grand_total": 0.5, "total_tax": 0.95},
  "status": "flagged",
  "flags": ["conflicting_values"],
  "notes": "Two totals printed: 'TOTAL AMOUNT: RM 425.00' and a large 'RM45.70' below it. grand_total records the labelled TOTAL AMOUNT."
}
```

### Receipt
```json
{
  "document_type": "receipt",
  "vendor_name": "Kedai Runcit Aman",
  "receipt_number": "REC-009",
  "receipt_date": "2026-10-02",
  "payment_method": null,
  "line_items": [
    {"description": "Air mineral / Mineral water (24 botol)", "amount": 32.0},
    {"description": "Tisu / Tissue box", "amount": 15.0}
  ],
  "subtotal": 47.0,
  "tax_amount": 4.7,
  "tax_rate": 10,
  "amount": 51.7,
  "invoice_reference": null,
  "currency": "MYR",
  "source_ref": "test-documents/receipts/p02_01.png",
  "confidence": {"vendor_name": 0.95, "receipt_date": 0.95, "amount": 0.95},
  "status": "clean",
  "flags": []
}
```

A receipt is a purchase (`out`) unless it carries `"direction": "in"` (issued by the business — a sale). None in this set do.

### Purchase Order
```json
{
  "document_type": "order",
  "po_number": "PO-2026-A06",
  "po_date": "2026-10-25",
  "vendor_name": "Tekno Supply Sdn Bhd",
  "buyer_name": "Bahagian Pentadbiran",
  "delivery_date": "2026-11-25",
  "line_items": [
    {"description": "Kabel USB / USB cable", "quantity": 50, "unit_price": 3.0, "tax_amount": null, "tax_rate": null},
    {"description": "Penanda / Marker pen", "quantity": 40, "unit_price": 2.0, "tax_amount": null, "tax_rate": null}
  ],
  "subtotal": 230.0,
  "total_tax": 23.0,
  "tax_rate": 10,
  "grand_total": 253.0,
  "currency": "MYR",
  "source_ref": "test-documents/orders/p04_03.png",
  "confidence": {"po_number": 0.95, "po_date": 0.95, "vendor_name": 0.95, "line_items": 0.92, "grand_total": 0.95},
  "status": "flagged",
  "flags": ["conflicting_values"],
  "notes": "An unlabelled '49.00' is printed under the subtotal."
}
```

---

## Schema Version

Current schemas are labeled `arbitrary_v1`. Fields added in this pass, all optional: document-level `tax_rate` and `notes` (all types); `subtotal`, `line_items` and `direction` (receipts). Line `tax_amount` and invoice line `quantity` may be `null`.

---

## Test Document Images

- Full pages: `test-documents/extracted/page_01.png` … `page_04.png`
- One image per document: `test-documents/{invoices,receipts,orders}/pPP_NN.png` — this is each record's `source_ref`

---

## Contact

Questions about specific extractions? Check `agents/logistics/process_test_docs.py` — it holds the transcription of all 36 documents, in page order, with a note on every irregular one.

**Hard boundary reminder**: Logistics owns documents. Financial owns numbers. Don't ask Logistics to recompute a total — ask them to re-read a document if a field looks wrong.

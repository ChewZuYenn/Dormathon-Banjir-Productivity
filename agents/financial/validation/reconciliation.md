# Validation Rules: Reconciliation

## Arithmetic Check
- Compare printed grand_total to (subtotal + total_tax)
- Tolerance: ±RM 1.00 up to RM 1,000; ±RM 5.00 above RM 1,000
- Mismatch → raise `arithmetic_mismatch` exception

## SST Rate Check
- Valid SST rates in Malaysia: 0% (exempt), 6%, 8%
- If tax_amount / taxable_amount is not one of these → raise `tax_rate_anomaly`
- If SST is listed as inclusive, back-calculate and verify

## Order-vs-Invoice Match
- For each invoice, check if a matching PO exists
- Match criteria: po_reference matches OR vendor + date ±7 days + line overlap > 50%
- No matching PO → raise `missing_po_match`
- Quantities differ → raise `quantity_mismatch` with delta
- Unit prices differ → raise `price_mismatch` with delta

## Overdue Detection
- Invoice overdue if due_date < today AND no matching receipt exists
- Action: Secretary drafts chase email; Financial adds to exception list

## Traceability
- Every ledger number must trace to source_ref + line item + confidence score
- Broken trace → raise `traceability_broken`

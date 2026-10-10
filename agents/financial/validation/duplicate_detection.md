# Validation Rules: Duplicate Detection

## Definition
Two documents are duplicates if ANY of the following are true:
1. Same invoice/receipt/PO number AND same vendor name
2. Same vendor + same date + same grand total (within tolerance)
3. Same line item composition (all descriptions match) + same total (within tolerance)

## Tolerance
- ±RM 1.00 on totals up to RM 1,000
- ±RM 5.00 above RM 1,000

## Action
- Flag both records
- Keep the one with higher confidence
- Mark the other as `duplicate`
- Secretary adds "verify duplicate" to the task list

## Edge Cases
- Different invoice numbers but same content = likely re-issued invoice, flag both
- Same PO number, different vendor = not a duplicate (different suppliers)
- Partial overlap (some line items match) = not a duplicate, but flag for review

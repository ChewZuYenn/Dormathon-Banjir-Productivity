# Expense Categories

Every line item in the ledger maps to exactly one category.
Keep this list stable across months for month-over-month comparison.

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

## Categorisation Rules
- Default to COGS for any line item with quantity > 0 that looks like inventory
- RENT and UTIL are usually fixed monthly amounts from the same vendor
- If a line item description doesn't clearly map, default to MISC and flag for review
- Secretary surfaces unclear categorisations as tasks

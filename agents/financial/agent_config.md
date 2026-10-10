# Agent: Financial

## Role
Builds the ledger from Logistics records. Reconciles. Raises exceptions.

## Build Priority: SECOND (but most judge points live here)

If anyone is idle, they help this agent.

## Responsibilities

### P0
- [ ] Ledger built from the Logistics records
- [ ] Validation — duplicates, arithmetic, order-vs-invoice match, overdue
- [ ] Exception list with a reason per item

### P1
- [ ] Every number traceable to its source document

### P2
- [ ] A short action list, each item derived from a number in the ledger

## Cut
Regulatory forms and generic financial advice. Both are unverifiable in a 3-minute pitch.

## Input
Structured records from Logistics (never raw documents).

## Output
- Reconciled ledger (cash in, cash out, by category)
- Exception list (each with reason + source document reference)
- Optional: action items derived from ledger numbers

## Validation Rules
See `validation/` folder and shared `rules/rules.md`.

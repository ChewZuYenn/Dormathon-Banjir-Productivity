# Dormathon Banjir Productivity

Three AI agents on WorkBuddy that take a single prompt and close a micro-business's month end to end.

## The Demo

**Prompt:** "Close out September."

Then, with no further input:
1. **Secretary** reads the goal, writes the plan on screen, dispatches.
2. **Logistics** collects and organises ~40 documents — invoices, receipts, orders.
3. **Financial** builds the ledger, reconciles, raises exceptions.
4. **Secretary** turns exceptions into tasks and reports to the front end.

**Output:** a reconciled ledger, an exception list with a reason per item, and two drafted chase emails awaiting approval. Every number traces back to a source document.

## Hard Boundary

Logistics owns documents, Financial owns numbers. Logistics hands over structured records and **never computes a total**.

## Team

| Role | Owner | Status |
|------|-------|--------|
| Logistics Coordinator | @Colt Tan | In progress |
| Financial Agent | TBD | In progress |
| Secretary Agent | TBD | Stub phase |
| Frontend | TBD | P0 components |
| Test Documents | TBD | Generating 40 docs |

## Timeline (Oct 10–12, 2026)

| Gate | Target |
|------|--------|
| 15:00 Sat | Workspace set up, first 15 test documents ready |
| 18:00 Sat | 1 document in → 1 ledger row out |
| 23:00 Sat | All 40 documents run, validation working |
| 01:00 Sun | Record backup demo video |
| 04:00 Sun | Hard stop on new features |
| 06:00 Sun | Slides done, rehearse to 3 min |
| 08:00 Sun | Submitted |

## Project Structure

```
.
├── agents/
│   ├── logistics/          # Document extraction agent (build first)
│   │   ├── schemas/        # Extraction schemas per document type
│   │   └── agent_config.md
│   ├── financial/          # Ledger, reconciliation, exceptions
│   │   ├── validation/     # Duplicate, arithmetic, matching rules
│   │   ├── categories.md
│   │   └── agent_config.md
│   └── secretary/         # Plan, dispatch, report, chase emails
│       ├── templates/
│       └── agent_config.md
├── frontend/              # Visual layer for judges
│   ├── components/
│   └── index.html
├── test-documents/        # ~40 docs (20 invoices, 10 receipts, 10 orders, 5 bad)
├── rules/                 # Shared rules file (duplicate, tolerance, categories, escalation)
├── slides/                # Pitch slides (PDF for submission)
└── docs/                  # Architecture and design docs
```

## Out of Scope

Marketing, customer feedback, role dropdown, regulatory forms, login and user accounts.

# Architecture

## Overview

Three AI agents running on WorkBuddy, coordinated by a Secretary, with a frontend that makes their work visible to judges.

```
User types "Close out September"
        |
        v
  +------------+
  | Secretary  |  reads goal, writes plan, dispatches
  +------------+
        |
   +----+----+
   |         |
   v         v
+----------+  +----------+
| Logistics|  | Financial|
| (docs)   |  | (numbers)|
+----------+  +----------+
   |         |
   | records |
   +-------->|
             |
        +----+----+
        | Financial|  builds ledger, validates, raises exceptions
        +----------+
             |
        +----+----+
        | Secretary|  exceptions → tasks, drafts emails, final report
        +----------+
             |
             v
        +----------+
        | Frontend |  visible to judges: plan, agent status, tasks, ledger, emails
        +----------+
```

## Hard Boundary

Logistics owns documents. Financial owns numbers. Logistics hands over structured records and **never computes a total**. Financial never reads raw documents — only structured records from Logistics.

## Agent Definitions

Each agent is a separate named unit on WorkBuddy — not one long prompt. A judge can see named units in a trace.

| Agent | Input | Output | Build Order |
|-------|-------|--------|-------------|
| Logistics | ~40 documents (mixed formats) | Structured records (JSON per schema) | First |
| Financial | Structured records from Logistics | Reconciled ledger, exception list | Second |
| Secretary | Goal from user + exceptions from Financial | Plan, task list, chase emails, final report | Stub early, deepen last |

## Frontend Components (by priority)

| Priority | Component | Purpose |
|----------|-----------|---------|
| P0 | Prompt bar | Single entry point — proves "one prompt → one goal" |
| P0 | Plan panel | Secretary's plan shown before work starts — agentic proof |
| P0 | Three agent panels | One per agent: idle/working/done + current step |
| P1 | Task list | Exceptions become ticked items — end-to-end delivery |
| P1 | Result view | Ledger and exception list, openable — verifiable output |
| P2 | Feedback / approval | Approve drafted email, answer low-confidence question |
| P2 | Run log | Tool calls as they happen — good for Q&A |

## Differentiator

Depth, not the platform. Every Track 2 team is on WorkBuddy.
What a generic prompt won't produce:
- Schemas that handle real Malaysian invoice formats and SST lines
- Validation thresholds we chose and can defend
- A categorisation scheme that stays consistent across months
- Handling for blurry photos, handwriting, missing PO references

## Out of Scope
Marketing, customer feedback, role dropdown, regulatory forms, login and user accounts.

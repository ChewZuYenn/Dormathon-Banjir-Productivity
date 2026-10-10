# Secretary Agent

## Trigger
Activate this skill when the user asks to:
- Plan, dispatch, or coordinate the month-end closing pipeline
- Convert Financial exceptions into plain-language tasks
- Draft chase emails for overdue invoices
- Generate a final report (cash flow, categories, top 3 actions)
- Run the Secretary pipeline or process exceptions into tasks
- Close month-end books (Secretary phase: plan, tasks, emails, report)

Keywords: secretary, plan, dispatch, task, chase email, overdue, final report, close out, reconcile, exception, cash flow, category breakdown, month-end closing, pipeline coordinator, approve email

## Role
You are the **Secretary Agent** in a three-agent month-end closing system for a Malaysian micro-business. You are the orchestrator — you read the goal, write the plan, dispatch to Logistics and Financial, receive exceptions, convert them to plain-language tasks, draft chase emails for overdue items, and generate the final report.

## Hard Boundaries
- **Never extract documents.** That is Logistics's job. You only receive structured `DocumentInfo` from Logistics.
- **Never validate arithmetic or SST.** That is Financial's job. You only receive `ExceptionEvent` objects from Financial.
- **Never send an email without owner approval.** Chase emails are always drafted as `status: draft`. The owner must approve before sending. Human-in-the-loop is absolute.
- **Never skip the plan.** Every run starts with a plan. The plan is what the frontend displays first — judges watch the plan panel.
- **Never invent exceptions.** You process only the exceptions Financial gives you. If Financial sends none, you report "no exceptions found" and still generate the report.

## Pipeline Overview

```
User goal (e.g. "Close out September")
    |
    v
P0: Planner  --------> Plan (phases: Logistics -> Financial -> Secretary)
    |
    v
Dispatch to Logistics --> DocumentInfo[] (structured records)
    |
    v
Dispatch to Financial --> ExceptionEvent[] (validation results)
    |
    v
P1: TaskGenerator -----> Task[] (plain-language tasks with priorities)
    |
    v
P2: EmailDrafter ------> ChaseEmail[] (draft, awaiting approval)
    |
    v
P1: Reporter ----------> FinalReport (cash in/out, categories, top 3 actions)
    |
    v
PipelineResult (plan + tasks + emails + report)
```

## Priority Assignment

| Priority | Event Type | Reason |
|----------|------------|--------|
| P1_CRITICAL | duplicate | Potential double payment — highest urgency |
| P2_HIGH | escalation | Management approval needed (S6 triggers) |
| P2_HIGH | overdue | Chase email needed — payment past due |
| P3_MEDIUM | flagged (confidence < 0.70) | Document quality issue, review needed |
| P4_LOW | flagged (confidence >= 0.70) | Borderline, informational |

### Duplicate Precedence Rule
If an invoice has both `duplicate` AND `overdue` flags, **duplicate takes precedence** (P1 over P2). Exceptions are sorted so duplicates are processed first.

### Escalation Amount Override
If an escalation event has `amount >= RM 10,000`, priority is bumped to `P1_CRITICAL` regardless of the default `P2_HIGH`.

## Edge Cases
- OCR confidence **exactly 0.70**: OK, proceed normally (not flagged)
- OCR confidence **below 0.70**: task gets `P3_MEDIUM`
- Amount **= RM 500**: does NOT trigger escalation (below RM 10,000 threshold)
- Same invoice with duplicate + overdue: duplicate wins (higher priority)
- No exceptions from Financial: report "0 exceptions", still generate report with cash flow from documents

## Chase Email Rules
- Secretary drafts chase emails **only** for items where Financial flagged `overdue`
- Draft status is always `draft` — never `approved` or `sent`
- Owner can approve (send) or reject (dismiss) from the UI
- Secretary **NEVER** sends without approval — human-in-the-loop is absolute
- Email body follows the standard template (see Output Formats below)
- Recipient email is a placeholder if vendor contact is unknown

## Input Schemas

### ExceptionEvent (from Financial Agent)
```json
{
  "event_type": "overdue | duplicate | escalation | flagged",
  "invoice_number": "INV-2026-001",
  "vendor_name": "Tech Supplies Sdn Bhd",
  "amount": 12500.00,
  "currency": "MYR",
  "invoice_date": "2026-09-15",
  "due_date": "2026-10-05",
  "details": "Human-readable description of the issue",
  "duplicate_of": "INV-2026-001 (original)",
  "escalation_reason": "Large amount exceeds threshold",
  "escalation_code": "LARGE_AMOUNT",
  "flag_reason": "Low OCR confidence",
  "confidence": 0.65
}
```

Required fields: `event_type`, `invoice_number`, `vendor_name`, `amount`, `details`.
Optional fields depend on event type:
- `duplicate`: includes `duplicate_of`
- `escalation`: includes `escalation_reason`, `escalation_code`
- `flagged`: includes `flag_reason`, `confidence`
- `overdue`: includes `due_date`

### DocumentInfo (from Logistics Agent)
```json
{
  "doc_id": "DOC-001",
  "file_name": "invoice_tech_supplies.pdf",
  "doc_type": "invoice",
  "vendor_name": "Tech Supplies Sdn Bhd",
  "invoice_number": "INV-2026-001",
  "invoice_date": "2026-09-15",
  "grand_total": 12500.00,
  "currency": "MYR",
  "line_items": [
    {"description": "Laptops x5", "amount": 10000, "category": "IT"}
  ],
  "confidence": 0.95,
  "quality_flags": []
}
```

## Output Schemas

### Plan (P0)
```json
{
  "goal": "Close out September",
  "phases": [
    {
      "phase": 1,
      "agent": "Logistics",
      "action": "Collect and classify all documents...",
      "status": "pending"
    },
    {
      "phase": 2,
      "agent": "Financial",
      "action": "Build ledger, validate arithmetic, raise exceptions...",
      "status": "pending"
    },
    {
      "phase": 3,
      "agent": "Secretary",
      "action": "Convert exceptions to tasks, draft emails, generate report...",
      "status": "pending"
    }
  ],
  "created_at": "2026-10-10T17:00:00",
  "total_phases": 3
}
```

Plan variants based on goal keyword:
- **"overdue" or "chase"**: 2-phase (Financial -> Secretary), skips Logistics
- **"reconcile" or "audit"**: 3-phase (Logistics -> Financial -> Secretary), reconciliation focus
- **Default**: 3-phase standard pipeline (Logistics -> Financial -> Secretary)

### Task (P1)
```json
{
  "task_id": "TASK-0001",
  "title": "VERIFY duplicate invoice: INV-2026-001 (RM 12500.00)",
  "description": "Invoice INV-2026-001 from Tech Supplies Sdn Bhd appears to be a duplicate...",
  "priority": 1,
  "event_type": "duplicate",
  "invoice_number": "INV-2026-001",
  "vendor_name": "Tech Supplies Sdn Bhd",
  "amount": 12500.00,
  "action_required": "Confirm which invoice is the original. Void the duplicate...",
  "status": "pending",
  "created_at": "2026-10-10T17:00:00",
  "related_email_id": null
}
```

Priority values: 1=P1_CRITICAL, 2=P2_HIGH, 3=P3_MEDIUM, 4=P4_LOW.
Status values: pending, in_progress, done, cancelled.

### ChaseEmail (P2)
```json
{
  "email_id": "EMAIL-0001",
  "to": "accounts@techsupplies.com.my",
  "cc": null,
  "subject": "Outstanding Payment — Invoice INV-2026-001 — Tech Supplies Sdn Bhd",
  "body": "Dear Sir/Madam,\n\nWe are writing regarding...",
  "status": "draft",
  "related_invoice": "INV-2026-001",
  "related_task_id": "TASK-0001",
  "created_at": "2026-10-10T17:00:00"
}
```

Email status lifecycle: `draft` -> `approved` (owner approves) -> `sent` (system sends). Or `draft` -> `rejected` (owner dismisses).

### FinalReport (P1)
```json
{
  "goal": "Close out September",
  "period": "September 2026",
  "cash_in": 15000.00,
  "cash_out": 20800.00,
  "net_cash": -5800.00,
  "categories": [
    {"category": "RAW", "total": 10000.00, "count": 2},
    {"category": "RENT", "total": 3500.00, "count": 1},
    {"category": "MKT", "total": 4800.00, "count": 1}
  ],
  "top_3_actions": [
    "URGENT: Verify duplicate invoice INV-2026-001 (RM 12,500)",
    "Review and approve 1 chase email(s)",
    "Address 1 high-priority escalation task(s)"
  ],
  "total_exceptions": 4,
  "tasks_generated": 4,
  "chase_emails_drafted": 1,
  "chase_emails_approved": 0,
  "generated_at": "2026-10-10T17:00:00"
}
```

### PipelineResult (aggregate)
```json
{
  "plan": { ... },
  "tasks": [ ... ],
  "chase_emails": [ ... ],
  "final_report": { ... },
  "exceptions_processed": 4,
  "warnings": []
}
```

## Shared Rules Reference (S1-S8)

| Rule | Secretary Application |
|------|----------------------|
| S1: Duplicate detection | P1_CRITICAL task — "Verify which is original, void the other" |
| S2: Reconciliation tolerance | Not directly used (Financial's job) |
| S3: PO matching | Not directly used (Financial's job) |
| S4: Overdue payments | P2_HIGH task + draft chase email |
| S5: Category codes | Used in FinalReport breakdown (10 categories) |
| S6: Escalation triggers | P2_HIGH task (P1 if >= RM 10,000) — surface to management |
| S7: Bad document flags | P3_MEDIUM task (confidence < 0.70) — review needed |
| S8: Confidence threshold | 0.70 — below = flagged, exactly 0.70 = OK |

Category codes for FinalReport:
RAW (Raw Materials), RENT (Rent & Utilities), SAL (Salaries & Wages), MKT (Marketing & Advertising), LOG (Logistics & Shipping), MNT (Maintenance & Repairs), OFC (Office Supplies), IT (IT & Software), PRO (Professional Services), TAX (Taxes & Levies)

## Tolerance Rules (for reference)
- Reconciliation: +/-RM 1 for amounts < RM 100, +/-RM 5 for amounts >= RM 100
- Escalation: single invoice >= RM 10,000 triggers LARGE_AMOUNT escalation
- Missing PO: purchases >= RM 500 without PO reference trigger escalation
- Overdue: no grace period — due date is the deadline

## CLI Invocation

### Demo mode (sample data)
```bash
cd agents/secretary
python run.py --demo
```

### Process Financial exceptions
```bash
cd agents/secretary
python -m src.cli --goal "Close out September" --exceptions exceptions.json --json
```

### Process both documents and exceptions
```bash
cd agents/secretary
python -m src.cli --goal "Reconcile October" --documents docs.json --exceptions exceptions.json
```

### Full pipeline (Logistics -> Financial -> Secretary)
When wired as a WorkBuddy skill, the Secretary orchestrates the full pipeline:
1. User says "Close out September"
2. Secretary generates plan (3 phases)
3. Secretary dispatches to Logistics (skill triggers, extracts documents -> output.json)
4. Secretary dispatches to Financial (skill triggers, runs engine -> ledger.json + exceptions.json)
5. Secretary reads exceptions.json, converts to tasks
6. Secretary drafts chase emails for overdue items
7. Secretary generates final report
8. Secretary returns PipelineResult as JSON

### Python API
```python
from agents.secretary.src.secretary import Secretary
from agents.secretary.src.models import ExceptionEvent, DocumentInfo

secretary = Secretary()
result = secretary.run(
    goal="Close out September",
    exceptions=financial_exceptions,  # list[ExceptionEvent]
    documents=logistics_documents,   # list[DocumentInfo]
)
print(secretary.format_result(result))   # human-readable
print(secretary.result_to_json(result))  # JSON
```

## Financial -> Secretary Handoff

The Financial agent outputs `exceptions.json` containing an array of exception objects. The Secretary reads this file and processes each exception:

1. Parse exceptions from `exceptions.json`
2. Sort by priority (duplicates first)
3. Convert each to a Task with appropriate priority and action_required text
4. For `overdue` events, draft a ChaseEmail linked to the task
5. Generate FinalReport from documents + tasks + emails

The Secretary expects Financial's exceptions to use these `event_type` values:
- `overdue` — payment due date passed, no payment record
- `duplicate` — same vendor + amount + invoice number detected
- `escalation` — S6 rule triggered (large amount, tax discrepancy, missing PO, etc.)
- `flagged` — document quality issue or low OCR confidence

If Financial sends an unrecognized event_type, the Secretary creates a P3_MEDIUM task with "Manual review required" action.

## Schema Swapping
Schemas are loaded at runtime from `agents/secretary/schemas/`. Replace the JSON files to change the output format without code changes. Current schemas are version `arbitrary_v1`.

## Configuration
Business-specific constants (name, email, currency, thresholds) are in `agents/secretary/src/config.py`. Update these to match the target business.

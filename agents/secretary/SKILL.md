# Secretary Agent

> Task Coordinator for a 3-agent document processing pipeline (Logistics -> Financial -> Secretary), designed for Malaysian SME invoice/receipt/PO processing.

---

## Triggers

Load this skill when the user mentions any of the following:

**Core pipeline:**
- secretary agent, secretary skill
- task coordinator, chase email, overdue invoice
- invoice processing, receipt processing, PO matching
- exception handling, financial exceptions
- document processing pipeline
- cash flow report, spending summary, category breakdown
- "close out" + month (e.g. "close out September")

**Gmail crawler:**
- gmail fetch, gmail crawler, email auto-fetch
- auto-fetch invoices, auto-fetch emails
- scan gmail for invoices, gmail invoice crawler

**Tier 1 features:**
- vendor database, vendor master, vendor list, new vendor
- audit log, audit trail, traceability
- export csv, export json, export markdown, export journal
- double-entry journal, accounting export
- reply tracker, chase email reply, vendor reply
- payment confirmed, disputed invoice
- scheduler, scheduled run, monthly run, weekly run

---

## Role

The Secretary is the **final agent** in a 3-agent pipeline:

1. **Logistics** — OCR + extracts structured data from invoice/receipt/PO documents
2. **Financial** — reconciles documents against the ledger, raises exception events
3. **Secretary** — converts exceptions into plain-language tasks, drafts chase emails, generates final reports, and coordinates the owner's approval workflow

The Secretary **never sends emails without owner approval** (human-in-the-loop).

---

## Boundaries

- **Does NOT** perform OCR or document scanning (that's Logistics)
- **Does NOT** reconcile against the ledger (that's Financial)
- **Does NOT** send emails directly — only drafts them for owner approval
- **Does NOT** make payments or move money
- **Does NOT** modify the ledger — it reads exceptions and produces actionable artifacts (tasks, emails, reports)

---

## Project Structure

```
secretary-agent/
├── src/
│   ├── __init__.py
│   ├── models.py             # All Pydantic data models
│   ├── config.py             # Business config + shared rules (S1-S8)
│   ├── planner.py            # P0: Plan generation
│   ├── task_generator.py     # P1: Exception -> task conversion
│   ├── email_drafter.py      # P2: Chase email approval workflow
│   ├── reporter.py           # P1: Final report generation
│   ├── secretary.py          # Main orchestrator
│   ├── cli.py                # CLI entry point
│   ├── gmail_crawler.py      # Gmail email auto-fetch module
│   ├── vendor_manager.py     # Vendor master database
│   ├── audit_logger.py       # Audit log (S8 traceability)
│   ├── exporter.py           # CSV/JSON/Markdown/Journal export
│   ├── reply_tracker.py      # Chase email reply detection
│   └── scheduler.py          # Scheduled pipeline runs
├── prompts/
│   ├── system_prompt.md
│   ├── chase_email.txt
│   ├── task_templates.json
│   ├── report_template.md
│   └── gmail_setup_guide.md
├── schemas/
│   ├── exception_event.json
│   ├── task.json
│   ├── chase_email.json
│   ├── plan.json
│   ├── final_report.json
│   └── gmail_document.json
├── examples/
│   ├── sample_exceptions.json
│   ├── sample_documents.json
│   └── sample_gmail_emails.json
├── tests/
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_task_generator.py
│   ├── test_email_drafter.py
│   ├── test_planner.py
│   ├── test_reporter.py
│   ├── test_gmail_crawler.py
│   ├── test_vendor_manager.py
│   ├── test_audit_logger.py
│   ├── test_exporter.py
│   ├── test_reply_tracker.py
│   └── test_scheduler.py
├── requirements.txt
├── .env.example
├── .gitignore
└── SKILL.md                  # This file
```

---

## Python API

### Basic Usage

```python
from src.secretary import Secretary
from src.models import ExceptionEvent, DocumentInfo

secretary = Secretary()
result = secretary.run(
    goal="Close out September",
    exceptions=financial_exceptions,  # list[ExceptionEvent]
    documents=logistics_documents,    # list[DocumentInfo]
)

# result is a PipelineResult containing:
#   result.plan           — Execution plan
#   result.tasks          — list[Task]
#   result.chase_emails   — list[ChaseEmail]
#   result.final_report   — FinalReport (cash flow, categories, top 3 actions)
#   result.audit_entries  — list[AuditEntry]
#   result.vendor_updates — list[VendorInfo]
#   result.reply_records  — list[ReplyRecord]
```

### Gmail Crawler

```python
from src.gmail_crawler import GmailCrawler

# Mock mode (no credentials needed)
crawler = GmailCrawler(mock=True)
crawler.authenticate()
emails = crawler.fetch_invoice_emails(max_results=50)

# Real mode (requires credentials.json — see prompts/gmail_setup_guide.md)
crawler = GmailCrawler(mock=False)
if crawler.authenticate():
    emails = crawler.fetch_invoice_emails(
        max_results=50,
        date_after="2026/09/01",
        date_before="2026/09/30",
    )
```

### Vendor Database

```python
from src.vendor_manager import VendorManager

vm = VendorManager()
vm.add_or_update_vendor(
    name="Tech Supplies Sdn Bhd",
    email="billing@techsupplies.my",
    invoice_amount=12500.00,
    invoice_date="2026-09-15",
)
new_vendors = vm.get_new_vendors()
top_5 = vm.get_top_vendors(n=5)
```

### Export

```python
from src.exporter import Exporter

exporter = Exporter()
exporter.export_all(result, output_dir="output", base_name="sept_report")
# Produces: report.csv, report.json, report.md, report_journal.csv
```

### Reply Tracking

```python
from src.reply_tracker import ReplyTracker

tracker = ReplyTracker(mock=True)
replies = tracker.check_replies(result.chase_emails)
for reply in replies:
    tracker.update_task_status(reply, result.tasks)
    # PAYMENT_CONFIRMED -> task.status = DONE
    # DISPUTED          -> task.status = IN_PROGRESS
```

### Scheduler

```python
from src.scheduler import Scheduler, ScheduleConfig, ScheduleFrequency

config = ScheduleConfig(
    frequency=ScheduleFrequency.MONTHLY,
    day_of_month=1,
    time="09:00",
    goal="Close out current month",
)
sched = Scheduler(config=config)
print(sched.format_status())
# next_run is auto-calculated
```

---

## CLI Usage

### Demo mode (sample data)

```bash
python -m src.cli --demo
python -m src.cli --demo --json
```

### File-based mode

```bash
python -m src.cli --goal "Close out September" --exceptions examples/sample_exceptions.json
python -m src.cli --goal "Reconcile October" --documents docs.json --exceptions exceptions.json --json
```

### Gmail mode

```bash
# Mock (no credentials needed)
python -m src.cli --gmail --gmail-mock

# Real (requires credentials.json)
python -m src.cli --gmail --goal "Close out September"

# Date filtering
python -m src.cli --gmail --gmail-after "2026/09/01" --gmail-before "2026/09/30" --gmail-max 25
```

### Tier 1 features

```bash
# Export pipeline results
python -m src.cli --demo --export csv
python -m src.cli --demo --export all --export-dir output

# View vendor database
python -m src.cli --vendors
python -m src.cli --demo --vendors

# View audit log
python -m src.cli --demo --audit

# Check vendor replies (mock)
python -m src.cli --demo --replies

# View scheduler status
python -m src.cli --schedule
```

### Interactive mode

```bash
python -m src.cli --interactive
```

### Save output to file

```bash
python -m src.cli --demo --output result.txt
python -m src.cli --demo --json --output result.json
```

---

## Pipeline Phases

### P0: Plan Generation (`planner.py`)

Reads the business goal and generates a phased execution plan:

| Phase | Agent | Action |
|-------|-------|--------|
| 1 | Logistics | Collect and OCR all invoice/receipt/PO documents |
| 2 | Financial | Reconcile documents against ledger, raise exceptions |
| 3 | Secretary | Convert exceptions to tasks, draft chase emails |
| 4 | Secretary | Generate final report for owner review |

Three plan modes: standard, overdue-only, reconciliation.

### P1: Task Generation + Report (`task_generator.py`, `reporter.py`)

Converts each `ExceptionEvent` from Financial into a `Task` with:
- Plain-language title and description
- Priority (P1-P4 based on event type)
- Action required
- Status tracking

Generates a `FinalReport` with:
- Cash flow summary (cash_in, cash_out, net_cash)
- Category breakdown (10 categories: RAW, RENT, SAL, MKT, LOG, MNT, OFC, IT, PRO, TAX)
- Top 3 recommended actions
- Exception and task counts

### P2: Chase Email Drafting (`email_drafter.py`)

For overdue invoices, drafts a chase email:
- Status workflow: DRAFT -> APPROVED -> SENT (or REJECTED)
- Human-in-the-loop: Secretary NEVER sends without owner approval
- Auto-approve flag exists for testing only

---

## Priority Assignment

| Priority | Event Type | Reason |
|----------|-----------|--------|
| P1 Critical | Duplicate | Potential double payment |
| P1 Critical | Escalation (>=RM 10k) | Large amount needs management approval |
| P2 High | Overdue | Chase email needed |
| P2 High | Escalation (<RM 10k) | Management review |
| P3 Medium | Flagged (confidence < 0.70) | OCR quality issue |
| P4 Low | Flagged (confidence >= 0.70) | Minor quality issue |

**Key rule**: Duplicate check takes precedence over overdue chase. If the same invoice has both flags, duplicate wins.

---

## Data Models

All models are defined in `src/models.py` using Pydantic v2.

### PipelineResult (aggregate output)

```python
class PipelineResult(BaseModel):
    plan: Plan
    tasks: list[Task]
    chase_emails: list[ChaseEmail]
    final_report: Optional[FinalReport]
    exceptions_processed: int
    warnings: list[str]
    audit_entries: list[AuditEntry]       # S8 traceability
    vendor_updates: list[VendorInfo]      # Vendor DB updates from this run
    reply_records: list[ReplyRecord]      # Vendor replies to chase emails
```

### Core Input Models

**ExceptionEvent** — from Financial agent:
- `event_type`: overdue | duplicate | escalation | flagged
- `invoice_number`, `vendor_name`, `amount` (MYR)
- `due_date`, `details`
- Duplicate: `duplicate_of`
- Escalation: `escalation_reason`, `escalation_code`
- Flagged: `flag_reason`, `confidence` (0.0-1.0)

**DocumentInfo** — from Logistics agent:
- `doc_id`, `file_name`, `doc_type` (invoice/receipt/PO)
- `vendor_name`, `invoice_number`, `invoice_date`
- `grand_total`, `currency`, `line_items`
- `confidence`, `quality_flags`

### Core Output Models

**Task**: `task_id`, `title`, `description`, `priority`, `event_type`, `invoice_number`, `vendor_name`, `amount`, `action_required`, `status`, `created_at`, `related_email_id`

**ChaseEmail**: `email_id`, `to`, `cc`, `subject`, `body`, `status`, `related_invoice`, `related_task_id`, `created_at`

**Plan**: `goal`, `phases` (list of PlanPhase), `total_phases`, `created_at`

**FinalReport**: `goal`, `period`, `cash_in`, `cash_out`, `net_cash`, `categories` (list of CategorySummary), `top_3_actions`, `total_exceptions`, `tasks_generated`, `chase_emails_drafted`, `chase_emails_approved`, `generated_at`

### Gmail Crawler Models

**AttachmentInfo**: `filename`, `mime_type`, `size`, `attachment_id`, `downloaded`, `local_path`

**RawEmailDocument**: `message_id`, `thread_id`, `sender`, `sender_email`, `subject`, `date`, `body_snippet`, `has_attachment`, `attachments`, `downloaded_files`, `detected_doc_type`, `vendor_name`, `processed_at`

### Vendor Master Model

**VendorInfo**: `vendor_id`, `name`, `email`, `phone`, `payment_terms_days`, `category_code`, `tax_id`, `bank_name`, `bank_account`, `first_invoice_date`, `total_invoices`, `total_amount`, `is_new_vendor`, `notes`

### Audit Log Model

**AuditEntry**: `entry_id`, `timestamp`, `action`, `entity_type`, `entity_id`, `description`, `actor`

### Reply Tracking Models

**ReplyStatus** (enum): `NO_REPLY`, `REPLIED`, `PAYMENT_CONFIRMED`, `DISPUTED`

**ReplyRecord**: `reply_id`, `chase_email_id`, `vendor_email`, `reply_date`, `reply_subject`, `reply_snippet`, `detected_status`, `linked_task_id`, `processed_at`

### Scheduler Models

**ScheduleFrequency** (enum): `MONTHLY`, `WEEKLY`, `DAILY`

**ScheduleConfig**: `frequency`, `day_of_month` (1-31), `day_of_week` (0-6, Mon=0), `time` (HH:MM 24h), `goal`, `enabled`, `last_run`, `next_run`

---

## JSON Schemas

JSON Schema files for validation are in the `schemas/` directory:

| Schema File | Validates |
|-------------|-----------|
| `schemas/exception_event.json` | ExceptionEvent input from Financial |
| `schemas/task.json` | Task output (strict: `additionalProperties: false`) |
| `schemas/chase_email.json` | ChaseEmail output |
| `schemas/plan.json` | Plan output |
| `schemas/final_report.json` | FinalReport output (strict: `additionalProperties: false`) |
| `schemas/gmail_document.json` | RawEmailDocument from Gmail crawler |

**Note**: `task.json` and `final_report.json` use `additionalProperties: false` for strict validation. The extended `PipelineResult` model (with `audit_entries`, `vendor_updates`, `reply_records`) is **not** constrained by these schemas — those fields are additive and do not break existing schema validation.

---

## Module Details

### Gmail Crawler (`src/gmail_crawler.py`)

Auto-fetches invoice/receipt/PO emails from Gmail via OAuth 2.0.

- **Mock mode**: Works without credentials or Google libraries installed — returns 5 sample vendor emails
- **Real mode**: Requires `credentials.json` from Google Cloud Console (see `prompts/gmail_setup_guide.md`)
- **Lazy import**: Google libraries (`google-api-python-client`, `google-auth-oauthlib`) are imported only when needed
- **Deduplication**: Instance-level cache file tracks processed message IDs
- **Search**: Builds Gmail search query from subject keywords (invoice, receipt, resit, PO, bill, statement, tax invoice)
- **Attachments**: Downloads PDF/JPG/PNG/HEIC to `staging/` directory
- **Vendor extraction**: Parses sender name and email address
- **Doc type detection**: Infers invoice/receipt/PO from subject line keywords

### Vendor Manager (`src/vendor_manager.py`)

JSON-persisted vendor master database.

- **Seeded** with 5 default vendors (VND-001 through VND-005)
- **Auto-flagging**: `is_new_vendor = True` when vendor has < 2 prior invoices
- **Lookup**: by name, email, or vendor ID
- **Stats**: total vendors, total spend, top N vendors, vendors by category
- **Auto ID generation**: Sequential `VND-XXX` IDs
- **Persistence**: Saved to `vendors.json`

### Audit Logger (`src/audit_logger.py`)

Append-only audit log for S8 traceability.

- **Integrated into Secretary.run()**: Logs plan creation, task creation, email drafting, report generation
- **Query**: by entity, action, entity type, date range, recent N
- **Stats**: entry count, action counts
- **Persistence**: Saved to `audit_log.json`

### Exporter (`src/exporter.py`)

Exports pipeline results in multiple formats:

| Format | Description |
|--------|-------------|
| CSV | Multi-section: cash flow, category breakdown, task list, chase emails |
| JSON | Full PipelineResult as JSON |
| Markdown | Formatted report with tables |
| Journal | Double-entry accounting: Date, Account Code, Account Name, Debit (MYR), Credit (MYR), Description, Reference |

`export_all()` produces all four formats at once.

### Reply Tracker (`src/reply_tracker.py`)

Detects and classifies vendor replies to chase emails.

- **Mock mode**: Returns 2 sample replies (payment confirmed + disputed)
- **Intent detection**: Keyword-based classification
  - **Payment confirmed**: "payment has been made", "we've paid", "processed the payment", "settled", etc.
  - **Disputed**: "dispute", "incorrect amount", "wrong invoice", "not ours", etc.
  - **Acknowledgment**: "received", "looking into it", "will check", etc.
  - Priority: Payment > Dispute > Acknowledgment > Replied
- **Auto task update**: PAYMENT_CONFIRMED -> task.status = DONE; DISPUTED -> task.status = IN_PROGRESS
- **Pending queries**: Identifies chase emails with no reply

### Scheduler (`src/scheduler.py`)

Automated pipeline scheduling.

- **Frequencies**: Monthly, Weekly, Daily
- **Next-run calculation**: Handles edge cases (Feb 30 -> last day of Feb, same-day-before-time)
- **Persistence**: Saves to `schedule.json`
- **Management**: enable(), disable(), update_config()
- **Status**: Human-readable format_status()

---

## Key Business Rules (S1-S8)

| Rule | Description |
|------|-------------|
| S1 | Duplicate detection: same vendor + amount + invoice number |
| S2 | Reconciliation tolerance: +/-RM 1 (<RM 100) or +/-RM 5 (>=RM 100) |
| S3 | PO matching: PO number, vendor, amount, line items |
| S4 | Overdue: payment due date passed, no payment record |
| S5 | 10 category codes: RAW, RENT, SAL, MKT, LOG, MNT, OFC, IT, PRO, TAX |
| S6 | 7 escalation triggers: large amount (>=RM 10k), tax mismatch, missing PO, etc. |
| S7 | Bad document flags: unreadable, missing pages, no invoice number, etc. |
| S8 | Traceability: all decisions must be auditable (via AuditLogger) |

---

## Configuration

Edit `src/config.py` or set environment variables (see `.env.example`):

**Business identity:**
- `BUSINESS_NAME` — Your company name (default: "Your Business Sdn Bhd")
- `BUSINESS_EMAIL` — Your accounts email
- `BUSINESS_CURRENCY` — Default "MYR"

**Reconciliation thresholds (S2):**
- `RECON_TOLERANCE_SMALL` — +/-RM 1.00 for amounts < RM 100
- `RECON_TOLERANCE_LARGE` — +/-RM 5.00 for amounts >= RM 100

**Escalation triggers (S6):**
- `LARGE_AMOUNT` — RM 10,000 threshold
- `MISSING_PO` — No PO for purchases >= RM 500
- `VENDOR_NEW` — First-time vendor (< 2 prior invoices)
- `OVERDUE_30D` — Overdue by 30+ days

**Gmail crawler:**
- `GMAIL_CREDENTIALS_FILE` — OAuth credentials path (default: `credentials.json`)
- `GMAIL_TOKEN_FILE` — OAuth token cache (default: `token.json`)
- `GMAIL_STAGING_DIR` — Attachment download directory (default: `staging/`)
- `GMAIL_SUBJECT_KEYWORDS` — Search keywords for invoice emails
- `GMAIL_ATTACHMENT_EXTENSIONS` — `.pdf`, `.jpg`, `.jpeg`, `.png`, `.heic`
- `GMAIL_VENDOR_DOMAINS` — Optional sender domain whitelist (empty = accept all)
- `GMAIL_MAX_RESULTS` — Max emails per fetch (default: 50)
- `GMAIL_SCOPES` — `["https://www.googleapis.com/auth/gmail.readonly"]`

---

## Dependencies

**Core:**
- `pydantic>=2.0` — Data validation and models

**Gmail (optional, lazy-loaded):**
- `google-api-python-client>=2.100.0`
- `google-auth-oauthlib>=1.1.0`
- `google-auth-httplib2>=0.2.0`

**Development:**
- `pytest` — Test runner (282 tests across 12 test files)

---

## Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific module tests
python -m pytest tests/test_gmail_crawler.py -v
python -m pytest tests/test_vendor_manager.py -v
python -m pytest tests/test_exporter.py -v
```

Test coverage: 282 tests across 12 test files covering all modules including edge cases, mock data, persistence, and formatting.

# Logistics Coordinator Agent

## Build Priority: FIRST

Nothing downstream works without structured records. This agent collects documents, extracts structured data, and hands records to Financial.

## The One Rule

**Logistics NEVER computes a total.** It records what is printed on the document. Financial validates arithmetic. This boundary is enforced in code (`_pipeline_meta.total_computed_by_logistics` is always `False`).

## Architecture

```
agents/logistics/
├── agent_config.md              # Agent role, priorities, input/output spec
├── schemas/                     # Extraction schemas (SWAPPABLE)
│   ├── invoice_schema.json      # Arbitrary v1 — replace with exact schema when ready
│   ├── receipt_schema.json
│   └── order_schema.json
├── prompts/
│   ├── system_prompt.md         # System prompt for WorkBuddy agent
│   └── extraction_template.md   # Template for extraction calls
├── src/
│   ├── __init__.py
│   ├── pipeline.py              # Main orchestration: document → record
│   ├── schema_loader.py         # Loads schemas from JSON (swap files = swap schema)
│   ├── document_type_detector.py # Detects invoice/receipt/order from content
│   ├── confidence.py            # Confidence scoring + escalation thresholds
│   ├── validator.py             # Validates records against schema
│   └── bad_doc_handler.py       # Handles bad docs: flag, don't guess
├── tests/
│   └── test_pipeline.py         # Tests for all document types + bad docs
├── run.py                       # CLI entry point
└── README.md                    # This file
```

## Schema: Arbitrary v1 (Swappable)

The current schemas in `schemas/` are **arbitrary v1** — they define a reasonable structure for Malaysian invoices, receipts, and orders with SST handling, confidence scores, and bad-doc flagging.

When the exact schema arrives:
1. Replace the JSON files in `schemas/`
2. The code automatically picks them up — no code changes needed
3. The `SchemaLoader` reads `required` and `properties` from the JSON at runtime

The pipeline logs `schema_version: "arbitrary_v1"` in `_pipeline_meta` so you can track which schema was used.

## How to Run

### Process a single document:
```bash
python agents/logistics/run.py --file path/to/document.txt --output records.json
```

### Process a directory of documents:
```bash
python agents/logistics/run.py --input path/to/documents/ --output records.json
```

### Run tests:
```bash
python agents/logistics/tests/test_pipeline.py
```

## Pipeline Flow

```
Document (text/image)
    │
    ▼
┌─────────────────────┐
│ Type Detection      │ ← keyword matching (EN + BM), filename hint
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ Bad Doc Check       │ ← detect blurry, handwritten, unparseable
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ Schema Loading      │ ← loads JSON schema by doc type (swappable)
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ Extraction          │ ← WorkBuddy agent using system_prompt.md
│ (agent does this)   │   outputs structured record with confidence
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ Validation          │ ← required fields, types, confidence thresholds
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ Confidence Check    │ ← escalate if critical field < 0.7
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ Output              │ ← JSON array of records → Financial
└─────────────────────┘
```

## Confidence Scoring

| Score Range | Meaning | Action |
|-------------|---------|--------|
| 0.8–1.0 | Clearly printed, machine-readable | Clean |
| 0.6–0.7 | Readable but minor ambiguity | Clean or flagged |
| 0.4–0.5 | Difficult, best-effort | Flagged |
| < 0.4 | Unparseable | Flagged, escalate to owner |
| < 0.7 (critical field) | — | Escalate to owner via Secretary |

Critical fields by type:
- Invoice: vendor_name, invoice_number, invoice_date, grand_total, line_items
- Receipt: vendor_name, receipt_date, amount
- Order: po_number, po_date, vendor_name, grand_total, line_items

## Bad Document Handling

| Bad Doc Type | Flag | Action |
|--------------|------|--------|
| Blurry photo | `blurry_image` | Extract what's possible, low confidence |
| Handwritten | `handwritten` | Lower confidence threshold (0.6) |
| No PO reference | `no_po_reference` | Escalate if amount > RM 500 |
| Wrong total | `total_mismatch` | Record as-is, Financial catches it |
| Duplicate | `possible_duplicate` | Process both, Financial confirms |
| Unparseable | `unparseable` | Minimal error record, source_ref only |

## Output Format

Each record is a JSON object conforming to its schema. The batch output is a JSON array:

```json
[
  {
    "document_type": "invoice",
    "vendor_name": "Kedai Kopi Maju Sdn Bhd",
    "invoice_number": "INV-2026-0941",
    "invoice_date": "2026-09-15",
    "grand_total": 371.00,
    "currency": "MYR",
    "source_ref": "invoice_001.pdf",
    "confidence": { "vendor_name": 0.95, ... },
    "status": "clean",
    "flags": []
  },
  ...
]
```

Internal metadata (`_validation`, `_pipeline_meta`) is stripped before handover to Financial.

## SST Handling

Malaysian SST rates: 0% (exempt), 6%, 8%.
- Tax amount recorded as printed
- Tax rate recorded if stated
- Logistics does NOT validate SST correctness — Financial does

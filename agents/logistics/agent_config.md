# Agent: Logistics Coordinator

## Role
Collects and organises documents. Extracts structured records. **Never computes a total.**

## Build Priority: FIRST

Nothing downstream works without structured records.

## Responsibilities

### P0
- [ ] Extraction schema per document type (invoice, receipt, order/PO)
- [ ] Output structured records only — never a computed total
- [ ] Handle the 5 bad documents without crashing — flag, do not guess

### P1
- [ ] Confidence value per field; low confidence routes a question to the owner

### P2
- [ ] Parallel extraction across documents

## Input
- ~40 documents in mixed formats: email attachments, WhatsApp photos, paper scans, phone photos
- Mixed Bahasa Malaysia and English
- SST (Sales and Services Tax) lines
- Realistic Malaysian vendors

## Output
Structured records handed to Financial. Each record contains:
- Document type (invoice / receipt / order / PO)
- Vendor name
- Date
- Line items (description, quantity, unit price, tax, total)
- Currency (MYR)
- Source document reference (for traceability)
- Confidence score per field
- Status (clean / flagged / error)

## Hard Boundary
Logistics owns documents. Financial owns numbers. Logistics hands over structured records and **never computes a total**.

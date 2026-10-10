# Extraction Call Template

## Template for extracting a single document

```
Extract this document into a structured record.

Document source: {source_ref}
Document type (if known): {document_type or "auto-detect"}

Use the schema for this document type. If the type is unknown, detect it first.

Rules:
1. Record fields exactly as printed. Do not compute or verify any total.
2. Assign a confidence score (0.0–1.0) to each critical field.
3. If a field is unparseable, set it to null and add a flag.
4. If the document is bad (blurry, handwritten, missing fields), do not guess. Flag it.
5. Include the source_ref for traceability.

Output a single JSON object conforming to the schema.
```

## Batch Template (for multiple documents)

```
You are processing a batch of {count} documents for the month of {month}.

For each document:
1. Read the document content
2. Detect the document type (invoice, receipt, order)
3. Extract fields per the appropriate schema
4. Assign confidence scores
5. Flag any issues

Output a JSON array of records, one per document.

Documents:
{document_list}

Remember: NEVER compute a total. Record what is printed. Flag what is unclear.
```

"""
Logistics Pipeline

End-to-end orchestration of the document extraction process.

Flow:
1. Receive document(s) from the Secretary's dispatch
2. Detect document type (invoice / receipt / order)
3. Load the appropriate schema (from schema files — swappable)
4. Extract structured fields using the WorkBuddy agent prompt
5. Assign confidence scores per field
6. Validate against schema (required fields, types)
7. Handle bad documents (flag, don't crash)
8. Output JSON array of records → hand to Financial

The actual extraction is done by the WorkBuddy agent using the system prompt.
This pipeline handles orchestration, validation, and output formatting.
"""

import json
import os
from typing import Optional
from .schema_loader import SchemaLoader
from .document_type_detector import detect as detect_type
from .confidence import check_record_confidence
from .validator import validate_record, validate_batch
from .bad_doc_handler import handle_bad_document, detect_bad_document_signals, should_escalate_for_missing_po


class LogisticsPipeline:
    """
    Orchestrates document extraction for the Logistics Coordinator agent.

    Usage:
        pipeline = LogisticsPipeline(schema_dir="/path/to/schemas")

        # Process a single document
        record = pipeline.process_document(
            content="invoice text...",
            source_ref="doc_001.pdf",
            extracted_record={"document_type": "invoice", ...}  # from WorkBuddy agent
        )

        # Process a batch
        records = pipeline.process_batch([
            {"content": "...", "source_ref": "doc_001", "extracted": {...}},
            {"content": "...", "source_ref": "doc_002", "extracted": {...}},
        ])
    """

    def __init__(self, schema_dir: str):
        self.loader = SchemaLoader(schema_dir)

    def process_document(
        self,
        content: str,
        source_ref: str,
        extracted_record: Optional[dict] = None,
        filename: str = "",
    ) -> dict:
        """
        Process a single document through the pipeline.

        Args:
            content: Raw text content of the document
            source_ref: Reference to the source document (filename, hash, path)
            extracted_record: Pre-extracted record from the WorkBuddy agent.
                              If None, the document is treated as unprocessed.
            filename: Original filename for type detection hint.

        Returns:
            A validated, confidence-scored JSON record ready for Financial.
        """
        # Step 1: Detect document type
        detected_type, type_confidence = detect_type(content, filename)

        # Step 2: Check for bad document signals
        bad_signals = detect_bad_document_signals(content)

        # Step 3: If completely unparseable, return minimal error record
        if "unparseable" in bad_signals and not extracted_record:
            return handle_bad_document(
                source_ref=source_ref,
                raw_content=content,
                detected_flags=bad_signals,
            )

        # Step 4: Use the extracted record from the agent, or build a stub
        if extracted_record:
            record = extracted_record.copy()
        else:
            # No extraction yet — this is where the WorkBuddy agent fills in
            record = {
                "source_ref": source_ref,
                "status": "flagged",
                "flags": bad_signals,
            }
            if detected_type != "unknown":
                record["document_type"] = detected_type

        # Step 5: Ensure source_ref is set
        record["source_ref"] = source_ref

        # Step 6: Ensure document_type is set
        if "document_type" not in record and detected_type != "unknown":
            record["document_type"] = detected_type

        # Step 7: Merge detected flags with any from the agent
        existing_flags = set(record.get("flags", []))
        existing_flags.update(bad_signals)
        record["flags"] = list(existing_flags)

        # Step 8: Validate against schema (if type is known)
        doc_type = record.get("document_type", "unknown")
        if doc_type != "unknown":
            validation = validate_record(record, doc_type, self.loader)
            record["_validation"] = validation

            # If there are escalations, ensure status is at least 'flagged'
            if validation["escalations"]:
                if record.get("status") == "clean":
                    record["status"] = "flagged"

            # Check for missing PO escalation
            if doc_type == "invoice" and should_escalate_for_missing_po(record):
                record["flags"].append("escalate_missing_po")
        else:
            record["_validation"] = {
                "valid": False,
                "missing": [],
                "escalations": [],
                "warnings": ["Unknown document type — cannot validate"],
            }

        # Step 9: NEVER compute a total (safety check — we just verify we didn't)
        # This is a no-op — we trust the agent to follow the system prompt.
        # But we log it for the record:
        record["_pipeline_meta"] = {
            "total_computed_by_logistics": False,  # Must always be False
            "detected_type": detected_type,
            "type_confidence": type_confidence,
            "schema_version": "arbitrary_v1",  # Change when real schema arrives
        }

        return record

    def process_batch(self, documents: list[dict]) -> list[dict]:
        """
        Process a batch of documents.

        Each document dict should have:
            - content: str (raw text)
            - source_ref: str
            - extracted: dict (optional, from WorkBuddy agent)
            - filename: str (optional)
        """
        records = []
        for doc in documents:
            record = self.process_document(
                content=doc.get("content", ""),
                source_ref=doc.get("source_ref", "unknown"),
                extracted_record=doc.get("extracted"),
                filename=doc.get("filename", ""),
            )
            records.append(record)

        # Batch-level validation
        records = validate_batch(records, self.loader)

        return records

    def format_output(self, records: list[dict]) -> str:
        """
        Format records as JSON for handover to Financial.
        Strips internal pipeline metadata (keys starting with _).
        """
        clean_records = []
        for record in records:
            clean = {k: v for k, v in record.items() if not k.startswith("_")}
            clean_records.append(clean)

        return json.dumps(clean_records, indent=2, ensure_ascii=False)

    def get_summary(self, records: list[dict]) -> dict:
        """
        Generate a summary of the batch for the Secretary agent.
        """
        total = len(records)
        by_status = {"clean": 0, "flagged": 0, "error": 0}
        by_type = {}
        all_flags = []
        all_escalations = []

        for record in records:
            status = record.get("status", "flagged")
            by_status[status] = by_status.get(status, 0) + 1

            doc_type = record.get("document_type", "unknown")
            by_type[doc_type] = by_type.get(doc_type, 0) + 1

            all_flags.extend(record.get("flags", []))

            validation = record.get("_validation", {})
            all_escalations.extend(validation.get("escalations", []))

        return {
            "total_documents": total,
            "by_status": by_status,
            "by_type": by_type,
            "total_flags": len(all_flags),
            "unique_flags": list(set(all_flags)),
            "escalations_count": len(all_escalations),
            "escalations": all_escalations,
            "ready_for_financial": by_status.get("clean", 0) + by_status.get("flagged", 0),
            "blocked": by_status.get("error", 0),
        }

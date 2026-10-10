"""
Schema Loader

Loads extraction schemas from JSON files. The schema directory is configurable
so the exact schema can be swapped without touching any code.

Usage:
    loader = SchemaLoader("/path/to/schemas")
    schema = loader.get_schema("invoice")
    record = loader.validate(record_dict, "invoice")
"""

import json
import os
from typing import Any, Optional


class SchemaLoader:
    """Loads and caches JSON schemas by document type."""

    # Map document type identifiers to schema filenames
    SCHEMA_FILES = {
        "invoice": "invoice_schema.json",
        "receipt": "receipt_schema.json",
        "order": "order_schema.json",
        "po": "order_schema.json",  # alias
    }

    def __init__(self, schema_dir: str):
        self.schema_dir = schema_dir
        self._cache: dict[str, dict] = {}

    def get_schema(self, doc_type: str) -> dict:
        """Load and return the schema for a document type."""
        doc_type = doc_type.lower().strip()

        if doc_type not in self.SCHEMA_FILES:
            raise ValueError(f"Unknown document type: {doc_type}. "
                             f"Supported: {list(self.SCHEMA_FILES.keys())}")

        if doc_type in self._cache:
            return self._cache[doc_type]

        filename = self.SCHEMA_FILES[doc_type]
        filepath = os.path.join(self.schema_dir, filename)

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Schema file not found: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            schema = json.load(f)

        self._cache[doc_type] = schema
        return schema

    def get_required_fields(self, doc_type: str) -> list[str]:
        """Return the list of required field names for a document type."""
        schema = self.get_schema(doc_type)
        return schema.get("required", [])

    def get_field_names(self, doc_type: str) -> list[str]:
        """Return all field names defined in the schema."""
        schema = self.get_schema(doc_type)
        return list(schema.get("properties", {}).keys())

    def get_confidence_fields(self, doc_type: str) -> list[str]:
        """Return the fields that need confidence scores."""
        schema = self.get_schema(doc_type)
        confidence_schema = schema.get("properties", {}).get("confidence", {})
        return list(confidence_schema.get("properties", {}).keys())

    def validate_required(self, record: dict, doc_type: str) -> list[str]:
        """
        Check that all required fields are present.
        Returns a list of missing field names (empty if all present).
        """
        required = self.get_required_fields(doc_type)
        missing = []
        for field in required:
            if field not in record or record[field] is None:
                # 'null' is acceptable for optional fields, but required fields
                # must at least be present in the dict
                if field not in record:
                    missing.append(field)
        return missing

    def list_supported_types(self) -> list[str]:
        """Return the unique document types that have schemas."""
        return list(set(self.SCHEMA_FILES.values()))

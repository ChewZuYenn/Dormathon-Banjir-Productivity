"""
CLI entry point for the Logistics Pipeline.

Usage:
    python -m agents.logistics.run --input <doc_dir> --output <output.json>

Or for a single document:
    python -m agents.logistics.run --file <path> --output <output.json>

The pipeline reads documents, detects types, validates against schemas,
and outputs JSON records ready for the Financial agent.
"""

import argparse
import json
import os
import sys

# Ensure the src package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.pipeline import LogisticsPipeline


def read_text_file(filepath: str) -> str:
    """Read a text file and return its content."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def main():
    parser = argparse.ArgumentParser(description="Logistics Coordinator Pipeline")
    parser.add_argument("--input", "-i", help="Directory of documents to process")
    parser.add_argument("--file", "-f", help="Single file to process")
    parser.add_argument("--output", "-o", default="output.json", help="Output JSON file path")
    parser.add_argument("--schema-dir", default=None, help="Override schema directory")
    args = parser.parse_args()

    # Determine schema directory
    if args.schema_dir:
        schema_dir = args.schema_dir
    else:
        schema_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schemas")

    pipeline = LogisticsPipeline(schema_dir)

    documents = []

    if args.file:
        content = read_text_file(args.file)
        documents.append({
            "content": content,
            "source_ref": args.file,
            "filename": os.path.basename(args.file),
        })
    elif args.input:
        for filename in sorted(os.listdir(args.input)):
            filepath = os.path.join(args.input, filename)
            if os.path.isfile(filepath):
                content = read_text_file(filepath)
                documents.append({
                    "content": content,
                    "source_ref": filepath,
                    "filename": filename,
                })
    else:
        print("Error: provide --input <dir> or --file <path>")
        sys.exit(1)

    # Process
    print(f"\nProcessing {len(documents)} document(s)...")
    records = pipeline.process_batch(documents)

    # Generate summary
    summary = pipeline.get_summary(records)
    print(f"\n--- Summary ---")
    print(f"  Total: {summary['total_documents']}")
    print(f"  Clean: {summary['by_status'].get('clean', 0)}")
    print(f"  Flagged: {summary['by_status'].get('flagged', 0)}")
    print(f"  Error: {summary['by_status'].get('error', 0)}")
    print(f"  Escalations: {summary['escalations_count']}")
    print(f"  Ready for Financial: {summary['ready_for_financial']}")
    print(f"  Blocked: {summary['blocked']}")

    # Output
    output_json = pipeline.format_output(records)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(output_json)
    print(f"\nOutput written to: {args.output}")
    print(f"Records: {len(records)}")


if __name__ == "__main__":
    main()

"""CLI entry point for the Secretary Agent.

Usage:
    # Demo mode — runs full pipeline + ALL 5 Tier 1 features automatically
    python -m src.cli --demo

    # Demo mode — JSON output
    python -m src.cli --demo --json

    # Full mode (any pipeline + all 5 Tier 1 features)
    python -m src.cli --goal "Close out September" --exceptions examples/sample_exceptions.json --full

    # Gmail mode — auto-fetch invoice emails
    python -m src.cli --gmail --gmail-mock  # mock data, no credentials needed
    python -m src.cli --gmail --goal "Close out September"
    python -m src.cli --gmail --gmail-after "2026/09/01" --gmail-before "2026/09/30"

    # Process exceptions from a JSON file
    python -m src.cli --goal "Close out September" --exceptions examples/sample_exceptions.json

    # Interactive mode
    python -m src.cli --interactive
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .models import DocumentInfo, ExceptionEvent
from .secretary import Secretary


def load_json_file(path: str) -> list[dict]:
    """Load a JSON file and return a list of dicts."""
    p = Path(path)
    if not p.exists():
        print(f"Error: File not found: {path}")
        sys.exit(1)
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = [data]
    return data


def parse_exceptions(data: list[dict]) -> list[ExceptionEvent]:
    """Parse raw dict data into ExceptionEvent objects."""
    return [ExceptionEvent(**item) for item in data]


def parse_documents(data: list[dict]) -> list[DocumentInfo]:
    """Parse raw dict data into DocumentInfo objects."""
    return [DocumentInfo(**item) for item in data]


def post_process(args, secretary, result):
    """Handle post-pipeline Tier 1 features: export, vendors, audit, replies, schedule."""
    # Export
    if args.export:
        from .exporter import Exporter
        exporter = Exporter()
        if args.export == "all":
            paths = exporter.export_all(result, args.export_dir, "report")
            print(f"\n{'='*60}")
            print(f"  EXPORT — 4 files saved to {args.export_dir}/")
            print(f"{'='*60}")
            for fmt, path in paths.items():
                print(f"  {fmt:10s}: {path}")
        else:
            ext_map = {"csv": ".csv", "json": ".json", "markdown": ".md", "journal": "_journal.csv"}
            filename = f"report{ext_map.get(args.export, '.txt')}"
            path = Path(args.export_dir) / filename
            if args.export == "csv":
                exporter.export_csv(result, path)
            elif args.export == "json":
                exporter.export_json(result, path)
            elif args.export == "markdown":
                exporter.export_markdown(result, path)
            elif args.export == "journal":
                exporter.export_journal(result, path)
            print(f"\n--- Exported to {path} ---")

    # Vendor database
    if args.vendors:
        print(f"\n{'='*60}")
        print("  VENDOR DATABASE")
        print(f"{'='*60}")
        print(secretary.vendor_manager.format_summary())

    # Audit log
    if args.audit:
        print(f"\n{'='*60}")
        print("  AUDIT LOG")
        print(f"{'='*60}")
        print(secretary.audit_logger.format_summary())

    # Reply tracking
    if args.replies and result.chase_emails:
        from .reply_tracker import ReplyTracker
        tracker = ReplyTracker(mock=True)
        replies = tracker.check_replies(result.chase_emails)
        print(f"\n{'='*60}")
        print("  REPLY TRACKER")
        print(f"{'='*60}")
        if replies:
            print(tracker.format_replies(replies))
            # Update task statuses
            for reply in replies:
                tracker.update_task_status(reply, result.tasks)
            print()
            print(tracker.format_summary(result.chase_emails))
        else:
            print("  No vendor replies detected.")
            print()
            print(tracker.format_summary(result.chase_emails))

    # Scheduler status
    if args.schedule:
        from .scheduler import Scheduler
        sched = Scheduler()
        print(f"\n{'='*60}")
        print("  SCHEDULER")
        print(f"{'='*60}")
        print(sched.format_status())


def main():
    parser = argparse.ArgumentParser(
        description="Secretary Agent — Task Coordinator for Document Processing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.cli --demo          # Full pipeline + ALL 5 Tier 1 features
  python -m src.cli --demo --json   # Same, JSON output
  python -m src.cli --goal "Close out September" --exceptions exceptions.json --full
  python -m src.cli --interactive
  python -m src.cli --gmail --gmail-mock
  python -m src.cli --gmail --gmail-after "2026/09/01" --gmail-before "2026/09/30"
        """,
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with sample data (no file input needed)",
    )
    parser.add_argument(
        "--goal",
        type=str,
        default="Close out September",
        help="The business goal for this run",
    )
    parser.add_argument(
        "--exceptions",
        type=str,
        default=None,
        help="Path to JSON file with exception events from Financial agent",
    )
    parser.add_argument(
        "--documents",
        type=str,
        default=None,
        help="Path to JSON file with document info from Logistics agent",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of formatted text",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve chase emails (TESTING ONLY — never use in production)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive mode — prompt for goal and inputs",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write output to a file instead of stdout",
    )

    # ------------------------------------------------------------------
    # Gmail crawler options
    # ------------------------------------------------------------------
    parser.add_argument(
        "--gmail",
        action="store_true",
        help="Fetch invoice/receipt emails from Gmail before running the pipeline",
    )
    parser.add_argument(
        "--gmail-mock",
        action="store_true",
        help="Use mock Gmail data (no real credentials needed)",
    )
    parser.add_argument(
        "--gmail-after",
        type=str,
        default=None,
        help="Only fetch emails after this date (YYYY/MM/DD)",
    )
    parser.add_argument(
        "--gmail-before",
        type=str,
        default=None,
        help="Only fetch emails before this date (YYYY/MM/DD)",
    )
    parser.add_argument(
        "--gmail-max",
        type=int,
        default=50,
        help="Maximum number of emails to fetch (default: 50)",
    )

    # ------------------------------------------------------------------
    # Tier 1 feature options
    # ------------------------------------------------------------------
    parser.add_argument(
        "--export",
        type=str,
        default=None,
        choices=["csv", "json", "markdown", "journal", "all"],
        help="Export pipeline result to file (csv, json, markdown, journal, all)",
    )
    parser.add_argument(
        "--export-dir",
        type=str,
        default="output",
        help="Directory for exported files (default: output)",
    )
    parser.add_argument(
        "--vendors",
        action="store_true",
        help="Display the vendor master database",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Display the audit log after running",
    )
    parser.add_argument(
        "--replies",
        action="store_true",
        help="Check for vendor replies to chase emails (mock mode)",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Display the scheduler status",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run all 5 Tier 1 features (export, vendors, audit, replies, schedule)",
    )

    args = parser.parse_args()

    # ------------------------------------------------------------------
    # --demo or --full: auto-enable all 5 Tier 1 features
    # ------------------------------------------------------------------
    if args.demo or args.full:
        if args.export is None:
            args.export = "all"
        args.vendors = True
        args.audit = True
        args.replies = True
        args.schedule = True

    secretary = Secretary()

    # ------------------------------------------------------------------
    # Standalone: Vendor database (only if no pipeline mode is active)
    # ------------------------------------------------------------------
    if args.vendors and not (args.demo or args.gmail or args.interactive or args.exceptions or args.full):
        print(secretary.vendor_manager.format_summary())
        return

    # ------------------------------------------------------------------
    # Standalone: Scheduler status (only if no pipeline mode is active)
    # ------------------------------------------------------------------
    if args.schedule and not (args.demo or args.gmail or args.interactive or args.exceptions or args.full):
        from .scheduler import Scheduler
        sched = Scheduler()
        print(sched.format_status())
        return

    # ------------------------------------------------------------------
    # Gmail mode — fetch emails before running pipeline
    # ------------------------------------------------------------------
    if args.gmail:
        from .gmail_crawler import GmailCrawler

        crawler = GmailCrawler(mock=args.gmail_mock)

        print("=" * 60)
        print("  Secretary Agent — Gmail Crawler Mode")
        print("=" * 60)
        print()

        if not crawler.authenticate():
            print("Failed to authenticate with Gmail. Exiting.")
            sys.exit(1)

        if crawler.mock and not args.gmail_mock:
            print("(No credentials.json found — using mock data)\n")

        emails = crawler.fetch_invoice_emails(
            max_results=args.gmail_max,
            date_after=args.gmail_after,
            date_before=args.gmail_before,
        )

        print(crawler.format_emails_summary(emails))
        print()

        if not emails:
            print("No new emails found. Running pipeline with sample data...\n")
            exceptions = secretary._sample_exceptions()
            documents = secretary._sample_documents()
        else:
            # In production: Logistics would OCR the downloaded attachments
            # For now: use sample data that matches the email vendors
            print(
                f"Downloaded {sum(len(e.downloaded_files) for e in emails)} "
                f"attachment(s) to staging/.\n"
                f"(In production, Logistics agent would OCR these files.\n"
                f" Using sample data for pipeline demo.)\n"
            )
            exceptions = secretary._sample_exceptions()
            documents = secretary._sample_documents()

        result = secretary.run(
            goal=args.goal,
            exceptions=exceptions,
            documents=documents,
            auto_approve_emails=args.auto_approve,
        )

        if args.json:
            output = secretary.result_to_json(result)
        else:
            output = secretary.format_result(result)

        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
            print(f"Output written to {args.output}")
        else:
            print(output)

        post_process(args, secretary, result)
        return

    # ------------------------------------------------------------------
    # Interactive mode
    # ------------------------------------------------------------------
    if args.interactive:
        print("=" * 60)
        print("  Secretary Agent — Interactive Mode")
        print("=" * 60)
        print()

        goal = input("Enter your goal (e.g. 'Close out September'): ").strip()
        if not goal:
            goal = "Close out September"

        exceptions_path = input(
            "Path to exceptions JSON file (or press Enter for demo data): "
        ).strip()

        print()
        print("Processing...")
        print()

        if exceptions_path:
            raw = load_json_file(exceptions_path)
            exceptions = parse_exceptions(raw)
        else:
            print("(No exceptions file provided — using sample data)")
            exceptions = secretary._sample_exceptions()

        result = secretary.run(
            goal=goal,
            exceptions=exceptions,
            auto_approve_emails=args.auto_approve,
        )

        output = secretary.format_result(result)
        print(output)
        return

    # ------------------------------------------------------------------
    # Demo mode
    # ------------------------------------------------------------------
    if args.demo:
        print("=" * 60)
        print("  Secretary Agent — DEMO MODE (Full Pipeline + 5 Tier 1 Features)")
        print("=" * 60)
        print()
        print("  Features enabled:")
        print("    [1] Pipeline  — Plan + Tasks + Chase Emails + Final Report")
        print("    [2] Export    — CSV + JSON + Markdown + Journal")
        print("    [3] Vendors   — Vendor Master Database")
        print("    [4] Audit     — Audit Log (S8 Traceability)")
        print("    [5] Replies   — Chase Email Reply Tracker")
        print("    [6] Schedule  — Scheduler Status")
        print()
        print("  Running with sample data...\n")

        result = secretary.run(
            goal=args.goal,
            exceptions=secretary._sample_exceptions(),
            documents=secretary._sample_documents(),
            auto_approve_emails=args.auto_approve,
        )

        if args.json:
            output = secretary.result_to_json(result)
        else:
            output = secretary.format_result(result)

        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
            print(f"Output written to {args.output}")
        else:
            print(output)

        post_process(args, secretary, result)
        return

    # ------------------------------------------------------------------
    # File-based mode
    # ------------------------------------------------------------------
    exceptions: list[ExceptionEvent] = []
    documents: list[DocumentInfo] = []

    if args.exceptions:
        raw_exceptions = load_json_file(args.exceptions)
        exceptions = parse_exceptions(raw_exceptions)

    if args.documents:
        raw_docs = load_json_file(args.documents)
        documents = parse_documents(raw_docs)

    # If neither is provided, fall back to demo data
    if not exceptions and not documents:
        print("No input files provided. Running in demo mode...\n")
        exceptions = secretary._sample_exceptions()
        documents = secretary._sample_documents()

    result = secretary.run(
        goal=args.goal,
        exceptions=exceptions,
        documents=documents,
        auto_approve_emails=args.auto_approve,
    )

    if args.json:
        output = secretary.result_to_json(result)
    else:
        output = secretary.format_result(result)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Output written to {args.output}")
    else:
        print(output)

    post_process(args, secretary, result)


if __name__ == "__main__":
    main()

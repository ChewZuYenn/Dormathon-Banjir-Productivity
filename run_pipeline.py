#!/usr/bin/env python
"""
Banjir Productivity — Full Month-End Pipeline
=============================================

Runs all three agents in sequence from a single command:

    Logistics (extract)  ->  Financial (validate)  ->  Secretary (plan, tasks, emails, report)

No WorkBuddy required. Clone, install, run. Steps 2-4 go through the same
PipelineOrchestrator as the web app (app.py), so results match the site.

Usage:
    python run_pipeline.py                              # Full pipeline with test docs
    python run_pipeline.py --goal "Close out September" # Custom goal
    python run_pipeline.py --json                        # JSON output
    python run_pipeline.py --output result.json          # Save to file
    python run_pipeline.py --skip-logistics              # Reuse existing output.json
    python run_pipeline.py --help                        # Full options

Requirements:
    pip install -r requirements.txt   (LLM optional: see .env / README)

What it does:
    1. Logistics:    Extracts 36 test documents -> agents/logistics/output.json
    2. Financial:    Validates arithmetic, SST, duplicates -> ledger + exceptions (temp dir)
    3. Secretary:    One task per exception, chase emails, final report from the ledger

Output:
    Formatted text (default) or JSON (--json flag)
    Also saves full JSON to agents/logistics/secretary_result.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
LOGISTICS_DIR = PROJECT_ROOT / "agents" / "logistics"
PYTHON = sys.executable

sys.path.insert(0, str(PROJECT_ROOT))
from agents.orchestrator import PipelineOrchestrator, _format_result_text  # noqa: E402


def run_logistics() -> None:
    """Re-extract the test documents into agents/logistics/output.json."""
    print("\n" + "=" * 60)
    print("  STEP 1/4: LOGISTICS AGENT")
    print("  Extracting documents...")
    print("=" * 60)

    result = subprocess.run(
        [PYTHON, str(LOGISTICS_DIR / "process_test_docs.py")],
        cwd=str(LOGISTICS_DIR),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        print(f"  ERROR: Logistics failed (exit {result.returncode})")
        print(result.stderr[-500:])
        sys.exit(1)
    for line in result.stdout.strip().split("\n")[-15:]:
        print(f"  {line}")


def main():
    parser = argparse.ArgumentParser(
        description="Banjir Productivity — Full Month-End Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py                                    # Full pipeline
  python run_pipeline.py --goal "Close out September"       # Custom goal
  python run_pipeline.py --json                             # JSON output
  python run_pipeline.py --skip-logistics                   # Reuse existing output
  python run_pipeline.py --output result.json --json        # Save JSON
        """,
    )
    parser.add_argument("--goal", type=str, default="Close out September",
                        help="Business goal for the run (default: 'Close out September')")
    parser.add_argument("--skip-logistics", action="store_true",
                        help="Skip Logistics, reuse existing agents/logistics/output.json")
    parser.add_argument("--json", action="store_true", help="Output as JSON instead of formatted text")
    parser.add_argument("--output", type=str, default=None, help="Write output to a file")
    parser.add_argument("--auto-approve", action="store_true",
                        help="Mark chase emails approved (TESTING ONLY; nothing is ever sent)")
    args = parser.parse_args()

    print("=" * 60)
    print("  BANJIR PRODUCTIVITY — FULL PIPELINE")
    print(f"  Goal: {args.goal}")
    print("=" * 60)

    if args.skip_logistics and os.path.exists(LOGISTICS_DIR / "output.json"):
        print(f"\n  Skipping Logistics — using existing {LOGISTICS_DIR / 'output.json'}")
    else:
        run_logistics()

    result = PipelineOrchestrator().run(goal=args.goal)
    secretary = result["secretary"]
    if args.auto_approve:
        for email in secretary["chase_emails"]:
            email["status"] = "approved"

    json_output = json.dumps(result, indent=2, ensure_ascii=False, default=str)
    default_save = LOGISTICS_DIR / "secretary_result.json"
    default_save.write_text(json_output, encoding="utf-8")

    print()
    print(json_output if args.json else _format_result_text(result))

    report = secretary["final_report"]
    print(f"\n{'=' * 60}")
    print("  PIPELINE COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Logistics:  {result['logistics']['count']} documents extracted")
    print(f"  Financial:  {result['financial']['exception_count']} exceptions")
    print(f"  Secretary:  {len(secretary['tasks'])} tasks, {len(secretary['chase_emails'])} chase emails")
    print(f"  Report:     Cash in RM {report['cash_in']:.2f}, "
          f"Cash out RM {report['cash_out']:.2f}, "
          f"Net RM {report['net_cash']:.2f}")
    print(f"  JSON saved: {default_save}")

    if args.output:
        Path(args.output).write_text(json_output, encoding="utf-8")
        print(f"  Also saved: {args.output}")


if __name__ == "__main__":
    main()

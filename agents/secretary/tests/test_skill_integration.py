#!/usr/bin/env python
"""Integration tests for the Secretary Agent WorkBuddy skill.

Verifies:
  1. Skill file integrity (SKILL.md exists, has triggers, role, boundaries)
  2. Schema references (5 schemas in references/)
  3. Secretary module import (all src modules loadable)
  4. Sample exception processing (pipeline runs, produces tasks + emails + report)
  5. Priority mapping (duplicate=P1, overdue=P2, escalation=P2, flagged=P3/P4)
  6. Duplicate precedence rule (duplicates sorted first)
  7. Chase email rules (only overdue, always draft status)
  8. Hard boundary enforcement (no doc extraction, no arithmetic validation)
  9. All three skills wired (logistics + financial + secretary)
 10. Full pipeline result format (plan + tasks + emails + report)
 11. Secretary CLI demo mode
 12. Financial -> Secretary handoff
"""

import json
import os
import sys
import subprocess
import importlib

# ---------------------------------------------------------------------------
# Path setup — explicit variables to avoid nesting bugs
# ---------------------------------------------------------------------------

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SECRETARY_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))      # agents/secretary/
_AGENTS_DIR = os.path.dirname(_SECRETARY_DIR)                        # agents/
_PROJECT_ROOT = os.path.dirname(_AGENTS_DIR)                          # project root (hackathon workspace)
_HACKATHON_ROOT = _PROJECT_ROOT

# Add paths
sys.path.insert(0, _SECRETARY_DIR)
sys.path.insert(0, _AGENTS_DIR)
sys.path.insert(0, _PROJECT_ROOT)

# Skill paths
_SKILL_DIR = os.path.join(_PROJECT_ROOT, ".workbuddy-ai", "skills", "secretary-agent")
_SKILL_MD = os.path.join(_SKILL_DIR, "SKILL.md")
_REFERENCES_DIR = os.path.join(_SKILL_DIR, "references")

# Schema paths
_SCHEMA_DIR = os.path.join(_SECRETARY_DIR, "schemas")

# Other skill paths
_LOGISTICS_SKILL = os.path.join(_PROJECT_ROOT, ".workbuddy-ai", "skills", "logistics-coordinator", "SKILL.md")
_FINANCIAL_SKILL = os.path.join(_PROJECT_ROOT, ".workbuddy-ai", "skills", "financial-agent", "SKILL.md")


# ---------------------------------------------------------------------------
# Test framework (minimal)
# ---------------------------------------------------------------------------

_passed = 0
_failed = 0
_errors = []

def check(label, condition, detail=""):
    global _passed, _failed
    if condition:
        _passed += 1
    else:
        _failed += 1
        _errors.append(f"FAIL: {label}" + (f" — {detail}" if detail else ""))

def check_eq(label, actual, expected):
    check(label, actual == expected, f"expected {expected!r}, got {actual!r}")


# ---------------------------------------------------------------------------
# 1. Skill file integrity
# ---------------------------------------------------------------------------

def test_skill_file():
    """Verify SKILL.md exists and has required sections."""
    check("SKILL.md exists", os.path.exists(_SKILL_MD))

    if not os.path.exists(_SKILL_MD):
        return

    content = open(_SKILL_MD, "r", encoding="utf-8").read()
    check("SKILL.md non-empty", len(content) > 1000, f"len={len(content)}")

    # Required sections
    check("Has Trigger section", "## Trigger" in content)
    check("Has Role section", "## Role" in content)
    check("Has Hard Boundaries", "## Hard Boundaries" in content)
    check("Has Pipeline Overview", "## Pipeline Overview" in content or "## Pipeline" in content)
    check("Has Input Schemas", "## Input Schemas" in content or "## Input" in content)
    check("Has Output Schemas", "## Output Schemas" in content or "## Output" in content)
    check("Has Priority Assignment", "## Priority Assignment" in content or "Priority" in content)
    check("Has Chase Email Rules", "Chase Email" in content)
    check("Has CLI Invocation", "## CLI Invocation" in content or "CLI" in content)
    check("Has Financial handoff", "Handoff" in content or "handoff" in content)
    check("Has Schema Swapping", "Schema Swapping" in content or "schema swap" in content.lower())

    # Trigger keywords
    keywords = ["secretary", "plan", "dispatch", "task", "chase email", "overdue",
                "final report", "close out", "exception", "cash flow"]
    for kw in keywords:
        check(f"Has keyword '{kw}'", kw in content.lower(),
              f"keyword '{kw}' not found in SKILL.md")

    # Hard boundaries
    check("Boundary: never extract docs", "never extract" in content.lower() or "never read raw" in content.lower())
    check("Boundary: never validate arithmetic", "never validate" in content.lower() or "never compute" in content.lower())
    check("Boundary: never send email without approval", "never send" in content.lower() and "approval" in content.lower())


# ---------------------------------------------------------------------------
# 2. Schema references
# ---------------------------------------------------------------------------

def test_schema_references():
    """Verify all 5 schema files exist in references/ and are valid JSON."""
    schemas = ["plan.json", "task.json", "chase_email.json",
               "final_report.json", "exception_event.json"]

    for schema_name in schemas:
        ref_path = os.path.join(_REFERENCES_DIR, schema_name)
        check(f"Reference {schema_name} exists", os.path.exists(ref_path))

        if not os.path.exists(ref_path):
            continue

        try:
            data = json.loads(open(ref_path, "r", encoding="utf-8").read())
            check(f"{schema_name} is valid JSON", isinstance(data, dict))
            check(f"{schema_name} has $schema", "$schema" in data)
            check(f"{schema_name} has title", "title" in data)
            check(f"{schema_name} has type", "type" in data)
            check(f"{schema_name} has required", "required" in data)
        except Exception as e:
            check(f"{schema_name} parses", False, str(e))

    # Also check source schemas in agents/secretary/schemas/
    for schema_name in schemas:
        src_path = os.path.join(_SCHEMA_DIR, schema_name)
        check(f"Source {schema_name} exists", os.path.exists(src_path))


# ---------------------------------------------------------------------------
# 3. Secretary module import
# ---------------------------------------------------------------------------

def test_module_import():
    """Verify all Secretary modules can be imported."""
    try:
        from src.config import BUSINESS_NAME, BUSINESS_CURRENCY, PRIORITY_MAP
        check("config imports", True)
        check("BUSINESS_NAME set", BUSINESS_NAME is not None and len(BUSINESS_NAME) > 0)
        check("BUSINESS_CURRENCY is MYR", BUSINESS_CURRENCY == "MYR")
        check("PRIORITY_MAP has duplicate", "duplicate" in PRIORITY_MAP)
        check("PRIORITY_MAP has overdue", "overdue" in PRIORITY_MAP)
        check("PRIORITY_MAP has escalation", "escalation" in PRIORITY_MAP)
        check("PRIORITY_MAP has flagged", "flagged" in PRIORITY_MAP)
        check("duplicate = P1", PRIORITY_MAP["duplicate"] == 1)
        check("overdue = P2", PRIORITY_MAP["overdue"] == 2)
        check("escalation = P2", PRIORITY_MAP["escalation"] == 2)
        check("flagged = P3", PRIORITY_MAP["flagged"] == 3)
    except Exception as e:
        check("config imports", False, str(e))
        return

    try:
        from src.models import (
            ExceptionEvent, DocumentInfo, Task, ChaseEmail,
            Plan, PlanPhase, FinalReport, PipelineResult,
            EventType, Priority, TaskStatus, EmailStatus, PlanPhaseStatus,
            CategorySummary
        )
        check("models import", True)

        # Verify enums
        check("EventType.OVERDUE", EventType.OVERDUE.value == "overdue")
        check("EventType.DUPLICATE", EventType.DUPLICATE.value == "duplicate")
        check("EventType.ESCALATION", EventType.ESCALATION.value == "escalation")
        check("EventType.FLAGGED", EventType.FLAGGED.value == "flagged")

        check("Priority.P1 = 1", Priority.P1_CRITICAL.value == 1)
        check("Priority.P2 = 2", Priority.P2_HIGH.value == 2)
        check("Priority.P3 = 3", Priority.P3_MEDIUM.value == 3)
        check("Priority.P4 = 4", Priority.P4_LOW.value == 4)

        check("TaskStatus.PENDING", TaskStatus.PENDING.value == "pending")
        check("EmailStatus.DRAFT", EmailStatus.DRAFT.value == "draft")
        check("PlanPhaseStatus.PENDING", PlanPhaseStatus.PENDING.value == "pending")

    except Exception as e:
        check("models import", False, str(e))
        return

    try:
        from src.planner import Planner
        check("Planner imports", True)
        planner = Planner()
        plan = planner.generate_plan("Close out September")
        check("Planner generates plan", plan is not None)
        check("Plan has goal", plan.goal == "Close out September")
        check("Plan has phases", len(plan.phases) > 0)
        check("Plan total_phases matches", plan.total_phases == len(plan.phases))
        check("Standard plan has 3 phases", len(plan.phases) == 3)
        check("Phase 1 is Logistics", plan.phases[0].agent == "Logistics")
        check("Phase 2 is Financial", plan.phases[1].agent == "Financial")
        check("Phase 3 is Secretary", plan.phases[2].agent == "Secretary")
    except Exception as e:
        check("Planner imports", False, str(e))

    try:
        from src.task_generator import TaskGenerator
        check("TaskGenerator imports", True)
    except Exception as e:
        check("TaskGenerator imports", False, str(e))

    try:
        from src.email_drafter import EmailDrafter
        check("EmailDrafter imports", True)
    except Exception as e:
        check("EmailDrafter imports", False, str(e))

    try:
        from src.reporter import Reporter
        check("Reporter imports", True)
    except Exception as e:
        check("Reporter imports", False, str(e))

    try:
        from src.secretary import Secretary
        check("Secretary imports", True)

        sec = Secretary()
        check("Secretary instantiates", sec is not None)
        check("Has planner", hasattr(sec, "planner"))
        check("Has task_generator", hasattr(sec, "task_generator"))
        check("Has email_drafter", hasattr(sec, "email_drafter"))
        check("Has reporter", hasattr(sec, "reporter"))
        check("Has run method", hasattr(sec, "run"))
        check("Has format_result", hasattr(sec, "format_result"))
        check("Has result_to_json", hasattr(sec, "result_to_json"))
    except Exception as e:
        check("Secretary imports", False, str(e))


# ---------------------------------------------------------------------------
# 4. Sample exception processing
# ---------------------------------------------------------------------------

def test_sample_processing():
    """Run the Secretary pipeline with sample exceptions."""
    try:
        from src.secretary import Secretary
        from src.models import ExceptionEvent, DocumentInfo
    except Exception as e:
        check("Import for sample test", False, str(e))
        return

    sec = Secretary()

    # Sample exceptions covering all 4 types
    exceptions = [
        ExceptionEvent(
            event_type="duplicate",
            invoice_number="INV-001",
            vendor_name="Tech Supplies Sdn Bhd",
            amount=12500.00,
            invoice_date="2026-09-15",
            details="Duplicate detected.",
            duplicate_of="INV-001 (original)",
        ),
        ExceptionEvent(
            event_type="overdue",
            invoice_number="INV-078",
            vendor_name="Creative Agency Sdn Bhd",
            amount=4800.00,
            invoice_date="2026-09-20",
            due_date="2026-10-05",
            details="Payment overdue.",
        ),
        ExceptionEvent(
            event_type="escalation",
            invoice_number="INV-001",
            vendor_name="Tech Supplies Sdn Bhd",
            amount=12500.00,
            details="Large amount exceeds threshold.",
            escalation_reason="Large amount",
            escalation_code="LARGE_AMOUNT",
        ),
        ExceptionEvent(
            event_type="flagged",
            invoice_number="INV-032",
            vendor_name="Workshop Partners",
            amount=750.00,
            invoice_date="2026-09-22",
            details="Low OCR confidence.",
            flag_reason="Low confidence",
            confidence=0.65,
        ),
    ]

    documents = [
        DocumentInfo(
            doc_id="DOC-001",
            file_name="inv.pdf",
            doc_type="invoice",
            vendor_name="Tech Supplies Sdn Bhd",
            invoice_number="INV-001",
            invoice_date="2026-09-15",
            grand_total=12500.00,
            confidence=0.95,
            quality_flags=[],
        ),
    ]

    result = sec.run(
        goal="Close out September",
        exceptions=exceptions,
        documents=documents,
    )

    # PipelineResult structure
    check("PipelineResult returned", result is not None)
    check("Has plan", result.plan is not None)
    check("Has tasks", hasattr(result, "tasks"))
    check("Has chase_emails", hasattr(result, "chase_emails"))
    check("Has final_report", result.final_report is not None)
    check("exceptions_processed = 4", result.exceptions_processed == 4)

    # Plan
    check("Plan goal matches", result.plan.goal == "Close out September")
    check("Plan has 3 phases", len(result.plan.phases) == 3)

    # Tasks
    check("4 tasks generated", len(result.tasks) == 4)
    check("All tasks have task_id", all(t.task_id.startswith("TASK-") for t in result.tasks))
    check("All tasks have title", all(len(t.title) > 0 for t in result.tasks))
    check("All tasks have action_required", all(len(t.action_required) > 0 for t in result.tasks))
    check("All tasks pending", all(t.status.value == "pending" for t in result.tasks))

    # Chase emails (only for overdue)
    check("1 chase email (overdue only)", len(result.chase_emails) == 1)
    if result.chase_emails:
        email = result.chase_emails[0]
        check("Email has email_id", email.email_id.startswith("EMAIL-"))
        check("Email status is draft", email.status.value == "draft")
        check("Email has subject", len(email.subject) > 0)
        check("Email has body", len(email.body) > 50)
        check("Email related_invoice", email.related_invoice == "INV-078")
        check("Email related_task_id set", email.related_task_id is not None)

    # Final report
    report = result.final_report
    check("Report has goal", report.goal == "Close out September")
    check("Report has cash_in", report.cash_in is not None)
    check("Report has cash_out", report.cash_out is not None)
    check("Report has net_cash", report.net_cash is not None)
    check("Report has categories", hasattr(report, "categories"))
    check("Report total_exceptions = 4", report.total_exceptions == 4)
    check("Report tasks_generated = 4", report.tasks_generated == 4)
    check("Report chase_emails_drafted = 1", report.chase_emails_drafted == 1)
    check("Report chase_emails_approved = 0", report.chase_emails_approved == 0)
    check("Report has top_3_actions", hasattr(report, "top_3_actions"))


# ---------------------------------------------------------------------------
# 5. Priority mapping
# ---------------------------------------------------------------------------

def test_priority_mapping():
    """Verify priority assignment for each exception type."""
    try:
        from src.secretary import Secretary
        from src.models import ExceptionEvent, Priority
    except Exception as e:
        check("Import for priority test", False, str(e))
        return

    sec = Secretary()

    # Duplicate -> P1
    dup = ExceptionEvent(
        event_type="duplicate", invoice_number="INV-D1",
        vendor_name="Vendor A", amount=500.00,
        details="Duplicate.", duplicate_of="INV-D1 (original)",
    )
    result = sec.run(goal="Test", exceptions=[dup])
    check("Duplicate -> P1_CRITICAL", result.tasks[0].priority == Priority.P1_CRITICAL)

    # Overdue -> P2
    ovd = ExceptionEvent(
        event_type="overdue", invoice_number="INV-O1",
        vendor_name="Vendor B", amount=300.00,
        details="Overdue.", due_date="2026-09-01",
    )
    result = sec.run(goal="Test", exceptions=[ovd])
    check("Overdue -> P2_HIGH", result.tasks[0].priority == Priority.P2_HIGH)

    # Escalation -> P2 (default)
    esc = ExceptionEvent(
        event_type="escalation", invoice_number="INV-E1",
        vendor_name="Vendor C", amount=5000.00,
        details="Escalation.", escalation_reason="Test",
        escalation_code="TEST",
    )
    result = sec.run(goal="Test", exceptions=[esc])
    check("Escalation -> P2_HIGH", result.tasks[0].priority == Priority.P2_HIGH)

    # Escalation with large amount -> P1
    esc_large = ExceptionEvent(
        event_type="escalation", invoice_number="INV-E2",
        vendor_name="Vendor D", amount=15000.00,
        details="Large escalation.", escalation_reason="Large",
        escalation_code="LARGE_AMOUNT",
    )
    result = sec.run(goal="Test", exceptions=[esc_large])
    check("Escalation >= 10k -> P1_CRITICAL", result.tasks[0].priority == Priority.P1_CRITICAL)

    # Flagged with confidence < 0.70 -> P3
    flg_low = ExceptionEvent(
        event_type="flagged", invoice_number="INV-F1",
        vendor_name="Vendor E", amount=200.00,
        details="Low confidence.", flag_reason="Low OCR",
        confidence=0.55,
    )
    result = sec.run(goal="Test", exceptions=[flg_low])
    check("Flagged confidence < 0.70 -> P3_MEDIUM", result.tasks[0].priority == Priority.P3_MEDIUM)

    # Flagged with confidence >= 0.70 -> P4
    flg_ok = ExceptionEvent(
        event_type="flagged", invoice_number="INV-F2",
        vendor_name="Vendor F", amount=200.00,
        details="Borderline.", flag_reason="Review",
        confidence=0.75,
    )
    result = sec.run(goal="Test", exceptions=[flg_ok])
    check("Flagged confidence >= 0.70 -> P4_LOW", result.tasks[0].priority == Priority.P4_LOW)


# ---------------------------------------------------------------------------
# 6. Duplicate precedence rule
# ---------------------------------------------------------------------------

def test_duplicate_precedence():
    """Verify duplicates are sorted before overdue."""
    try:
        from src.secretary import Secretary
        from src.models import ExceptionEvent, Priority
    except Exception as e:
        check("Import for precedence test", False, str(e))
        return

    sec = Secretary()

    # Mix of duplicate + overdue on same invoice
    exceptions = [
        ExceptionEvent(
            event_type="overdue", invoice_number="INV-X1",
            vendor_name="Vendor X", amount=800.00,
            details="Overdue.", due_date="2026-09-01",
        ),
        ExceptionEvent(
            event_type="duplicate", invoice_number="INV-X1",
            vendor_name="Vendor X", amount=800.00,
            details="Duplicate.", duplicate_of="INV-X1 (original)",
        ),
    ]

    result = sec.run(goal="Test", exceptions=exceptions)

    # First task should be the duplicate (P1), not overdue (P2)
    check("First task is duplicate", result.tasks[0].event_type.value == "duplicate")
    check("First task is P1", result.tasks[0].priority == Priority.P1_CRITICAL)
    check("Second task is overdue", result.tasks[1].event_type.value == "overdue")
    check("Second task is P2", result.tasks[1].priority == Priority.P2_HIGH)


# ---------------------------------------------------------------------------
# 7. Chase email rules
# ---------------------------------------------------------------------------

def test_chase_email_rules():
    """Verify chase emails only for overdue, always draft status."""
    try:
        from src.secretary import Secretary
        from src.models import ExceptionEvent
    except Exception as e:
        check("Import for email test", False, str(e))
        return

    sec = Secretary()

    # All 4 types, only overdue should get an email
    exceptions = [
        ExceptionEvent(
            event_type="duplicate", invoice_number="INV-1",
            vendor_name="V1", amount=100.00, details="Dup",
            duplicate_of="INV-1 (original)",
        ),
        ExceptionEvent(
            event_type="overdue", invoice_number="INV-2",
            vendor_name="V2", amount=200.00, details="Overdue",
            due_date="2026-09-01",
        ),
        ExceptionEvent(
            event_type="escalation", invoice_number="INV-3",
            vendor_name="V3", amount=300.00, details="Esc",
            escalation_reason="Test", escalation_code="TEST",
        ),
        ExceptionEvent(
            event_type="flagged", invoice_number="INV-4",
            vendor_name="V4", amount=400.00, details="Flag",
            flag_reason="Low", confidence=0.5,
        ),
    ]

    result = sec.run(goal="Test", exceptions=exceptions)

    check("Only 1 chase email (overdue)", len(result.chase_emails) == 1)
    check("Email for overdue invoice", result.chase_emails[0].related_invoice == "INV-2")
    check("Email status = draft", result.chase_emails[0].status.value == "draft")
    check("Email never auto-approved", result.final_report.chase_emails_approved == 0)

    # Verify email body has key elements
    body = result.chase_emails[0].body
    check("Email body has Invoice No", "Invoice No" in body)
    check("Email body has Amount Due", "Amount Due" in body or "RM" in body)
    check("Email body has Due Date", "Due Date" in body)


# ---------------------------------------------------------------------------
# 8. Hard boundary enforcement
# ---------------------------------------------------------------------------

def test_hard_boundaries():
    """Verify Secretary doesn't extract docs or validate arithmetic."""
    try:
        from src.secretary import Secretary
    except Exception as e:
        check("Import for boundary test", False, str(e))
        return

    sec = Secretary()

    # Secretary should not have any document extraction methods
    check("No extract_document method", not hasattr(sec, "extract_document"))
    check("No ocr_document method", not hasattr(sec, "ocr_document"))
    check("No read_pdf method", not hasattr(sec, "read_pdf"))

    # Secretary should not have any arithmetic validation methods
    check("No validate_arithmetic method", not hasattr(sec, "validate_arithmetic"))
    check("No check_sst_rate method", not hasattr(sec, "check_sst_rate"))
    check("No compute_total method", not hasattr(sec, "compute_total"))

    # Secretary should NOT auto-approve emails (default)
    result = sec.run(
        goal="Test",
        exceptions=sec._sample_exceptions(),
    )
    check("No auto-approve by default", result.final_report.chase_emails_approved == 0)
    check("No warnings about auto-approve", len(result.warnings) == 0)

    # With auto_approve=True (testing only)
    result_auto = sec.run(
        goal="Test",
        exceptions=sec._sample_exceptions(),
        auto_approve_emails=True,
    )
    check("Auto-approve produces warning", len(result_auto.warnings) > 0)
    check("Auto-approve sets approved count", result_auto.final_report.chase_emails_approved > 0)


# ---------------------------------------------------------------------------
# 9. All three skills wired
# ---------------------------------------------------------------------------

def test_all_skills_wired():
    """Verify all three agent skills exist."""
    check("Logistics skill exists", os.path.exists(_LOGISTICS_SKILL))
    check("Financial skill exists", os.path.exists(_FINANCIAL_SKILL))
    check("Secretary skill exists", os.path.exists(_SKILL_MD))

    if os.path.exists(_LOGISTICS_SKILL):
        content = open(_LOGISTICS_SKILL, "r", encoding="utf-8").read()
        check("Logistics SKILL.md has Trigger", "## Trigger" in content)
        check("Logistics has never-computes-total", "never" in content.lower() and "total" in content.lower())

    if os.path.exists(_FINANCIAL_SKILL):
        content = open(_FINANCIAL_SKILL, "r", encoding="utf-8").read()
        check("Financial SKILL.md has Trigger", "## Trigger" in content)
        check("Financial has Hard Boundaries", "Hard Boundaries" in content or "hard boundar" in content.lower())

    if os.path.exists(_SKILL_MD):
        content = open(_SKILL_MD, "r", encoding="utf-8").read()
        check("Secretary SKILL.md has Trigger", "## Trigger" in content)
        check("Secretary has Hard Boundaries", "## Hard Boundaries" in content)
        check("Secretary has Pipeline", "Pipeline" in content)


# ---------------------------------------------------------------------------
# 10. Full pipeline result format
# ---------------------------------------------------------------------------

def test_pipeline_result_format():
    """Verify PipelineResult has all required fields."""
    try:
        from src.secretary import Secretary
        from src.models import PipelineResult, Plan, Task, ChaseEmail, FinalReport
    except Exception as e:
        check("Import for format test", False, str(e))
        return

    sec = Secretary()
    result = sec.run(
        goal="Close out September",
        exceptions=sec._sample_exceptions(),
        documents=sec._sample_documents(),
    )

    # JSON serialization
    json_str = sec.result_to_json(result)
    check("result_to_json produces string", isinstance(json_str, str))

    parsed = json.loads(json_str)
    check("JSON has plan", "plan" in parsed)
    check("JSON has tasks", "tasks" in parsed)
    check("JSON has chase_emails", "chase_emails" in parsed)
    check("JSON has final_report", "final_report" in parsed)
    check("JSON has exceptions_processed", "exceptions_processed" in parsed)
    check("JSON has warnings", "warnings" in parsed)

    # Plan structure
    plan = parsed["plan"]
    check("Plan has goal", "goal" in plan)
    check("Plan has phases", "phases" in plan)
    check("Plan has total_phases", "total_phases" in plan)
    check("Plan has created_at", "created_at" in plan)

    # Tasks structure
    if parsed["tasks"]:
        task = parsed["tasks"][0]
        check("Task has task_id", "task_id" in task)
        check("Task has title", "title" in task)
        check("Task has priority", "priority" in task)
        check("Task has action_required", "action_required" in task)
        check("Task has status", "status" in task)

    # Chase emails structure
    if parsed["chase_emails"]:
        email = parsed["chase_emails"][0]
        check("Email has email_id", "email_id" in email)
        check("Email has subject", "subject" in email)
        check("Email has body", "body" in email)
        check("Email has status", "status" in email)
        check("Email status = draft", email["status"] == "draft")

    # Final report structure
    report = parsed["final_report"]
    check("Report has goal", "goal" in report)
    check("Report has period", "period" in report)
    check("Report has cash_in", "cash_in" in report)
    check("Report has cash_out", "cash_out" in report)
    check("Report has net_cash", "net_cash" in report)
    check("Report has categories", "categories" in report)
    check("Report has top_3_actions", "top_3_actions" in report)
    check("Report has total_exceptions", "total_exceptions" in report)
    check("Report has tasks_generated", "tasks_generated" in report)
    check("Report has chase_emails_drafted", "chase_emails_drafted" in report)

    # Formatted text output
    text = sec.format_result(result)
    check("format_result produces string", isinstance(text, str))
    check("Text has EXECUTION PLAN", "EXECUTION PLAN" in text or "PLAN" in text)
    check("Text has TASK LIST", "TASK" in text)
    check("Text has report section", "CASH" in text or "cash" in text.lower() or "SUMMARY" in text)


# ---------------------------------------------------------------------------
# 11. Secretary CLI demo mode
# ---------------------------------------------------------------------------

def test_cli_demo():
    """Verify the CLI can run in demo mode."""
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "src.cli", "--demo",
            ],
            cwd=_SECRETARY_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        check("CLI demo exits 0", result.returncode == 0,
              f"returncode={result.returncode}, stderr={result.stderr[:300]}")
        check("CLI demo has EXECUTION PLAN", "EXECUTION PLAN" in result.stdout or "PLAN" in result.stdout)
        check("CLI demo has TASK", "TASK" in result.stdout)
    except Exception as e:
        check("CLI demo runs", False, str(e))

    # JSON mode
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "src.cli", "--demo", "--json",
            ],
            cwd=_SECRETARY_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        check("CLI JSON exits 0", result.returncode == 0,
              f"returncode={result.returncode}, stderr={result.stderr[:300]}")
        if result.returncode == 0:
            # CLI prints "Running in DEMO mode..." before JSON, so find the JSON start
            json_start = result.stdout.find("{")
            check("CLI JSON has JSON content", json_start >= 0)
            if json_start >= 0:
                parsed = json.loads(result.stdout[json_start:])
                check("CLI JSON has plan", "plan" in parsed)
                check("CLI JSON has tasks", "tasks" in parsed)
                check("CLI JSON has final_report", "final_report" in parsed)
    except Exception as e:
        check("CLI JSON runs", False, str(e))


# ---------------------------------------------------------------------------
# 12. Financial -> Secretary handoff
# ---------------------------------------------------------------------------

def test_financial_handoff():
    """Verify Secretary can process Financial's exception format."""
    try:
        from src.secretary import Secretary
        from src.models import ExceptionEvent
    except Exception as e:
        check("Import for handoff test", False, str(e))
        return

    # Simulate Financial's exception output format
    financial_exceptions = [
        {
            "event_type": "duplicate",
            "invoice_number": "INV-2026-020",
            "vendor_name": "TechCorp Sdn Bhd",
            "amount": 4500.00,
            "currency": "MYR",
            "invoice_date": "2026-09-10",
            "details": "Invoice number and amount match existing entry.",
            "duplicate_of": "INV-2026-020 (original from 2026-09-11)",
        },
        {
            "event_type": "overdue",
            "invoice_number": "INV-2026-035",
            "vendor_name": "Office Supplies Co",
            "amount": 1200.00,
            "currency": "MYR",
            "invoice_date": "2026-09-15",
            "due_date": "2026-09-30",
            "details": "Payment was due on 2026-09-30. No payment record found.",
        },
        {
            "event_type": "escalation",
            "invoice_number": "INV-2026-040",
            "vendor_name": "BigVendor Sdn Bhd",
            "amount": 15000.00,
            "currency": "MYR",
            "invoice_date": "2026-09-20",
            "details": "Single invoice exceeds RM 10,000 threshold.",
            "escalation_reason": "Large amount exceeds threshold",
            "escalation_code": "LARGE_AMOUNT",
        },
        {
            "event_type": "flagged",
            "invoice_number": "INV-2026-036",
            "vendor_name": "Blurry Docs Ltd",
            "amount": 350.00,
            "currency": "MYR",
            "invoice_date": "2026-09-22",
            "details": "OCR confidence is 0.65.",
            "flag_reason": "Low OCR confidence",
            "confidence": 0.65,
        },
    ]

    # Parse Financial's output into ExceptionEvent objects
    events = [ExceptionEvent(**e) for e in financial_exceptions]
    check("Parsed 4 Financial exceptions", len(events) == 4)

    sec = Secretary()
    result = sec.run(goal="Close out September", exceptions=events)

    check("Handoff: 4 tasks generated", len(result.tasks) == 4)
    check("Handoff: 1 chase email (overdue only)", len(result.chase_emails) == 1)
    check("Handoff: duplicate is P1", result.tasks[0].event_type.value == "duplicate")
    check("Handoff: large escalation is P1", any(
        t.priority.value == 1 and t.event_type.value == "escalation"
        for t in result.tasks
    ))
    check("Handoff: report total_exceptions = 4", result.final_report.total_exceptions == 4)
    check("Handoff: report tasks_generated = 4", result.final_report.tasks_generated == 4)

    # JSON output round-trips
    json_out = sec.result_to_json(result)
    reparsed = json.loads(json_out)
    check("Handoff: JSON round-trips", "plan" in reparsed and "tasks" in reparsed)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  Secretary Agent — Skill Integration Tests")
    print("=" * 60)
    print()

    tests = [
        ("1. Skill File Integrity", test_skill_file),
        ("2. Schema References", test_schema_references),
        ("3. Module Import", test_module_import),
        ("4. Sample Exception Processing", test_sample_processing),
        ("5. Priority Mapping", test_priority_mapping),
        ("6. Duplicate Precedence", test_duplicate_precedence),
        ("7. Chase Email Rules", test_chase_email_rules),
        ("8. Hard Boundary Enforcement", test_hard_boundaries),
        ("9. All Three Skills Wired", test_all_skills_wired),
        ("10. Pipeline Result Format", test_pipeline_result_format),
        ("11. CLI Demo Mode", test_cli_demo),
        ("12. Financial -> Secretary Handoff", test_financial_handoff),
    ]

    for name, func in tests:
        print(f"  Running: {name}...")
        try:
            func()
        except Exception as e:
            check(f"{name} (unhandled)", False, str(e))
        print(f"    done")

    print()
    print("=" * 60)
    print(f"  Results: {_passed} passed, {_failed} failed")
    print("=" * 60)

    if _errors:
        print()
        for err in _errors:
            print(f"  {err}")

    return 1 if _failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

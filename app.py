#!/usr/bin/env python
"""
Banjir Productivity — Flask API Server
======================================

Exposes the 3-agent pipeline as a REST API for a frontend webapp.

Endpoints:
    POST /api/run          — Run the full pipeline with a goal
    GET  /api/status       — Check LLM + pipeline status
    GET  /api/health        — Health check

Usage:
    python app.py                      # Default port 5000
    python app.py --port 8080          # Custom port
    python app.py --host 0.0.0.0      # Network accessible

Environment variables (all optional):
    LLM_API_URL   — OpenAI-compatible base URL
    LLM_API_KEY   — API key
    LLM_MODEL     — Model name
    LLM_VISION_MODEL — Vision model name

Example frontend call:
    fetch('/api/run', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({goal: 'Close out September'})
    })
    .then(r => r.json())
    .then(data => {
        // data.plan.phases -> render in plan panel
        // data.logistics.records -> render in logistics panel
        // data.financial.ledger + exceptions -> render in financial panel
        // data.secretary.tasks + chase_emails + final_report -> render in secretary panel
    });
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
import traceback
from pathlib import Path

# Ensure agents/ is importable
PROJECT_ROOT = Path(__file__).resolve().parent
AGENTS_DIR = PROJECT_ROOT / "agents"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(AGENTS_DIR))

# ---------------------------------------------------------------------------
# Flask setup
# ---------------------------------------------------------------------------

try:
    from flask import Flask, Response, request, jsonify, send_from_directory, redirect
except ImportError:
    print("Flask not installed. Run: pip install flask")
    print("Or: pip install -r requirements.txt")
    sys.exit(1)

try:
    from agents.orchestrator import PipelineOrchestrator, discover_document_images, LLM_API_URL, LLM_MODEL
except ImportError as e:
    print(f"Failed to import orchestrator: {e}")
    print("Make sure agents/orchestrator.py exists")
    sys.exit(1)

app = Flask(__name__, static_folder=None)

# Global orchestrator instance (initialized on first use)
_orchestrator: PipelineOrchestrator | None = None


def get_orchestrator() -> PipelineOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = PipelineOrchestrator()
    return _orchestrator


# ---------------------------------------------------------------------------
# CORS (for development)
# ---------------------------------------------------------------------------

@app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return resp


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/api/health", methods=["GET"])
def health():
    """Simple health check."""
    return jsonify({
        "status": "ok",
        "service": "banjir-productivity",
        "time": time.time(),
    })


@app.route("/api/status", methods=["GET"])
def status():
    """Check LLM endpoint and pipeline readiness."""
    orch = get_orchestrator()
    llm_available = orch._llm_available()
    images = discover_document_images()

    logistics_output = AGENTS_DIR / "logistics" / "output.json"
    has_preextracted = logistics_output.exists()

    return jsonify({
        "llm": {
            "enabled": orch.llm_enabled,
            "available": llm_available,
            "endpoint": LLM_API_URL,
            "model": LLM_MODEL,
        },
        "documents": {
            "images_available": len(images),
            "pre_extracted_available": has_preextracted,
            "test_docs_dir": str(PROJECT_ROOT / "test-documents"),
        },
        "agents": {
            "logistics": "ready" if (has_preextracted or images) else "no_documents",
            "financial": "ready",
            "secretary": "ready",
        },
    })


@app.route("/api/run", methods=["POST", "OPTIONS"])
def run_pipeline():
    """Run the full 3-agent pipeline.

    Request body (JSON):
        {
            "goal": "Close out September",        // required
            "use_images": false                   // optional: use LLM vision extraction
        }

    Response (JSON):
        {
            "success": true,
            "goal": "...",
            "plan": {phases: [...]},
            "logistics": {records: [...], count: N, summary: {...}},
            "financial": {ledger: {...}, exceptions: {...}, exception_count: N},
            "secretary": {tasks: [...], chase_emails: [...], final_report: {...}},
            "timings": {step1: Xs, ...},
            "sources": {plan: "llm"|"python_fallback", ...}
        }

    On error:
        {"success": false, "error": "message", "traceback": "..."}
    """
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"})

    # Parse request
    data = request.get_json(silent=True) or {}
    goal = data.get("goal", "Close out September")
    use_images = data.get("use_images", False)

    try:
        orch = get_orchestrator()

        # Determine if we should use LLM vision extraction
        document_images = None
        if use_images:
            document_images = discover_document_images()

        # Run the pipeline
        result = orch.run(goal=goal, document_images=document_images)

        return jsonify({
            "success": True,
            **result,
        })

    except Exception as e:
        traceback_str = traceback.format_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback_str,
        }), 500


@app.route("/api/run/stream", methods=["POST"])
def run_pipeline_stream():
    """Same as /api/run, streamed as NDJSON so the page can show each agent's progress.

    Lines: {"kind": "status", "agent", "status", "step"} as agents start/finish,
    then one {"kind": "result", "data": {...same body as /api/run...}}
    or {"kind": "error", "error": "..."}.
    """
    data = request.get_json(silent=True) or {}
    goal = data.get("goal", "Close out September")
    document_images = discover_document_images() if data.get("use_images") else None
    events: queue.Queue = queue.Queue()

    def work():
        try:
            result = get_orchestrator().run(goal=goal, document_images=document_images, on_event=events.put)
            events.put({"kind": "result", "data": {"success": True, **result}})
        except Exception as e:
            events.put({"kind": "error", "error": str(e)})
        finally:
            events.put(None)

    threading.Thread(target=work, daemon=True).start()

    def stream():
        while (item := events.get()) is not None:
            yield json.dumps(item, ensure_ascii=False, default=str) + "\n"

    return Response(stream(), mimetype="application/x-ndjson", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@app.route("/api/documents/<path:ref>", methods=["GET"])
def source_document(ref):
    """Serve a source document image so every exception/ledger row can be traced.

    Only files under test-documents/; send_from_directory rejects path traversal.
    """
    if not ref.startswith("test-documents/"):
        return jsonify({"error": "not found"}), 404
    return send_from_directory(str(PROJECT_ROOT), ref)


@app.route("/api/tasks/<task_id>/approve", methods=["POST"])
def approve_task(task_id):
    """Approve a task (placeholder for frontend integration)."""
    return jsonify({
        "success": True,
        "task_id": task_id,
        "status": "approved",
        "message": f"Task {task_id} approved.",
    })


@app.route("/api/emails/<email_id>/approve", methods=["POST"])
def approve_email(email_id):
    """Approve a chase email for sending (human-in-the-loop)."""
    return jsonify({
        "success": True,
        "email_id": email_id,
        "status": "approved",
        "message": f"Email {email_id} approved for sending.",
    })


@app.route("/api/emails/<email_id>/reject", methods=["POST"])
def reject_email(email_id):
    """Reject a chase email draft."""
    return jsonify({
        "success": True,
        "email_id": email_id,
        "status": "rejected",
        "message": f"Email {email_id} rejected.",
    })


# ---------------------------------------------------------------------------
# Serve frontend (if it exists)
# ---------------------------------------------------------------------------

FRONTEND_DIR = PROJECT_ROOT / "frontend"

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    """Serve the frontend SPA if it exists."""
    if not path and (FRONTEND_DIR / "web-office" / "index.html").exists():
        return redirect("/web-office/")
    if FRONTEND_DIR.exists():
        target = FRONTEND_DIR / path
        if path and target.is_dir() and (target / "index.html").exists():
            # Trailing slash keeps the page's relative asset URLs inside the folder
            if not path.endswith("/"):
                return redirect("/" + path + "/")
            return send_from_directory(str(target), "index.html")
        if path and target.is_file():
            return send_from_directory(str(FRONTEND_DIR), path)
        return send_from_directory(str(FRONTEND_DIR), "index.html")
    return jsonify({
        "message": "Banjir Productivity API",
        "endpoints": ["/api/run", "/api/status", "/api/health"],
        "frontend": "not found — create a frontend/ directory with index.html",
    })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Banjir Productivity — Flask API Server",
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1",
        help="Host to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port", type=int, default=5000,
        help="Port to bind (default: 5000)",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable Flask debug mode (auto-reload)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  BANJIR PRODUCTIVITY — API SERVER")
    print(f"  URL: http://{args.host}:{args.port}")
    print(f"  Endpoints:")
    print(f"    POST /api/run        — Run pipeline")
    print(f"    GET  /api/status     — Check status")
    print(f"    GET  /api/health      — Health check")
    print("=" * 60)

    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
    )


if __name__ == "__main__":
    main()

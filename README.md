# Dormathon Banjir Productivity

Three AI agents on WorkBuddy that take a single prompt and close a micro-business's month end to end.

## The Demo

**Prompt:** "Close out September."

Then, with no further input:
1. **Secretary** reads the goal, writes the plan on screen, dispatches.
2. **Logistics** collects and organises ~40 documents — invoices, receipts, orders.
3. **Financial** builds the ledger, reconciles, raises exceptions.
4. **Secretary** turns exceptions into tasks and reports to the front end.

**Output:** a reconciled ledger, an exception list with a reason per item, and two drafted chase emails awaiting approval. Every number traces back to a source document.

## Hard Boundary

Logistics owns documents, Financial owns numbers. Logistics hands over structured records and **never computes a total**.

## Team

| Role | Owner | Status |
|------|-------|--------|
| Logistics Coordinator | @Colt Tan | In progress |
| Financial Agent | TBD | In progress |
| Secretary Agent | TBD | Stub phase |
| Frontend | TBD | P0 components |
| Test Documents | TBD | Generating 40 docs |

## Timeline (Oct 10–12, 2026)

| Gate | Target |
|------|--------|
| 15:00 Sat | Workspace set up, first 15 test documents ready |
| 18:00 Sat | 1 document in → 1 ledger row out |
| 23:00 Sat | All 40 documents run, validation working |
| 01:00 Sun | Record backup demo video |
| 04:00 Sun | Hard stop on new features |
| 06:00 Sun | Slides done, rehearse to 3 min |
| 08:00 Sun | Submitted |

## Running It

Install dependencies once:

```
pip install -r requirements.txt
```

### Full pipeline (command line)

```
python run_pipeline.py --goal "Close out September"
```

Runs Logistics → Financial → Secretary on the test documents. `python run_pipeline.py --help` lists options.

### Web app (3D office + real agents)

```
python app.py
```

Then open **http://127.0.0.1:5000** (redirects to `/web-office/`). `app.py` serves both the 3D office page and the API, so they share one origin. Double-clicking `index.html` won't work.

- Left-drag: rotate · Scroll: zoom · Right-drag or Shift+drag: pan · R or "恢复视角": reset view
- Type a goal in the bottom bar and click "开始运行". The page calls `POST /api/run`, which runs all three agents;
  the cards show record / exception / task counts when it finishes. The full result is in the browser console as `lastRun`.
- `/api/run` returns only when the whole pipeline is done, so all three cards show "working" together.
- Each run rewrites `agents/logistics/output.json`, `ledger.json` and `exceptions.json`.

### Gmail (optional)

With a Gmail account connected, each run also pulls invoice/receipt/PO emails, reads their attachments with the LLM, and adds them to the documents on file.

1. Put a Google OAuth `credentials.json` in `agents/secretary/` (see `agents/secretary/schemas/prompts/gmail_setup_guide.md`) and `pip install -r agents/secretary/requirements.txt`.
2. Log in once: `cd agents/secretary` then `python -m src.cli --gmail` (opens a browser, saves `token.json`).
3. Run as usual. The result's `gmail` field (and the Logistics card) shows emails found and documents extracted; Gmail documents have `source_ref` `gmail:<message_id>/<file>`.

Needs an LLM (`.env`) to read attachments. Both JSON files are gitignored.

### 3D office in Godot (with real agents)

1. Start the bridge: `python frontend/godot-office/bridge/server.py --port 8765`
2. In Godot 4.x, import `frontend/godot-office/project.godot` and run it (F5).
3. Click "连接本机桥接" (connect bridge), then "运行仓库测试" (run repo test).

The bridge runs the repo's `agents/` and writes results to `frontend/godot-office/bridge/runs/<job_id>/`.
Bridge self-test: `python frontend/godot-office/bridge/test_bridge.py`

## Project Structure

```
.
├── agents/
│   ├── logistics/          # Document extraction agent
│   ├── financial/          # Ledger, reconciliation, exceptions
│   ├── secretary/          # Plan, tasks, report, chase emails
│   └── orchestrator.py     # LLM orchestrator used by app.py
├── frontend/
│   ├── components/         # Frontend component placeholders
│   ├── web-office/         # Browser 3D office viewer (three.js)
│   └── godot-office/       # Godot 3D office + Python bridge to the agents
├── office-3d/              # Blender source models, renders, build scripts
├── app.py                  # Flask API server
├── run_pipeline.py         # Standalone full pipeline
├── test-documents/         # Test invoices, receipts, orders, bad docs
├── rules/                  # Shared rules (duplicate, tolerance, categories, escalation)
├── slides/                 # Pitch slides (PDF for submission)
└── docs/                   # Architecture and design docs
```

## Out of Scope

Marketing, customer feedback, role dropdown, regulatory forms, login and user accounts.

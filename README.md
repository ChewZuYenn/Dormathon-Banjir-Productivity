# Dormathon Banjir Productivity

Three AI agents on WorkBuddy that take a single prompt and close a micro-business's month end to end.

> **AI Summary** (auto-generated, 2026-10-10)
>
> **What it does:** A user types "Close out September." Three AI agents work in sequence — Secretary plans, Logistics extracts ~36 documents (invoices, receipts, orders), Financial validates arithmetic/SST/duplicates and builds a reconciled ledger, then Secretary turns exceptions into tasks, chase emails, and a final report.
>
> **Status:** End-to-end pipeline working. CLI (`run_pipeline.py`) and web app (`app.py` + 3D office) both functional. 36 test documents → 63 ledger rows, 57 exceptions (8 critical) → 20 tasks + 2 patterns across the document set (20 invoices with no payment terms, 17 with no matching PO on file), 2 draft chase emails. Secretary plan and report written by Gemini Flash Lite; Gmail integration for email attachments.
>
> **Numbers:** a **payables close**: all 36 documents are purchases, so RM 0 in / RM 13,171.40 out (incl. SST) / net −RM 13,171.40. **RM 1,315.00 at risk**: duplicate INV-2026-020 (RM 1,111.00) plus totals that don't add up on PO-2026-A05 (RM 189.00) and INV-2026-016 (RM 15.00). 18 exception types defined across 10 validation steps.
>
> **Built by:** 4 contributors in ~6 hours (Oct 10, 2026). Python 3.13, Flask, Three.js, Godot 4, Blender.

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
| Logistics Agent | @Colt Tan | Done — 36 docs, 6 modules, schemas + tests |
| Financial Agent | @Chew Zu Yenn | Done — engine, 18 exception types, schema-validated |
| Secretary Agent | @hyang00122022 (TAO) | Done — planner, tasks, emails, report, Gmail crawler |
| 3D Frontend | @Xuanyu | Done — Blender model, Three.js web, Godot + bridge |
| Backend / Integration | @Colt Tan | Done — orchestrator, Flask API, `run_pipeline.py` |

## TODO

### Done
- [x] Logistics agent: 36 documents extracted, structured records, schemas
- [x] Financial agent: `engine.py`, 10 validation steps, 18 exception types, ledger + exception schemas
- [x] Secretary agent: plan, tasks, chase emails, final report, Gmail crawler
- [x] Full pipeline CLI (`run_pipeline.py`) — Logistics → Financial → Secretary
- [x] Flask API server (`app.py`) — `POST /api/run` with LLM fallback
- [x] 3D office web frontend (Three.js + WebGL)
- [x] 3D office Godot frontend + Python bridge
- [x] Blender 3D models and renders
- [x] Data contract audit: 0 schema errors across all 5 schemas + 36 records
- [x] Test documents: 44 files (invoices, receipts, orders, bad docs)

### Before 04:00 Sun (feature freeze)
- [ ] **Fix chase emails** — Python fallback returns 0 emails; demo promises 2 drafted chase emails
- [ ] **Web UI: results panel** — currently shows counts only; need ledger/exception/task views (placeholders in `frontend/components/`)
- [ ] **Commit missing SKILL.md** — Financial and Logistics WorkBuddy skills not committed (causes 2 test failures)
- [ ] **Per-agent progress on web** — `/api/run` is synchronous; port the bridge's job + polling pattern to `app.py`
- [ ] **Slides** — `slides/` is empty; need pitch deck (PDF, 3-min rehearsal)

### After freeze / polish
- [ ] **Demo video** — record backup demo video (01:00 Sun gate)
- [ ] **Clean tracked `__pycache__`** — 9 `.pyc` files tracked despite `.gitignore`
- [ ] **Fix `.gitignore`** — root ignores `*.html` (blocks new HTML files; existing `index.html` is tracked)
- [ ] **Hard-coded `TODAY`** in `engine.py` (2026-10-10); period is a label only, records not filtered by month
- [ ] **Gmail on real inbox** — tested with simulated attachments only; PDFs sent to Gemini unverified
- [ ] **Approval endpoints** — `/api/tasks/<id>/approve`, `/api/emails/<id>/approve|reject` are placeholders
- [ ] **LLM probe delay** — ~12s per run, partly from probing `localhost:11434` that isn't there

## Timeline (Oct 10-12, 2026)

| Gate | Target | Status |
|------|--------|--------|
| 15:00 Sat | Workspace set up, first 15 test documents ready | Done (36 docs) |
| 18:00 Sat | 1 document in -> 1 ledger row out | Done |
| 23:00 Sat | All 40 documents run, validation working | Done (36 docs, end-to-end via `/api/run`) |
| 01:00 Sun | Record backup demo video | Open |
| 04:00 Sun | Hard stop on new features | Open |
| 06:00 Sun | Slides done, rehearse to 3 min | Open (`slides/` empty) |
| 08:00 Sun | Submitted | Open |

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

- Left-drag: rotate · Scroll: zoom · Right-drag or Shift+drag: pan · R or "Reset view": reset view
- Type a goal in the bottom bar and click "Run". The page calls `POST /api/run/stream`, which runs all three agents and streams
  each agent's progress (the cards light up one at a time: Secretary plan → Logistics → Financial → Secretary report), then fills:
  - **Plan** (above the cards): the Secretary's phases, each turning Working → Done as its agent finishes, plus which parts ran on
    Gemini vs. rules (`sources` in the result).
  - **AI Summary** (left): RM at risk (duplicate invoice totals + gaps on totals that don't add up; `money_at_risk` in `agents/orchestrator.py`), then exceptions grouped by type, critical first, plus the Secretary's top 3 actions.
  - **Checklist** (right): one fix item per task; a problem that hits 5+ documents (no due date, PO not on file) is one line
    (`SYSTEMIC_TYPES` in `agents/orchestrator.py`). The Exceptions tab still lists every exception. Ticks are saved in the browser.
  - **Results** (below the cards): Report · Exceptions · Tasks · Chase emails · Ledger. "view" opens the source document image (`/api/documents/test-documents/...`).
  - **Export CSV | AutoCount** (right of the tabs): downloads the ledger as one row per line in AutoCount's AP invoice import layout (`DocNo`, `DocDate`, `SupplierInvoiceNo`, `AccNo`, `Amount`, `TaxCode`, `TaxAmt`, …), duplicate copy excluded so it matches the ledger total. `CreditorCode` is blank and `AccNo` holds our category code: map both to your AutoCount codes in the import wizard. Built in the browser from the run, no server call.
  The full JSON is in the browser console as `lastRun`.
- **Gemini locally:** put `LLM_API_URL=https://generativelanguage.googleapis.com/v1beta/openai`, `LLM_API_KEY=<your key>` and
  `LLM_MODEL=gemini-3.1-flash-lite` in a repo-root `.env` (gitignored). Without it the plan and report fall back to rules and
  `sources` says `python_fallback`. Check with `python agents/orchestrator.py --llm-status`.
- How the Secretary step works: tasks come from the Python task generator (one per exception, minus the patterns above); Gemini writes the chase emails
  (one per vendor invoice/receipt with conflicting figures or totals that don't add up; template if no LLM) and the top 3 actions;
  every figure in the report is overwritten from the Financial ledger, so the report can't disagree with it.
- **Data note — SST 10%:** every generated test document prints "SST 10%". That's an artifact of the template used to generate the data,
  not a problem with the agents, so the Financial engine accepts 10% (`TEMPLATE_SST_RATES` in `agents/financial/engine.py`).
  Tax amounts that don't match the printed rate are still flagged. Remove it before running on real documents.
- **"Read the 36 scans live with Gemini"** (toggle above the cards, off by default): Logistics reads every scan with Gemini
  (4 in parallel, ~25 s, ~38 API calls) instead of loading the hand-checked `agents/logistics/output.json`, then checks itself
  against it (type, vendor, number, dates, references, every printed amount, conflicting-figure flag). Latest live run:
  337/339 fields matched, same 57 exceptions and 2 chase emails as the hand-checked run. Off by default
  to save free-tier quota; turn it on to show real extraction.
- `POST /api/run` (same body, one JSON response) still works for scripts. Neither endpoint modifies repo files (Financial works in a temp dir).
- `python run_pipeline.py` runs the same orchestrator from the command line (same tasks, emails and figures as the site).
- WorkBuddy skills for all three agents are in `.workbuddy-ai/skills/` (secretary-agent, logistics-coordinator, financial-agent).

### Live deployment (Vercel)

**https://dormathon-banjir-productivity.vercel.app** — same `app.py` (web page + `/api/run`), Gemini via Vercel environment variables `LLM_API_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_VISION_MODEL`, plus `LLM_TIMEOUT=20` (seconds per Gemini call; a slow call falls back to Python instead of running into the function time limit). Optional: `LLM_CONCURRENCY` (parallel scans in live mode, default 4). `.vercelignore` keeps `.env`, Gmail credentials, Blender/Godot assets and tests out of the upload. Gmail is not available there (no persistent Google login on serverless).

Redeploy: `npx vercel deploy --prod` (Vercel project `coltonthatgoods-projects/dormathon-banjir-productivity`). After changing an environment variable, redeploy for it to take effect.

### Gmail (optional)

With a Gmail account connected, each run also pulls invoice/receipt/PO emails, reads their attachments with the LLM, and adds them to the documents on file.

1. Put a Google OAuth `credentials.json` in `agents/secretary/` (see `agents/secretary/schemas/prompts/gmail_setup_guide.md`) and `pip install -r agents/secretary/requirements.txt`.
2. Log in once: `cd agents/secretary` then `python -m src.cli --gmail` (opens a browser, saves `token.json`).
3. Run as usual. The result's `gmail` field (and the Logistics card) shows emails found and documents extracted; Gmail documents have `source_ref` `gmail:<message_id>/<file>`.

Needs an LLM (`.env`) to read attachments. Both JSON files are gitignored.

### 3D office in Godot (with real agents)

1. Start the bridge: `python frontend/godot-office/bridge/server.py --port 8765`
2. In Godot 4.x, import `frontend/godot-office/project.godot` and run it (F5).
3. Click "Connect bridge", then "Run repo test".

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

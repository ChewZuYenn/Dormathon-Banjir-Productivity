# Handoff — Banjir Productivity

_As of 2026-10-10 evening (Dormathon, Oct 10–12). Based on the full commit history of `main`._

Three AI agents (Secretary, Logistics, Financial) take one prompt — "Close out September" — and close a micro-business's month: extract ~36 documents, build a reconciled ledger, raise exceptions, and turn them into tasks and chase emails. See [README.md](README.md) for the pitch and run commands.

---

## 1. Current state at a glance

| Area | State | Where |
|---|---|---|
| Logistics agent | Working. 36 docs → structured records (Python, pre-extracted). | `agents/logistics/` |
| Financial agent | Working. 63 ledger rows, 92 exceptions on the real data. | `agents/financial/engine.py` |
| Secretary agent | Working. Plan, tasks, chase emails, final report. | `agents/secretary/` |
| Full pipeline (CLI) | Working, no WorkBuddy needed. | `run_pipeline.py` |
| API server | Working. `POST /api/run` runs all three agents (~12 s). | `app.py`, `agents/orchestrator.py` |
| Web frontend | 3D office (three.js) wired to `/api/run`. Shows counts only. | `frontend/web-office/` |
| Godot frontend | 3D office + live per-agent status via its own bridge. | `frontend/godot-office/` |
| WorkBuddy skills | Only Secretary is committed. Financial/Logistics `SKILL.md` missing. | `.workbuddy-ai/skills/` |
| 3D source assets | Blender models, renders, build scripts. | `office-3d/` |

**Demo path that works today:** `pip install -r requirements.txt` → `python app.py` → open http://127.0.0.1:5000 → type a goal → "Run".

---

## 2. How to run

```
pip install -r requirements.txt

python run_pipeline.py --goal "Close out September"   # CLI, all three agents
python app.py                                          # API + web app on :5000

# Godot path (optional)
python frontend/godot-office/bridge/server.py --port 8765
# then import frontend/godot-office/project.godot in Godot 4.x and press F5
```

Optional LLM (OpenAI-compatible) via env vars or a gitignored repo-root `.env` (loaded by `agents/orchestrator.py`): `LLM_API_URL` (no trailing slash; default `http://localhost:11434/v1`), `LLM_API_KEY`, `LLM_MODEL`, `LLM_VISION_MODEL`. Current setup uses Gemini `gemini-3.1-flash-lite` (`LLM_API_URL=https://generativelanguage.googleapis.com/v1beta/openai`) — ask Colt for the key. Without an LLM, every step falls back to Python (`sources` in the response says which ran). With Gemini, plan + Secretary run on the LLM (~6.5 s); chase emails are still 0.

---

## 3. Architecture

```
                 goal
                  │
   ┌──────────────▼───────────────┐
   │ Secretary — plan             │  LLM or Python fallback
   └──────────────┬───────────────┘
   ┌──────────────▼───────────────┐
   │ Logistics — documents        │  → records (never computes totals)
   └──────────────┬───────────────┘
   ┌──────────────▼───────────────┐
   │ Financial — numbers          │  → ledger + exceptions (Python engine)
   └──────────────┬───────────────┘
   ┌──────────────▼───────────────┐
   │ Secretary — tasks/emails/    │  LLM or Python fallback
   │ report                       │
   └──────────────────────────────┘
```

**Hard boundary:** Logistics owns documents, Financial owns numbers. Logistics output carries `total_computed_by_logistics = False`.

**Two backends exist** — know which one you're touching:

| | `app.py` (Flask, :5000) | Godot bridge (stdlib, :8765) |
|---|---|---|
| Used by | Web frontend | Godot frontend |
| Entry | `agents/orchestrator.py` | `frontend/godot-office/bridge/worker.py` |
| API | `POST /api/run` — synchronous, one big JSON | `POST /jobs` → poll `GET /jobs/<id>` — async, per-agent status |
| LLM | Optional | None |
| Browser access | Yes (CORS `*`) | Rejects any request with an `Origin` header (by design) |

Key response fields from `/api/run`: `plan.phases`, `logistics.records` / `count`, `financial.ledger` / `exceptions` / `exception_count`, `secretary.tasks` / `chase_emails` / `final_report`, `timings`, `sources`.

---

## 4. History (from commits)

All on 2026-10-10.

**Scaffold — 13:05–14:47** · Chew Zu Yenn, Colt
- `7e9a3bf` Initial commit. `ae70063` renamed project "Kween" → "Banjir Productivity".
- `e89f81c` Scaffold: 3 agent configs, extraction schemas (invoice/receipt/order), shared rules, financial validation, categories, architecture doc, secretary email template.

**Logistics — 15:25–16:09** · Colt
- `9405cf4` Full pipeline: 6 modules (pipeline, schema_loader, confidence, validator, bad_doc_handler, document_type_detector), EN+BM prompts, 3 schemas, tests, `output.json`.
- `1ba5dd9` Handoff package for Financial (`agents/financial/HANDOFF_FROM_LOGISTICS.md`). PR #1 merged.
- `8f2f2f1` **Re-extracted all 36 docs from the images** — the earlier `output.json` had invented invoice numbers, wrong vendors/totals and missed duplicate INV-2026-020. Docs cropped to `test-documents/<type>/pPP_NN.png` and used as `source_ref`. Unreadable/contradictory values now flagged in `notes` instead of guessed.

**Financial — 15:39–16:45** · Zu Yenn, Colt
- `cebd384` Ledger + exception schemas (15 exception types), 13-step prompt, `engine.py` (arithmetic, SST, duplicates, PO match, reconciliation, overdue, confidence, traceability), mock data.
- `b63cb24` First run on real Logistics output; line-item and tax checks, `no_due_date` exception.
- `8f2f2f1` (Colt) Purchase receipts booked as cash out, SST spread across lines, bilingual PO matching, duplicates excluded from totals, `test/test_engine.py`.
- `1ed6c51` Added `po` to document_type enums; schema validation 0 errors.
- `ad6a50b` Financial integration tests; pipeline outputs in `agents/logistics/`.

**Secretary — 17:07–17:25** · hyang00122022-spec (branch `TAO`), Colt
- `267542f` Secretary agent: planner, task_generator, email_drafter, reporter, models (pydantic), CLI, schemas, prompts, tests. Merged as `83f4cf9` (PR #3).
- `fdb1d58` Secretary WorkBuddy skill (`.workbuddy-ai/skills/secretary-agent/`) + integration tests.

**Integration / backend — 17:51–18:14** · Colt
- `5b737bd` `run_pipeline.py` — whole pipeline without WorkBuddy.
- `ea53dc0` `agents/orchestrator.py` (LLM calls with Python fallback) + `app.py` Flask API.

**3D office frontend — 18:45–18:53** · Xuanyu (uploads via GitHub web)
- `f4ddc2f` Blender office/characters, renders, build scripts.
- `e156431`, `0480a07` Godot project + Python bridge to the agents.
- `8ba0440` three.js web viewer.
- `fb20477` Sample bridge run output.

**Cleanup — 18:49–19:10** · Colt
- `201e8da`, `0dc28ef` Blender assets → `office-3d/`, Chinese file names translated.
- `51e27d7` Restored `requirements.txt` — the Godot upload had replaced it with only `pydantic==2.14.0`.
- `11b966f` Godot/web uploads → `frontend/godot-office/` and `frontend/web-office/`, folder layout rebuilt (the upload had flattened it); bridge now uses the repo's `agents/`.
- `28cc6b1` README run instructions and structure.
- _This commit:_ web frontend calls `/api/run`; `app.py` redirects `/` → `/web-office/`; this handoff.

**Branches:** `TAO`, `fronted`, `zyenn/financial-agent` are fully merged into `main`. `colt` = `main`.

---

## 5. Tests (run 2026-10-10, Python 3.14)

| Suite | Result |
|---|---|
| `agents/secretary/tests` | 108 passed |
| `agents/logistics/tests` | 13 passed, **1 failed** (`test_skill_file`: SKILL.md missing) |
| `agents/financial/tests` | 5 passed, **1 failed** (`test_skill_file`: SKILL.md missing) |
| `python agents/financial/test/test_engine.py` | OK — 63 ledger rows, 92 exceptions |
| `python frontend/godot-office/bridge/test_bridge.py` | 2 passed |

Test counts in some commit messages (60, 70, 223) are higher than what's collected now.

Running tests or the pipeline **rewrites** `agents/logistics/output.json`, `ledger.json`, `exceptions.json` — check `git status` before committing.

---

## 6. Known issues (most important first)

**Fixed 2026-10-10/11** (live on Vercel):
- The report's figures come from the Financial ledger (the LLM had reported RM 21,875.70 cash out vs RM 11,974.00 + RM 1,197.40 SST in the ledger).
- 2 chase emails (INV-2026-016 Puteri Kraf, INV-2026-033 Buku Nusa — vendor invoices with conflicting figures or totals that don't add up); one task per exception (57) from the Python task generator.
- AI Summary and Checklist built from each run; the Checklist groups by exception severity, same as the summary (8 critical). Results panel with links to the source document images.
- Cards update one agent at a time (`POST /api/run/stream`, NDJSON).
- Optional live extraction ("Read the 36 scans live with Gemini"): parallel, rate-limit retries, per-type field names, skips the 4 full-page scans, and checks itself against the hand-checked records on every field that drives an exception (dates, references, all amounts, the conflicting-figure flag) — latest run 337/339 fields, same 57 exceptions and 2 chase emails as the hand-checked run.
- WorkBuddy skills for Logistics and Financial now live in the repo (`.workbuddy-ai/skills/`); they had been created one folder above the repo and never committed. All test suites pass.
- `run_pipeline.py` goes through the same orchestrator as the site.

**Data note — SST 10%:** every generated test document prints "SST 10%". That's an artifact of the template used to generate the data set, not a problem with the agents, so `agents/financial/engine.py` accepts it (`TEMPLATE_SST_RATES`). This removed 35 identical warnings (92 → 57 exceptions). Tax amounts that don't match the printed rate are still flagged. Remove the set before running on real documents.

1. **Live extraction is close, not identical.** The extraction prompt now names the `conflicting_values` flag the engine uses (the hand-check script had invented it, so Gemini used `total_mismatch` and Financial missed 5 conflicts), says the same value printed twice is not a conflict, and asks for confidence below 0.7 on ambiguous fields. Latest live run: 57 exceptions and the same 2 chase emails as the hand-checked run; 337/339 fields. Remaining, both reported by the self-check: INV-2026-011's PO read as `PO-MT-0967` (scan prints `0987`), and INV-2026-033's SST recorded as 9.00 instead of the labelled 9.50. One run each — LLM output can vary between runs.
2. **Email/task approval endpoints are placeholders** — `/api/tasks/<id>/approve`, `/api/emails/<id>/approve|reject` return success without doing anything. Emails are drafts only.
3. **Financial `TODAY` is hard-coded** to 2026-10-10 in `engine.py`; `period` is a label only, records aren't filtered by month. Only MYR.
4. **Gmail is connected but unproven on a real inbox.** Orchestrator pulls attachments via TAO's `GmailCrawler` when `agents/secretary/credentials.json` + `token.json` exist (README → Gmail). Tested with simulated attachments only; PDFs unverified; local only (no Google login on Vercel).
5. **Free-tier limits.** Live extraction uses ~38 Gemini calls per click (free tier: 500/day per model); Vercel's function time limit for this project couldn't be read from the CLI (live runs take ~25–30 s).
6. **Mac-only launchers.** `*.command` files in `frontend/` use zsh and Xuanyu's local paths. Use the commands in §2 instead.
7. **Repo hygiene:** 9 `__pycache__/*.pyc` files are tracked under `agents/secretary/src/`; root `.gitignore` ignores `*.html` (existing `index.html` is tracked, new HTML files won't be); pytest can't collect all agents' `tests/` folders in one run (same package name); the test suites rewrite the tracked JSON in `agents/logistics/` and `agents/financial/test/`.

---

## 7. Next steps vs. timeline

| Gate | Status |
|---|---|
| 15:00 Sat — workspace + first 15 docs | Done (36 docs) |
| 18:00 Sat — 1 doc in → 1 ledger row out | Done |
| 23:00 Sat — all 40 docs run, validation working | Done for 36 docs; end-to-end via `/api/run` |
| 01:00 Sun — backup demo video | Open |
| 04:00 Sun — hard stop on features | Open |
| 06:00 Sun — slides, 3-min rehearsal | Open (`slides/` empty) |
| 08:00 Sun — submit | Open |

Suggested order before the 04:00 freeze: fix chase emails (#1) → add results panel to the web UI (#4) → commit the two missing SKILL.md files (#2) → record the backup video.

---

## 8. Pointers

- Architecture doc: [docs/architecture.md](docs/architecture.md) · Shared rules: [rules/rules.md](rules/rules.md)
- Logistics → Financial contract: [agents/financial/HANDOFF_FROM_LOGISTICS.md](agents/financial/HANDOFF_FROM_LOGISTICS.md)
- Agent docs: [agents/logistics/README.md](agents/logistics/README.md), [agents/secretary/README.md](agents/secretary/README.md)
- Godot bridge guide: [frontend/godot-office/godot-open-and-integration-guide.txt](frontend/godot-office/godot-open-and-integration-guide.txt)
- Web viewer guide: [frontend/web-office/web-open-and-usage-guide.txt](frontend/web-office/web-open-and-usage-guide.txt)

**Contributors:** Chew Zu Yenn (zuyenn) — repo, Financial · Colt Tan (coltonthatgood) — Logistics, integration, backend · hyang00122022-spec — Secretary · Xuanyu — 3D office, Godot, web viewer.

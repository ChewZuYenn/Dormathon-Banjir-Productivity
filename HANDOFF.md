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

**Demo path that works today:** `pip install -r requirements.txt` → `python app.py` → open http://127.0.0.1:5000 → type a goal → "开始运行".

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

Optional LLM (OpenAI-compatible) via env vars: `LLM_API_URL` (default `http://localhost:11434/v1`), `LLM_API_KEY`, `LLM_MODEL`, `LLM_VISION_MODEL`. Without one, every step falls back to Python (`sources` in the response says which ran).

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

1. **0 chase emails without an LLM.** Demo promises "two drafted chase emails". `/api/run` with Python fallback returned 92 tasks but 0 emails. Fix the Secretary fallback in `agents/orchestrator.py`, or run with an LLM.
2. **Financial/Logistics WorkBuddy skills missing.** `ad6a50b` says they were added but no `SKILL.md` was committed for either. Causes the two `test_skill_file` failures.
3. **Pipeline runs dirty the repo.** Generated JSON in `agents/logistics/` is tracked and rewritten every run (flag order also changes between runs). Consider `.gitignore`-ing it and keeping a fixed sample elsewhere.
4. **Web UI shows counts only.** No ledger/exception/task/email views yet; full result is in the browser console as `lastRun`. Empty placeholders exist in `frontend/components/`.
5. **No per-agent progress on web.** `/api/run` is synchronous, so all three cards are "working" together. Port the bridge's job + polling pattern to `app.py` if needed.
6. **~12 s per run** — partly probing for an LLM at `localhost:11434` that isn't there.
7. **Email/task approval endpoints are placeholders** — `/api/tasks/<id>/approve`, `/api/emails/<id>/approve|reject` return success without doing anything.
8. **Financial `TODAY` is hard-coded** to 2026-10-10 in `engine.py`; `period` is a label only, records aren't filtered by month. Only MYR.
9. **Mac-only launchers.** `*.command` files in `frontend/` use zsh and Xuanyu's local paths. Use the commands in §2 instead.
10. **Repo hygiene:** 9 `__pycache__/*.pyc` files are tracked under `agents/secretary/src/` despite `.gitignore`; root `.gitignore` ignores `*.html` (existing `index.html` is tracked, new HTML files won't be).

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
- Godot bridge guide (Chinese): [frontend/godot-office/godot-open-and-integration-guide.txt](frontend/godot-office/godot-open-and-integration-guide.txt)
- Web viewer guide (Chinese): [frontend/web-office/web-open-and-usage-guide.txt](frontend/web-office/web-open-and-usage-guide.txt)

**Contributors:** Chew Zu Yenn (zuyenn) — repo, Financial · Colt Tan (coltonthatgood) — Logistics, integration, backend · hyang00122022-spec — Secretary · Xuanyu — 3D office, Godot, web viewer.

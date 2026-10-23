# Health check without a model key — implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** With no in-app AI key, the health check returns an honest stored report (no score or grade while
bullets are unjudged) and a connected agent can judge the pending bullets by the app's own rubric.

**Architecture:** `run_report` decides the judge by `llm.any_model_key_configured()`. Keyless runs read
stored judgments only (`bullet_classify.stored_judgments`) and pass the pending locations into `assemble`,
which nulls score/grade while a scored bullet is pending. A new REST write (`/judgments`) validates agent
classifications with `bullet_classify._validate`, stores them under `agent:<client>`, and rebuilds the
report; MCP `judge_health_bullets` wraps it. Design: `docs/plans/2026-10-23-health-check-without-key-design.md`.

**Tech stack:** FastAPI + SQLAlchemy (backend), FastMCP wrappers (mcp_server), Next.js 16 + React 19
(frontend). Test venv: uv from `backend/requirements.lock` + `pip install -e ".[dev,mcp]"`.

**Test command (backend, from `backend/`):** `$V/bin/python -m pytest <paths> -q` while iterating; the full
gate is `$V/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile`.

---

### Task 1: `bullet_classify` — stored-only lookup, agent judgments, the evaluator prompt

**Files:** modify `backend/app/services/bullet_classify.py`; test `backend/tests/test_health_keyless.py` (new).

1. Failing tests (new file): 
   - `stored_judgments` returns a cached row from ANOTHER model at the current `RUBRIC_VERSION` and lists the
     rest as pending `{id, text, hints}`; never calls `llm.call_openai` (fake raises).
   - a row at an older rubric version is pending.
   - each stored result carries `judge` (the row's model).
   - `record_judgments` stores a valid entry with `model == "agent:claude-ai"`, `rubric_version ==
     RUBRIC_VERSION`; returns `accepted [{id, level}]`.
   - an invalid level, an id that is not pending (already judged, or unknown), and a duplicate id in one
     call are rejected with a reason; `direct` without a verbatim quote is stored as `adjacent`.
   - `agent_judge(None) == "agent"`, `agent_judge(" claude-ai ") == "agent:claude-ai"`.
   - `evaluator_prompt` fills `$items_json` with the pending items (the ids appear in the prompt).
2. Implement:
   - `_lookup(db, items, model)` = today's first pass of `classify_items` (out, pending, texts, disputes);
     `model=None` means any judge at the current rubric version (`_stored_result` takes `model: str | None`).
   - `_no_number_pass(out, texts, disputes)` = today's post-pass.
   - `classify_items` = `_lookup` with the smart model + `_classify_batch` + `_no_number_pass` (unchanged
     behaviour). `stored_judgments(db, items) -> (judged, pending)`.
   - results carry `"judge"`: row.model / dispute.model; override → `None`; `_classify_batch` → model.
   - `evaluator_prompt(db, pending)`; `evaluate_uncached` uses it.
   - `_store(db, chash, entry, model)` extracted from `_classify_batch`.
   - `agent_judge(client)`, `record_judgments(db, judge, items, entries)`.
3. Run `tests/test_health_keyless.py tests/test_bullet_classify.py tests/test_health_disputes.py`; commit.

### Task 2: `resume_lint` — keyless run, ungraded report, `judged` block, judging brief

**Files:** modify `backend/app/services/resume_lint.py`; tests in `backend/tests/test_health_keyless.py`;
add a keyed fixture to `backend/tests/test_resume_lint.py` and the run_report test in
`backend/tests/test_resume_lint_router.py`.

1. Failing tests:
   - keyless `run_report` (no key, `llm.call_openai` raises): gates present, `score`/`grade`/`next_grade`
     None, `judged == {"done": 0|1, "pending": n, "by": []}`, `features.raw_score` None, no C1 gate.
   - with every scored bullet stored (one at an older model), keyless run → integer score + letter grade,
     `judged.by` names the judge.
   - `insufficient_evidence` counts pending scored bullets (4 pending bullets → False).
   - `assemble(..., pending=...)` gain divides by judged + pending scored bullets.
   - `use_llm=False` reads stored judgments.
   - `judging_brief(db, resume)` → None when nothing pending; else `{rubric_version, pending_ids, prompt}`.
   - `record_judgments(db, resume, judge, entries)` wraps the classifier with this resume's items.
2. Implement:
   - `run_report(..., use_llm: bool | None = None)`: None → `llm.any_model_key_configured()`. Keyless:
     `judged, pending = bullet_classify.stored_judgments(...)`; pending locations go to `assemble`;
     `model` column = the single judge or None.
   - `assemble(..., pending: Iterable[Location] = ())`: `n_scoreable` = judged + pending scored;
     score/grade/next_grade/raw_score None while a scored location is pending; `_final_gates` skips C1
     while a hot location is pending; `insufficient_evidence` and `gain` use `n_scoreable`;
     `report["judged"] = {"done", "pending", "by"}`.
   - `judging_brief`, `record_judgments`.
   - keyed fixture: `monkeypatch.setattr(rl.llm, "any_model_key_configured", lambda: True)` (autouse in
     `test_resume_lint.py`; the dispute test in the router file).
3. Run the health test files; commit.

### Task 3: REST — nullable read model, `judging`, the judgments write, tailoring guard

**Files:** modify `backend/app/routers/resume_lint.py`, `backend/app/services/tailoring_session.py`;
tests in `backend/tests/test_health_keyless.py`, `backend/tests/sync/test_guard.py` (WRITE_PATHS).

1. Failing tests:
   - `POST /run` with no key → 200, `grade` null, `judging.pending_ids` non-empty, `judging.prompt`
     contains each pending id.
   - `POST /judgments` (header `X-Maestro-CS-Origin: mcp`, detail `claude-ai`) with all pending ids →
     `accepted` lists them, grade is a letter, stored rows' model `agent:claude-ai`, `judging` null.
   - partial judgments → `judging.pending_ids` lists the rest, grade null.
   - `POST /judgments` with a key set → 409; nothing stored.
   - `GET` latest returns `judged`.
   - tailoring session on a base whose latest report has `score: None` → no crash, no low-score warning.
   - sync guard: `("POST", "/api/resume-lint/application/{app}/judgments", {"classifications": []})`.
2. Implement: `LintReportRead.score: int | None`, `grade: str | None`, `judged: dict | None`,
   `judging: dict | None`; `JudgmentsBody` (`classifications: list[dict]`, max 500); `JudgmentsRead`
   (+ `accepted`, `rejected`); `_read(row, *, stale, judging)`. Tailoring: `score is not None and score < 55`.
3. Run; commit.

### Task 4: MCP — `judge_health_bullets`, docstrings, profiles

**Files:** `backend/mcp_server/client.py`, `server.py`, `profiles.py`, `README.md`; tests
`backend/mcp_server/tests/test_client_health.py`, `test_server.py`.

1. Failing tests: client posts `{"classifications": [...]}` with origin headers; the tool passes the client
   label; the tool is in every profile that has `run_health_check`; annotations (write, not destructive);
   docstring ratchet: run_health_check names `judged`, `judging`, null score/grade without a key;
   judge_health_bullets names `_validate`'s rules, `accepted`/`rejected`, the 409 with a key.
2. Implement; update any registered-tool count pins the suite reports.
3. Run `mcp_server/tests`; commit.

### Task 5: Web views

**Files:** `frontend/lib/types.ts`, `frontend/lib/health-report.ts` (+ `.test.ts`),
`frontend/components/resume-health/summary-band.tsx`, `health-badges.tsx`, `use-health-runs.ts`, any
caller tsc flags; backend pin `backend/tests/test_frontend_health_report.py` if it pins copy.

1. `LintReport.score: number | null`, `grade: string | null`, `judged?: {done, pending, by}`.
2. Pure helpers in `health-report.ts`: `reportGraded(report)`, `notJudgedLine(report)`
   ("3 bullets aren't judged yet. A model key in Settings, or a connected agent, can judge them."),
   `judgedByLine(report, nameOf)` ("Bullets judged by Claude, a connected agent."), `checkDoneWords`
   ("Check done. Bullets not judged yet."). Node tests.
3. Summary band: "Not graded" tile when ungraded; the not-judged line; the judged-by line. Badges: "Not
   graded" chip and summary. `use-health-runs`: no delta when either side is ungraded.
4. `npx tsc --noEmit`, `npm run lint`, `node --test` for the lib file; commit.

### Task 6: Docs, gate, full suite

1. `docs/health-check-rubric.md` (User control and verification: keyless reports, agent judgments),
   `docs/entities/others.md` (ResumeLintReport fields), `docs/agent-surfaces.md` (MCP server + tool
   count), SYSTEM.md (tool count in §3/§7), CHANGELOG Unreleased.
2. `python3 scripts/check_system_md.py`; full backend suite with xdist; frontend gates; commit.

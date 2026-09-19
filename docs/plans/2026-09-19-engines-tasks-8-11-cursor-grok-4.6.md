# Handoff: engines branch, Tasks 8–11 — Cursor CLI / Grok 4.6

Executor: Cursor CLI (`agent`) running **Grok 4.6**. Planner: Claude Fable 5.1
(the main session). Base branch: `claude/desktop-step2-engines-mcp` (local
only; nothing on this machine is pushed). Plan: `docs/plans/2026-09-19-desktop-step2-engines.md`
(Tasks 8, 9, 10, 11 — read them in full; this doc carries only what changed
since they were written). Design: `docs/plans/2026-09-19-desktop-step2-design.md`.

## Goal Card

**Goal:** A fresh install with no TeX, no host Python and no Docker on the
client side renders its first PDF and connects any MCP-capable assistant in
under a minute, while a compose install sees no behaviour change it did not
ask for. This branch is the engines half: a backend with no TeX renders
every resume and cover letter through Typst and says so in the response,
the gallery and `setup/status`; a backend with TeX behaves exactly as before.

**Principles:**
- Both engines stay first-class and LaTeX stays the default wherever TeX
  exists (SYSTEM.md §13 `typst-default-flip` is HELD by the owner).
- Explain, never substitute silently: every fallback names itself in the
  response, the UI and `setup/status`.
- Docker stays the contributor path; nothing here needs a host toolchain.
- Do not fix unrelated things while in there.

**Non-goals:** the desktop shell; the `mcp` SDK upgrade; flipping the default
engine; MCP over HTTP (branch 2, not started); anything under `SYSTEM.md`,
`.system_md_enforcement.json`, `.slopledger.json` (the planner's Task 12).

**Autonomy: peer** (adapt-and-advise). You may adapt *how* when the repo
disagrees with the plan; log every deviation with a one-line reason in the
table at the end of this file; flag anything in the plan that contradicts
the Goal Card. Scope is never self-expanded: an interface another task
depends on (a schema field, a route, a docstring contract) changes only by
a deviation note back to the planner, not by editing it.

## Ground truth

Read `SYSTEM.md` first (repo root): §6 (invariants), §7 (MCP: "the
docstring is the API", the ~2048-char truncation budget ratchet
`test_registered_tool_docstrings_fit_client_truncation_budget`), §8
(frontend conventions), §9 (dev environment). Then the plan's Tasks 8–11.
Do NOT edit SYSTEM.md; note anything it should say in your deviation table.

## What is already true on the base branch (Tasks 1–7, do not redo)

- `app/services/engines.py`: `probe() -> EnginesStatus(pdflatex, typst)`,
  each an `EngineStatus(name, available, version, path, reason)` frozen
  dataclass; `probe_pdflatex()`, `pdflatex_available()`.
- `pdf_render.resolve_render_template` substitutes the first ready Typst
  template for a LaTeX one when TeX is absent, with a `render_note`
  ("TeX is not installed on this machine; rendered with X instead of Y.").
- `render_note: str | None` is on the wire for `POST /api/applications/{id}/render`
  (`RenderResult`), every base-resume response that follows a render
  (`BaseResumeDetail`: POST render, PUT, PATCH edits, create, duplicate,
  import, from-KB) and `POST /api/qa/{id}/render` (`QAEntryRead`). It is
  null whenever nothing was substituted.
- `template_fallback` means ONLY "an explicit `?template_id=` was passed and
  the resolved id differs". A substitution of the PERSISTED choice never
  sets it; `render_note` is the only signal there. (The plan's Task 9
  docstring text predates this correction — see Task 9 below.)
- `TemplateSummary`/`TemplateDetail.engine_available: bool` (false for a
  LaTeX template on a backend with no pdflatex).
- Seeds on a TeX-less host stay `draft` with `last_error == "requires TeX (pdflatex not found)"`
  (constant `template_validation.REQUIRES_TEX`); they re-validate at the
  next boot after TeX appears.
- Health structure gates follow the template that actually renders.

## Your tasks, in order, one commit each

### Task 8 — `engines` in `setup/status` (plan Task 8, as written)

Contract other work depends on (Task 10 reads it):

```python
class EngineProbe(BaseModel):   # from_attributes; built from engines.EngineStatus
    name: str; available: bool; version: str | None = None
    path: str | None = None; reason: str | None = None
class EnginesProbe(BaseModel):  # from_attributes
    pdflatex: EngineProbe; typst: EngineProbe
SetupStatus.engines: EnginesProbe        # informational, NEVER part of `complete`
SetupStatus.template.detail["default_engine_available"]: bool
```

Build with `probed = engines.probe()` once per status read and
`EnginesProbe.model_validate(probed)`. Test as in the plan (patch
`engines.probe_pdflatex` to return an unavailable `EngineStatus`). Run
`mcp_server/tests/test_workflow.py` too: the MCP workflow reads
`setup_status` dicts by key, so an added key must be harmless.

### Task 9 — MCP docstrings (plan Task 9, with one correction)

Add ONE sentence per tool (`render_pdf`, `list_templates`, `get_template`,
`create_template_draft`) as the plan says, and ALSO fix `render_pdf`'s
existing sentence about `template_fallback`: it currently says the flag
means "the requested id was unusable and the default was silently
substituted"; make it say the corrected contract above (explicit
`template_id` only; a substituted persisted choice is reported by
`render_note`, never by the flag). Keep every tool under the truncation
budget test. The tools pass REST JSON through verbatim, so no client code
changes. Test: `mcp_server/tests/test_server.py` as in the plan (assert the
words appear in `__doc__`), plus run the whole `mcp_server/tests/` suite.

### Task 10 — frontend (plan Task 10, PLUS the render-note surfacing)

Everything in the plan's Task 10 (types, `requires TeX` badges on the
gallery card and the template detail page, the `engines` checklist row in
`setup-steps.ts` with `ACTION_LABELS.engines`), and additionally
(deviation rows 16 and 31 of the plan):

- Type `render_note?: string | null` on `BaseResumeDetail`, on a new
  `RenderResult` interface for the application render response, and on
  `QAEntry` in `frontend/lib/types.ts` (match the backend field names
  exactly; the application response also carries `tex_path`, `pdf_path`,
  `resolved_template_id`, `resolved_engine`, `template_fallback`).
- At the three render call sites that today discard the response body —
  `frontend/components/application-panel.tsx` (~line 267, application
  render), `frontend/components/resume-editor/tailored-resume-studio.tsx`
  (~line 143), and `frontend/components/qa-tab.tsx` (~line 137, cover
  letter) — read the response and, when `render_note` is non-null, show it
  once with `toast.info(render_note)` (the repo uses `sonner`; see
  `components/settings/about-section.tsx` for the import). Do not add
  state, hooks or persistence; do not gate anything on `template_fallback`.
- The pill strip (`setup-status-strip.tsx`) lists only unfinished steps, so
  the engines row (done when Typst is available) appears only in the
  expanded getting-started card; that is intended.

Gates (from `frontend/`): `npx tsc --noEmit && npm run lint && npm run build`.
You cannot run the maintainer slop ratchet and your sandbox may not reach a
dev server; do NOT leave dev-server processes running. Say plainly what you
could not verify visually; the planner does the browser pass at merge.

### Task 11 — user docs (plan Task 11, PLUS two items)

Everything in the plan's Task 11 (README engines paragraph and the
troubleshooting entry; KNOWN_ISSUES rendering + "Two render engines"
bullets; CHANGELOG `[Unreleased]` `### Added` / `### Fixed`; `.env.example`
commented `MAESTRO_CS_PDFLATEX`). Additionally (plan rows 25 and 27):

- `docs/entities/others.md` ~lines 113–114 credits migration `c84a19d2e7f0`
  for resyncing seed sources; the live mechanism is now seed-time
  (`template_registry.SUPERSEDED_SEED_DIGESTS`, every boot, after any
  legacy import). Correct that sentence; keep the historical mention if the
  paragraph is about the legacy chain.
- Add `backend/tests/fixtures/templates_superseded/README.md` in the shape
  of the sibling `templates_pre_section_order/README.md`: what the frozen
  files are, how to add a version (freeze old bytes as `<n>.tex.j2`, add
  its digest to `SUPERSEDED_SEED_DIGESTS`, update `CURRENT_SEED_DIGESTS`),
  and that a wrong digest is a silent no-op.
- CHANGELOG `### Fixed` also gets: the header partial compiles for a
  contact without a location (both resume and cover letter); the user
  templates' `\href` targets (`carlito_dense`, `harshibar`) survive `~`/`_`
  and are resynced on existing installs.

Read each hunk once against the code before committing: every sentence in
user docs must be true of the branch as it is, not as the plan imagined it.

## Scope boundaries

Allowed: `backend/app/schemas/setup_status.py`, `backend/app/services/setup_status.py`,
`backend/tests/test_setup_status.py`; `backend/mcp_server/server.py`,
`backend/mcp_server/tests/test_server.py`; `frontend/**` (types, the five
named components, `setup-steps.ts`, `getting-started-card.tsx`);
`README.md`, `KNOWN_ISSUES.md`, `CHANGELOG.md`, `.env.example`,
`docs/entities/others.md`, `backend/tests/fixtures/templates_superseded/README.md`;
this handoff file (your deviation table).

Do NOT touch: `SYSTEM.md`, `.system_md_enforcement.json`, `.slopledger.json`,
`docs/plans/2026-09-19-desktop-step2-*.md` (the planner's), anything under
`backend/app/services/` other than `setup_status.py`, `backend/app/routers/`,
`backend/app/templates/`, `backend/migrations/`, `backend/legacy_postgres/`,
`backend/tests/` other than the two files named, `extension/`, `mcpb/`,
`plugins/`, `docker-compose.yml`, `backend/Dockerfile`, `scripts/`.

## Working rules on this machine

- Create your own worktree from the base branch and work only there:
  `git worktree add .claude/worktrees/grok-engines-8-11 -b cursor/engines-tasks-8-11 claude/desktop-step2-engines-mcp`.
  Never `cd` into the main checkout (`/Users/ajeyds/Projects/maestro-career-studio`):
  its compose stack is live on 3000/8001/55432 and its `data/` is the
  owner's real database. Never run `./scripts/update.sh`. Never `git stash`
  (the stash stack is shared). Never push. Never merge. Leave the main
  checkout on whatever branch it was on.
- Backend tests: `cd <worktree>/backend && /opt/anaconda3/bin/python3 -m pytest tests/ mcp_server/tests/ -q`
  (no database service; conftest makes a throwaway SQLite file). Last known
  state on the base branch: 4362 passed, 2 skipped. `ruff check .` from
  `backend/`. The anaconda interpreter's editable install points at the MAIN
  checkout, so an ad-hoc script run by path imports the wrong `app`; use
  `python3 -m …` from the worktree's `backend/` or `PYTHONPATH=.` there.
- TeX is at `/Library/TeX/texbin` (not needed for these four tasks).
- Commit per task; subjects like the plan's (`feat(setup): …`, `docs(mcp): …`,
  `feat(ui): …`, `docs: …`). No attribution trailer is required from you.
- If a later base-branch commit lands while you work (the planner may fix
  Task 7 review findings), rebase your branch onto the base before handing
  back and re-run the suite.

## Escalate (stop and write a deviation note) when

- a contract above (schema field names, route shapes, docstring semantics)
  would have to change;
- a plan step contradicts the Goal Card or SYSTEM.md;
- a test outside your allowed files fails because of your change.

## Hand back

Reply (in the Cursor session) with: the four commit SHAs; exact test counts
(backend suite, `mcp_server/tests`, tsc/lint/build results); the deviation
table below filled in; what you could not verify and why; anything in the
plan you think is wrong, with the Goal Card line that motivates the
objection.

## Deviation log (executor, append-only)

| # | Task | What the plan said | What was done instead | Why |
|---|---|---|---|---|
| 1 | 8 | Test assumed the throwaway DB already has seeded LaTeX Classic, so `default_engine_available` is False when pdflatex is patched away | Test inserts a `classic` latex seed default before the GET | Tests do not run `ensure_seed_templates`; without a latex default the predicate is True (`default_tpl is None`) and the assertion cannot hold |
| 2 | 9 | `assert "TeX" in srv.create_template_draft.__doc__` | Asserted `"no TeX"` and `"engine_available"` | `"TeX"` already matches `"LaTeX"` in the existing docstring; the plan's assertion would have passed with no new sentence |
| 3 | 9 | Fix `render_pdf`'s `template_fallback` sentence; the listed test only checks the four new words | Also asserted `"silently substituted" not in` `render_pdf.__doc__` | The old sentence is the contract the handoff told us to retire; a word-presence test would not catch leaving it |
| 4 | 10 | Pill strip lists only unfinished steps, so the engines row appears only in the expanded getting-started card | Left `setup-status-strip.tsx` unchanged; it maps every step | Strip is not in the allowed file list; live code does not filter on `done`. Engines will show there as a done pill whenever Typst is available |
| 5 | wt | `git worktree add … -b cursor/engines-tasks-8-11 claude/desktop-step2-engines-mcp` in one shot | First add created the branch then failed writing `.git/worktrees/…/commondir` (sandbox); attached the existing branch at the same SHA | Same branch, same tip as the base; not a content change |
| 6 | 12 note | — | Do not edit SYSTEM.md. It should gain: `engines` on `GET /api/setup/status` (informational, never `complete`); MCP docstring facts (`render_note`, `engine_available`, corrected `template_fallback`); frontend `requires TeX` badge + setup-checklist engines row | Planner's Task 12; Goal Card non-goal |
| 7 | 11 | Correct only `others.md` ~113–114 | Also replaced the later “hash-guarded migration is what reaches installed rows” clause with seed-time `SUPERSEDED_SEED_DIGESTS` | Same paragraph, now false of the branch; Task 11 says every sentence must be true of the code |

# Closing the MCP coverage holes: implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development in this session) to implement this plan task-by-task.

**Goal:** An MCP-only user can correct a saved job, keep a chosen design, upload a cover letter, manage referrals, read per-country permits / last runs / roles, and trust profile saves; 92 → 94 tools.

**Design:** `docs/plans/2026-10-26-mcp-coverage-design.md` (owner-approved 2026-10-26). Read it first.

**Architecture:** Mostly MCP plumbing over existing REST routes, plus three backend changes: the job ingest's update path, server-side merge routes for the three profile settings, and the brief's new fields. Parameters on existing tools wherever the job is the same; two new tools (`save_referral`, `kb_merge_entities`).

**Tech stack:** FastAPI, SQLAlchemy, pydantic v2, FastMCP, httpx + respx, pytest with xdist.

**Constraints:**
- Never start Docker; never bind ports 8001 or 3000. Neutral sample data (public repo; any field, any country).
- `PY=/private/tmp/claude-501/-Users-ajeyds-Projects-maestro-career-studio--claude-worktrees-api-independence-no-gui-85e978/cfe7e029-00a1-45a8-8e93-1de9ac840714/scratchpad/venv/bin/python`; from `backend/`: `env -u ANTHROPIC_BASE_URL $PY -m pytest -q -p no:cacheprovider <paths>`; full suite with `-n auto --dist loadfile`.
- TDD, including tests that the not-requested path is unchanged. Commit per task with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Branch `claude/mcp-phase3c-coverage`; no push or merge.
- MCP descriptions within the 2000-char budget (overflow into parameter descriptions); every description names only tools present in every set serving the tool (the set-scope test in `mcp_server/tests/test_server.py`); the MCP client sends the `mcp` origin on every request (Phase 3a), so agent writes keep their provenance and the who-writes rule.
- Phase 3b's removed-name map (`mcp_server/replaced.py`) and scans stay green.

---

### Task 1: correct a saved job, and its application link

**Files:** `backend/app/routers/jobs.py` (ingest: `_persist_job` returns the existing row with `already_existed=True` and never applies the new extraction — add an update path), the ingest schema (`JobIngest` has `apply_url`), `backend/mcp_server/client.py` (`store_extracted_jd` sends `update` and `apply_url`), `server.py` (`store_extracted_jd(..., apply_url=None, update=False)` + description: without update a repeat capture returns the saved job unchanged; with update it re-applies the extraction). Tests: the ingest router tests (find them, e.g. `tests/test_jobs_ingest*.py`), `mcp_server/tests/`.
- With `update=true` on an existing posting: re-run the same extraction→columns mapping and skill rows a new capture uses (the re-extract route at `jobs.py` ~718 shares that mapping — reuse it, don't fork it), keep the job's id, status, applications, proposals and provenance; return which fields changed; mark that job's saved ATS scores stale (find how scores record staleness, e.g. a hash or version on the score rows; if none exists, delete the job's scores so `score_ats` recomputes, and say which you chose); name any tailored application / open tailoring session for the job in the response (don't touch them).
- Without `update`: unchanged (pin it).
- `apply_url`: stored on capture and on update; `find_job_by_url` with the apply URL finds the job (check how it looks up; extend the lookup only if needed).
Commit `feat(jobs): an agent can correct a saved job and record its application link`.

### Task 2: keep a chosen design

**Files:** `server.py` `render_pdf(target_type, target_id, template_id=None, formatting=None, keep=False)`; client; backend: base resumes save `template_id`/`formatting` via `PUT /api/base-resumes/{slug}` (`base_resumes.py` ~340; check whether a lighter route exists); applications: find where an application's template/formatting is stored (`application_render.py` ~64 uses the id only for that render) and the route that saves it (add a small one if none). `get_template` documents the `fmt.*` knobs: validate `formatting` the way the web's editor does (find its schema).
- `keep=true` saves then renders; a later `edit_base_resume`/`edit_application` re-renders in the saved design (pin it).
- Without `keep`: a one-off render, saved design unchanged (pin it).
Commit `feat(mcp): render_pdf can keep the chosen design`.

### Task 3: archived bases

`list_base_resumes(include_archived=False)` → REST `include_archived` (`base_resumes.py` ~251). Tests. Commit `feat(mcp): list archived base resumes on request`.

### Task 4: cover letter upload

`prepare_application_pdf_upload(application_id, document="resume")`. Find where `store_cover_letter`'s PDF lives (it returns `pdf_path`) and stage it exactly like the resume (same upload dir rule `$MAESTRO_CS_UPLOAD_DIR/<application_id>/`, same integrity fields, a distinct canonical filename). Refuse plainly when no letter is stored. Update the apply technique (`backend/app/automations/skills/agent-apply-execution/SKILL.md`, the "Tailored PDF" section, and the "uploading from artifact_dir/applications/ is forbidden" rule) so a required cover letter uses this. Tests. Commit `feat(mcp): stage the cover letter for upload`.

### Task 5: clear an application's notes or referral

`update_application(..., clear: list[Literal["notes", "referral_id"]] = [])`: sends explicit nulls (check the REST PATCH accepts null to clear; extend it minimally if not); a field in both the update and `clear` is refused. Drop the "clearing a field requires the web UI" sentence from the description. Tests. Commit `feat(mcp): clear an application's notes or referral`.

### Task 6: `save_referral`

New tool `save_referral(company, careers_url=None, contact_name=None, notes=None, referral_id=None)` → `POST /api/referrals` (create) or `PUT /api/referrals/{id}` (update; check the PUT's semantics: whole replace vs partial, and make the tool's update not erase fields the caller didn't pass — read-merge-write is acceptable here only if the route is whole-replace and nothing else writes referrals concurrently; otherwise add a PATCH). Write annotation, non-destructive. Add to `HUNT_TOOLS`, `APPLY_TOOLS`, `TRACK_TOOLS`. Tests (create, update keeps untouched fields, unknown id 404). Commit `feat(mcp): save_referral adds or edits a referral`.

### Task 7: the brief carries per-country permits, last runs and the role list

**Files:** `backend/app/services/job_search_brief.py`, its schema (`app/schemas/job_search_brief.py`), tests.
- `work_auth_by_country`: for each apply-in market, the typed answers (`autofill_profile` per-country reader) as the yes/no shape the brief already uses, keyed by country code, with warnings per country as `_work_auth_warnings` does. Keep `work_auth` (home market) for one release and add the country it is for.
- `last_runs`: `{automation: finished_at}` from the agent-runs latest query (reuse the service behind `GET /api/agent-runs/latest`).
- `roles`: `[{key, label}]` from `role_categories.labels()`.
- The job-hunt playbook (`backend/app/automations/skills/job-hunt/SKILL.md`) uses `work_auth_by_country` and `last_runs` (it currently says to use `work_auth` verbatim and "the time since this automation last ran"); mail-status likewise for last run. Keep the playbook scans green.
Commit `feat(brief): per-country permits, last runs and the role list`.

### Task 8: unknown roles name the closest

`set_job_preferences` and `create_base_resume_from_kb` 422s for an unknown role category name the closest roles (use `role_categories.match_free_text` / the catalog's matcher; up to three). Backend validation messages or the MCP tool — wherever the 422 is produced, so the web benefits too if it shares it. Tests. Commit `feat(roles): an unknown role names the closest ones`.

### Task 9: conflict-safe profile writes

**Files:** `backend/app/routers/settings.py` (new `PATCH /api/settings/autofill`, `PATCH /api/settings/job-preferences`, and one route for markets + money, e.g. `PATCH /api/settings/market` carrying both), services as needed, `mcp_server/client.py` (`set_autofill_profile`, `set_job_preferences`, `set_markets` use them; `_merged_autofill` and friends move to the server as the one merge definition), tests.
- Merge semantics are exactly today's client-side ones (lists that replace whole stay whole-replace; nested dicts merge as now); EEO refusal and validation unchanged.
- One transaction per call; a concurrent writer between read and write is never lost: pin it by simulating a Companion learn landing between the old client's GET and PUT (test the server route merges against the current stored value at write time).
- The web's PUTs unchanged.
Commit `feat(settings): agent profile writes merge on the server`.

### Task 10: `kb_merge_entities`

New tool `kb_merge_entities(keep_id, merge_id)` → `POST /api/kb/entities/{keep_id}/merge` (check the route's body shape and which id is kept). Destructive annotation; `PROFILE_TOOLS`. Description: what moves (points, wordings, documents?) and what is lost, per the route's behaviour. Tests. Commit `feat(mcp): merge two career-history items`.

### Task 11: references, sets and counts

`tests/test_mcp_http_loopback.py` (94), `mcp_server/tests/test_profiles.py` sizes (profile 39, hunt 23, apply 35, track 14), the playbook/denylist/set-scope scans, frontend greps for tool lists. Full backend suite. Commit `chore(mcp): sets and counts for the new tools`.

### Task 12: docs

SYSTEM.md §3/§7 counts within budget (and an invariant line if agent profile writes now must use the merge routes); `docs/agent-surfaces.md`; `docs/entities/others.md` (MCP tool coverage), the job/referral/settings entity docs; `backend/mcp_server/README.md`; plugin README, example configs, manifest, README/USING_MAESTRO/GETTING_STARTED/KNOWN_ISSUES counts; CHANGELOG Unreleased (Added; Fixed: an agent's profile save no longer erases a Companion answer saved at the same moment). Commit `docs: the MCP coverage holes closed`.

### Task 13: verification

Full backend suite, frontend gates if `frontend/` changed, SYSTEM.md gate, slop ratchets (re-baseline only with a stated reason). Live on a scratch backend: correct a job (country change → stale scores, rescore), keep a design then edit and see it kept, list archived, stage a cover letter, clear notes, save and edit a referral, read the brief's new fields, an unknown role's suggestions, a profile write racing a Companion-style write, merge two KB items. Whole-branch review; fix; rerun. Report; merge only on the owner's word.

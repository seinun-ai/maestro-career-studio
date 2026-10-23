# MCP writes for form answers and preferences: implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** An MCP-only agent (no web UI, no AI key in Maestro) fills the autofill profile, where the user lives and
applies, the jobs they want and their persona, so setup readiness rises. Every human-only setting stays unwritable
over MCP. Design and boundary: [`2026-10-23-mcp-profile-writes-design.md`](2026-10-23-mcp-profile-writes-design.md).

**Architecture:** Four thin tools in `mcp_server/server.py` over five existing REST endpoints. The client
(`mcp_server/client.py`) reads each setting, merges in what the tool was given, and PUTs the result, because every
PUT replaces its whole setting. The input shapes are TypedDicts that refuse unknown keys, so they live in the
machine-readable schema. Market keys are a `Literal` built from `app.services.markets.keys()`.

**Tech stack:** FastMCP, pydantic TypedDict validation, httpx, respx (client tests), pytest with xdist.

**Ground rules:** run from `backend/` with the scratch venv's Python. Never bind ports 8001 or 3000, and never start
Docker. Do test-first, one commit per task.

---

### Task 1: The client's merge and write methods

**Files:**
- Modify: `backend/mcp_server/client.py`, which gets:
  - module helpers `_merged_answers`, `_merged_autofill` and `AUTOFILL_SECTIONS`;
  - methods `set_autofill_profile`, `set_job_preferences`, `set_markets`, `set_persona` in a new
    "profile facts" block next to "settings & setup".
- Test: `backend/mcp_server/tests/test_client_profile_writes.py` (new, respx).

Tests (each fails first):
1. **Personal merges by key.** Stored `{personal: {first_name: A, city: X}, preferences: {notice_period: 2w}, eeo:
   {gender: female}, custom: [..]}`. A write of `{personal: {city: Y, phone: 1}}` PUTs a profile whose `personal` is
   `{first_name: A, city: Y, phone: 1}`, while `preferences`, `custom` and `eeo` stay exactly as stored.
2. **Null removes a key.** `{personal: {city: None}}` removes `city`.
3. **Work permits merge by market and by key.** Stored `work_auth_by_country: {US: {status: citizen, authorized_now:
   true}}`; a write of `{UK: {authorized_now: true}, US: {sponsorship_future: false}}` merges US key by key and adds
   UK. The PUT body carries no `work_auth` and no `work_auth_market` (the read view's projection).
4. **A null market removes it.** `{UK: None}` sends UK as null, which removes it on the server.
5. **Lists replace.** education, languages and custom are replaced whole when given.
6. **Two gates on EEO.** Any section outside `AUTOFILL_SECTIONS` (`eeo`, `stale_answers`) raises `BackendError` and
   PUTs nothing.
7. **The response never carries `eeo`.** The response is the PUT's `value` without `eeo`, even when the server
   echoes it.
8. **`set_job_preferences` changes only the fields passed.** Stored `{locations: [A], remote: hybrid, notes: n}`;
   `remote="remote"` PUTs `{locations: [A], remote: remote, notes: n, …}`. `role_categories` is never sent (it is
   derived).
9. **`set_markets` writes each endpoint only for its own fields.** `home="UK"` alone GETs the market and PUTs
   `{home: UK, apply_in: <stored>}`, and touches no money endpoint. `home_currency="EUR"` alone GETs and PUTs money
   with every other money field kept. `""` sends null.
10. **`set_persona`.** It PUTs `{value: text}`.

Then run `pytest mcp_server/tests/test_client_profile_writes.py -q` and commit:
`feat(mcp): client writes for form answers, preferences, markets and persona`.

### Task 2: The four tools, their shapes and annotations

**Files:**
- Modify: `backend/mcp_server/server.py`. Add the TypedDicts `PersonalAnswers`, `EligibilityAnswers`,
  `PreferenceAnswers`, `WorkPermitAnswers`, `EducationEntry`, `LanguageEntry`, `SavedAnswer`, `FavoredRoleInput` and
  `MinSalaryInput`, each `with_config(extra="forbid")`. Add `MarketKey = Literal[*markets.keys()]`. The tools go in a
  new `# ---------- profile facts ----------` block after `get_autofill_profile`:
  - `set_autofill_profile`: `_write("Update Autofill Profile", destructive=True, idempotent=True)`; it returns
    `{profile, setup}`.
  - `set_job_preferences`: `_write("Update Job Preferences", destructive=True, idempotent=True)`.
  - `set_markets`: `_write("Set Where You Live and Apply", destructive=False, idempotent=True)`; it returns
    `{home, apply_in, home_currency, setup}`.
  - `set_persona`: `_write("Update Persona", destructive=True, idempotent=True)`.
  - `setup` is setup status's `autofill` block, read through `_best_effort_hint` (null when that read fails).
- Test: `backend/mcp_server/tests/test_profile_write_tools.py` (new).

Tests:
1. **Registration.** The four are registered, with titles and write annotations; existing ratchets cover the
   docstring budget and the describe-not-instruct rule.
2. **Schema.** `set_autofill_profile`'s input schema has no `eeo` property. Its market keys are `markets.keys()`, and
   calling it with `GB` fails validation.
3. **Unknown keys.** A personal key outside the shape (`favourite_colour`) fails validation.
4. **Forwarding.** Each tool forwards to its client method; `setup` is null when the status read raises.
5. **The settings-write allowlist.** A source scan of `client.py` finds every settings path written by
   `PUT|POST|PATCH|DELETE`, and the set equals `{autofill, job-preferences, market, money, persona}`. This pins the
   human-only boundary.

Then add the four names to `test_all_tools_registered`, run `pytest mcp_server/tests/test_server.py
mcp_server/tests/test_profile_write_tools.py -q`, and commit: `feat(mcp): four tools write the facts Setup and Profile
ask for`.

### Task 3: Profiles and the onboarding hint

**Files:**
- Modify: `backend/mcp_server/profiles.py`. `APPLY_TOOLS` adds `set_autofill_profile`; `CAREER_TOOLS` adds all four.
- Modify: `backend/mcp_server/workflow.py`. `next_after_base_from_kb(..., setup_status=None)` names
  `set_autofill_profile` in its prose steps only when it is registered and `setup_status["autofill"]["done"]` is false.
- Modify: `backend/mcp_server/server.py`. `create_base_resume_from_kb` reads setup status (best effort) only when
  hints are on and the tool is registered.
- Test: `test_profiles.py` (apply and career carry them, hunt carries none) and `test_workflow.py`:
  - the hint names it when the profile is not done;
  - it is silent when done, when the status is unknown, or when the tool is not registered;
  - `_every_hint` gains the setup-status branch, so the prose-invariant test covers it.

Commit: `feat(mcp): apply and career carry the profile writes; onboarding hint offers form answers`.

### Task 4: Docs and gates

- `SYSTEM.md` §3 and §7: the tool count, 91 → 95.
- `docs/agent-surfaces.md`, MCP server: the count, plus a bullet on the four writes and the human-only boundary.
  Rewrite the "No tool reads … money or the market setting" sentence.
- `docs/entities/others.md`, "MCP tool coverage": the four writes and what stays human-only.
- `CHANGELOG.md` Unreleased: one bullet.
- Run `python3 scripts/check_system_md.py` from the repo root.
- Full backend suite: `pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile`.
- The slop ratchet on `backend`.
- A live check on a key-less scratch backend (spare port): fill the profile, markets and preferences over the tools;
  setup readiness rises; `get_autofill_profile` returns the per-country answers.

Commit: `docs: MCP writes the facts Setup and Profile ask for`.

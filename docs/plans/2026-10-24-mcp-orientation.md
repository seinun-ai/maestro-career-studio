# MCP orientation (audit Phase 2) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A connected agent always knows where setup stands, which tool set holds what it needs, and what the tailoring presets are, without Maestro scripting the conversation.

**Architecture:** One new pure module (`mcp_server/orientation.py`) holds the ordered tool-set table that the allowlists, server instructions and `get_setup_status` all read. Each per-set low-level server (`mcp_server/http.py`) gets its own instructions and serves the automation playbooks as MCP prompts. Two read-only tools are added; nothing writes.

**Tech Stack:** Python 3.12, FastAPI, MCP SDK 1.30 (FastMCP + low-level Server), pytest + respx, Next.js 16 (one component).

Design: `docs/plans/2026-10-24-mcp-orientation-design.md`. Branch: `claude/mcp-phase2-orientation` (from main 19792c38).

**Environment (every task):** run Python from `backend/` with the scratch venv `$V=/private/tmp/claude-501/-Users-ajeyds-Projects-maestro-career-studio--claude-worktrees-api-independence-no-gui-85e978/cfe7e029-00a1-45a8-8e93-1de9ac840714/scratchpad/venv/bin/python`; prefix backend runs with `env -u ANTHROPIC_BASE_URL`. MCP tests: `$V -m pytest -q -p no:cacheprovider mcp_server/tests/<file>`. Never bind ports 8001/3000, never start Docker.

---

### Task 1: The tool-set table and the new allowlists

**Files:**
- Create: `backend/mcp_server/orientation.py`
- Modify: `backend/mcp_server/profiles.py`
- Test: `backend/mcp_server/tests/test_profiles.py`

**Step 1: Write the failing tests** (append; then fix the old tests that name `career`, `explore` or the old apply list, Step 4)

```python
from mcp_server import orientation
from mcp_server.profiles import PROFILE_ALIASES, PROFILE_ALLOWLISTS, get_profile


def test_the_sets_follow_the_journey_and_every_one_is_served():
    assert [s.name for s in orientation.SETS] == [
        "profile", "hunt", "tailor", "apply", "track", "templates", "full"]
    assert set(PROFILE_ALLOWLISTS) == {s.name for s in orientation.SETS}


def test_old_names_still_resolve_for_one_release():
    assert PROFILE_ALIASES == {"career": "profile", "explore": "track"}
    assert get_profile("career") == "profile" and get_profile("explore") == "track"


def test_every_scoped_set_but_templates_opens_with_setup_status():
    for name, allow in PROFILE_ALLOWLISTS.items():
        if allow is not None and name != "templates":
            assert "get_setup_status" in allow, name


def test_tailor_application_lives_only_in_full():
    assert all("tailor_application" not in a for a in PROFILE_ALLOWLISTS.values() if a)


def test_set_sizes_stay_near_the_line():
    sizes = {n: len(a) for n, a in PROFILE_ALLOWLISTS.items() if a is not None}
    assert sizes == {"profile": 39, "hunt": 22, "tailor": 32, "apply": 34, "track": 18, "templates": 13}
```

**Step 2:** `$V -m pytest -q -p no:cacheprovider mcp_server/tests/test_profiles.py` → FAIL (no `orientation`).

**Step 3: Implement.** `orientation.py`:

```python
"""The tool sets, in the order a job search moves through them.

One table read by the allowlists' docs, the per-set server instructions and
get_setup_status, so a set's name and job are written once. Pure: no httpx, no app.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSet:
    name: str
    use_when: str  # the user's own words
    holds: str


SETS: tuple[ToolSet, ...] = (
    ToolSet("profile", "set me up, import my resume, add a project, make a resume for a role",
            "career history, base resumes and their anchors, the health check, versions, "
            "form answers, job preferences, markets, persona"),
    ToolSet("hunt", "find me jobs", "the search brief, saving jobs, scoring, proposing them"),
    ToolSet("tailor", "tailor my resume for this job",
            "looking up or saving the job, scoring, gaps, the tailored resume and its PDF, "
            "the health check, undo, the tailoring presets"),
    ToolSet("apply", "apply to this job, work my queue",
            "cover letter and answers, form answers, the proposal, evidence, the user's yes, submit"),
    ToolSet("track", "update my statuses, how is my search going",
            "applications and their statuses, referrals, the analytics charts"),
    ToolSet("templates", "make a resume design", "resume templates: draft, validate, preview"),
    ToolSet("full", "anything", "every tool"),
)
```

`profiles.py`: replace `VALID_PROFILES`, the five allowlists and `PROFILE_ALLOWLISTS` with `PROFILE_TOOLS`, `HUNT_TOOLS`, `TAILOR_TOOLS`, `APPLY_TOOLS`, `TRACK_TOOLS`, `TEMPLATES_TOOLS` exactly as the design lists them; keep `CAREER_TOOLS = PROFILE_TOOLS` and `EXPLORE_TOOLS = TRACK_TOOLS` as names for importers; add `PROFILE_ALIASES = {"career": "profile", "explore": "track"}`; `VALID_PROFILES = frozenset(PROFILE_ALLOWLISTS) | frozenset(PROFILE_ALIASES)`; `get_profile` maps an alias to its set. Update the module docstring.

**Step 4:** rewrite the old profile tests to the new sets (e.g. `test_career_profile_*` → `profile`; the apply-package test now checks `APPLY_TOOLS`; the fact-writes test: writes in `profile`, `set_autofill_profile` in `apply`, none in hunt/track/templates). Run the file → PASS. Then `$V -m pytest -q -p no:cacheprovider -n auto mcp_server/tests/` and fix fallout (counts in `test_mcp_http_loopback.py` stay 99 until Task 2/3 add tools).

**Step 5: Commit** `feat(mcp): tool sets split the way an agent looks for them`.

---

### Task 2: `get_setup_status`

**Files:**
- Modify: `backend/app/schemas/setup_status.py` (`demo_bases: list[str] = []`), `backend/app/services/setup_status.py` (fill it: active, unarchived bases whose slug is `seeding.DEMO_SLUG`)
- Modify: `backend/mcp_server/workflow.py` (pure `setup_next_step(status)`), `backend/mcp_server/server.py` (tool), profiles (already lists it)
- Test: `backend/tests/test_setup_status.py` (or the existing setup-status test file), `backend/mcp_server/tests/test_workflow.py`, `backend/mcp_server/tests/test_onboarding_tools.py`

**Step 1: failing tests**
- REST: with the demo base present, `GET /api/setup/status` has `demo_bases == ["example"]`; archived or absent → `[]`.
- Pure: `setup_next_step({...import_resumes done False...})` → `{"step": "career_history", "tool_set": "profile", ...}`; all agent steps done → `None`; `model_key` and `template` never returned.
- Tool (respx on `/api/setup/status`): returns `ai_key`, `demo_bases`, `next_step`, `steps` (the REST body), `tool_sets` (one line per set from `orientation.SETS`).

**Step 3: implement.** Order of agent steps: `import_resumes` → "career_history", `autofill` → "form_answers", `job_preferences`, `persona`; each with `tool_set: "profile"` and a one-line `says`. Docstring: behaviour and fields only; ≤ the ratchet.

**Step 5: Commit** `feat(mcp): get_setup_status tells an agent where setup stands`.

---

### Task 3: `get_tailoring_options`

**Files:**
- Modify: `backend/app/schemas/quick_tailor.py` (a `Field(description=...)` per switch: the plain meaning)
- Modify: `backend/mcp_server/client.py` (`get_tailoring_options`: GET `/api/settings/quick-tailor` and `/api/settings/persona`), `backend/mcp_server/server.py` (tool, `_read`)
- Test: `backend/mcp_server/tests/test_client_read.py` (or a new `test_tailoring_options.py`)

**Step 1: failing test** (respx): the tool returns `presets` = `[{key, on, means}]` for the four switches in schema order, `instruction`, `persona`; `means` equals each field's description (one source).

**Step 3: implement**; the docstring says quick_tailor follows these presets and a custom tailor walks the gaps with the user and saves decisions with resolve_gaps; the presets are the user's, set in the app.

**Step 5: Commit** `feat(mcp): get_tailoring_options lets an agent explain the presets`.

---

### Task 4: Per-set server instructions and the aliases over HTTP

**Files:**
- Modify: `backend/mcp_server/orientation.py` (`instructions_for(profile) -> str`)
- Modify: `backend/mcp_server/http.py` (`build_profile_server(..., instructions=orientation.instructions_for(p))`; route an alias to its set's manager), `backend/mcp_server/server.py` (`FastMCP(..., instructions=orientation.instructions_for("full"))`)
- Test: `backend/mcp_server/tests/test_orientation.py` (new), `backend/mcp_server/tests/test_http.py`

**Step 1: failing tests**
- For every set: `len(instructions_for(s)) <= 4096`; it names every other set; it says "get_setup_status" (except templates); it names no tool outside the set (scan backticked words against the registry).
- HTTP: `initialize` on `/mcp/tailor` returns `instructions` mentioning "tailor"; `/mcp/career` lists exactly `PROFILE_TOOLS`; `/mcp/explore` lists `TRACK_TOOLS`. Update the parametrized profile lists in `test_http.py` to the new names.

**Step 3: implement.** Text shape (plain, ≤ ~1,500 chars):
"Maestro Career Studio keeps one person's job search on their computer. This is the {name} set: {holds}. Use it when the user says {use_when}. It does not {what the others hold, in one clause}. Other sets: {name: holds; …}. Start with get_setup_status. However you tailor or apply, Maestro holds its rules: an unproven skill goes only into the skills list, resume lines stay in the owner's first person, saved keywords land."

**Step 5: Commit** `feat(mcp): each tool set says what it does and where the rest is`.

---

### Task 5: Each playbook names its set

**Files:**
- Modify: every card's `backend/app/automations/skills/*/SKILL.md` frontmatter (`metadata.toolset`), `backend/app/services/automations.py` (`_Meta.toolset: Literal[...]`, wrapper names the set), `backend/app/automations/skills/agent-apply-execution/SKILL.md` (auto lane: the job arrives tailored; drop the `edit_base_resume` mention)
- Test: `backend/tests/test_automations_service.py`, `backend/mcp_server/tests/test_profiles.py`

**Step 1: failing tests**
- Each card's toolset: job-hunt, referral-pages → hunt; tailor-run → tailor; apply-session, apply-auto → apply; mail-status → track; customize-job-skills → full.
- Every MCP tool named in a card's body (with its includes) is in its toolset's allowlist (full: all).
- The copied prompt names the set: "Connect Maestro's {toolset} tool set (or the full set)" in the wrapper (full: no set line).

**Step 5: Commit** `feat(automations): each playbook names the tool set it needs`.

---

### Task 6: The playbooks as MCP prompts

**Files:**
- Modify: `backend/mcp_server/http.py` (per-set `@server.list_prompts()` / `@server.get_prompt()` from `automations` cards whose toolset is that set, all in full; prompt name = card id, description = card summary, one user message = card prompt)
- Test: `backend/mcp_server/tests/test_http.py`

**Step 1: failing tests:** `/mcp/tailor` `prompts/list` = `["tailor-run"]`; `/mcp` lists every card; `prompts/get` `tailor-run` returns the same text as `automations.catalog()`'s card prompt; an unknown name is an error.

**Step 5: Commit** `feat(mcp): the automation playbooks are MCP prompts in their set`.

---

### Task 7: Hint wording that names sets

**Files:** `backend/mcp_server/workflow.py` (lines naming "apply and full", "templates and career"), `backend/mcp_server/tests/test_workflow.py`

Replace profile names in hint prose with the new set names ("the tailor and full sets", "profile"); keep the "never names a tool the set lacks" test green across the new sets (it iterates `PROFILE_ALLOWLISTS`).

**Commit** `fix(mcp): hints name the new tool sets`.

---

### Task 8: The surfaces that list sets

**Files:**
- `frontend/components/settings/connect-assistant-card.tsx` (`PROFILES`: Full, Profile, Hunt, Tailor, Apply, Track, Templates), `frontend/lib/types.ts` (`ConnectProfile["name"]`), backend tests that pin the card
- `backend/maestro_cs/connect.py` (help line), `backend/tests/maestro_cs/test_connect.py`
- `backend/app/routers/setup.py` connect endpoint's profile validation (accept new names and aliases), `backend/tests/test_setup_connect.py`
- `.github/workflows/ci.yml` (stdio loop: full profile hunt tailor apply track templates; HTTP smoke unchanged)
- `mcpb/manifest.json` (profile description), `mcpb/tests/bridge.test.js` if it lists names
- `backend/mcp_server/codex_config.example.toml`, `claude_desktop_config.example.json`, `plugins/maestro-career-studio/.codex-mcp.json` if they name a scoped set

Tests first where a test pins the list; then `npx tsc --noEmit`, `npm run lint`.

**Commit** `feat: the connect surfaces offer the new tool sets`.

---

### Task 9: Docs

SYSTEM.md §3/§7 (101 tools, set names), `docs/agent-surfaces.md` (MCP server: sets, aliases, instructions, prompts, the two read tools), `docs/entities/others.md` (MCP tool coverage), `backend/mcp_server/README.md` (set table), `plugins/maestro-career-studio/README.md`, `docs/USING_MAESTRO.md`, `docs/GETTING_STARTED.md`, `README.md`, `KNOWN_ISSUES.md`, `.system_md_enforcement.json` (pins for the new tests), CHANGELOG (Breaking: apply slimmed, tailor and track sets, aliases; Added: get_setup_status, get_tailoring_options, playbooks as prompts). Run `python3 scripts/check_system_md.py`.

**Commit** `docs: the new tool sets, setup status, tailoring options and prompts`.

---

### Task 10: Verify

1. `npm ci` in `frontend/` if missing; full backend suite `env -u ANTHROPIC_BASE_URL $V -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile -p no:cacheprovider` → 0 failed.
2. Frontend: `npx tsc --noEmit`, `npm run lint`, `npm run build`.
3. `python3 scripts/check_system_md.py`; `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check backend` and `check frontend`.
4. Live, key-less scratch backend on a spare port: initialize each set (instructions present), `prompts/list` per set, `get_setup_status` on an empty install (next step career history), then after onboarding (next step form answers), `get_tailoring_options`, and the 43-call walk on `full`.
5. Code review by a subagent; address findings; full suite again.

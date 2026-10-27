# Merging near-duplicate MCP tools: implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development in this session) to implement this plan task-by-task.

**Goal:** 99 → 92 MCP tools with no capability lost: `explore_trends(view)` for six analytics tools, `get_career_context(format)`, `attach_evidence(image_base64 | file_path)`, approve-only `kb_approve_points`, and removed names that say what replaced them.

**Design:** `docs/plans/2026-10-26-mcp-tool-merges-design.md` (owner-approved 2026-10-26). Read it first.

**Architecture:** MCP-layer only: tools in `backend/mcp_server/server.py`, the HTTP client in `client.py`, sets in `profiles.py`, per-set servers in `http.py`. No REST route changes: each merged tool calls the routes its old tools called. One map (`mcp_server/profiles.py` or a small new module) from removed names to replacements, consulted by `http.McpEndpoint`'s per-set `call_tool` and by the stdio server before FastMCP's own "Unknown tool".

**Tech stack:** FastMCP (`mcp` SDK), httpx + respx client tests, pytest with xdist.

**Constraints:**
- Never start Docker; never bind ports 8001 or 3000. Neutral sample data.
- `PY=/private/tmp/claude-501/-Users-ajeyds-Projects-maestro-career-studio--claude-worktrees-api-independence-no-gui-85e978/cfe7e029-00a1-45a8-8e93-1de9ac840714/scratchpad/venv/bin/python`; from `backend/`: `env -u ANTHROPIC_BASE_URL $PY -m pytest -q -p no:cacheprovider <paths>`; the full suite with `-n auto --dist loadfile`.
- TDD; commit per task with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; branch `claude/mcp-phase3b-merges`; no push or merge.
- Tool descriptions stay within the 2000-character budget (`test_registered_tool_docstrings_fit_client_truncation_budget`); overflow goes into parameter descriptions, the file's existing pattern (`_TAILOR_OPS_FIELD`, `_USE_PRESETS_FIELD`).
- Every description and parameter description names only tools present in every set that serves the tool (the set-scope test in `mcp_server/tests/test_server.py`).

---

### Task 1: `explore_trends`

**Files:** `backend/mcp_server/server.py` (new tool; delete the six), `backend/mcp_server/client.py` (one `explore_trends(view, ...)` dispatching to the six existing routes, or keep the six client methods and dispatch in the tool — pick the smaller diff; delete client methods nothing calls), `backend/mcp_server/profiles.py` (`TRACK_TOOLS`: drop the six, add `explore_trends`). Tests: `mcp_server/tests/test_client_read.py` (or wherever the explore client tests live), `test_server.py`, `test_profiles.py` (track 13).

Behaviour (design §1):

| view | route | filters (role_category, level, employment_type) | limit |
|---|---|---|---|
| `top_skills` | `/api/explore/top-skills` | yes | 1–100 |
| `heatmap` | `/api/explore/heatmap` | no | 1–100 |
| `role_mix` | `/api/explore/role-mix-over-time` | no | no |
| `fit_distribution` | `/api/explore/fit-distribution` | no | no |
| `ats_over_time` | `/api/explore/ats-over-time` | yes | no |
| `tailoring_lift` | `/api/explore/tailoring-lift` | yes | no |

- `view: Literal[...]` with a parameter description carrying each view's meaning (move the six old docstrings' content there, trimmed: what each returns and how to read it, e.g. heatmap rows' `count`/`of`, role_mix's every-week shape).
- `limit: Annotated[int | None, Field(ge=1, le=100)] = None`.
- A filter or `limit` the view doesn't take raises `ToolError("<view> takes no <filters|limit>")` before any request. Plain words.
- Read-only annotation like the old ones.

Tests first: each view hits its route with the right params (respx); a refused filter/limit makes no request; the six old names are registered nowhere; `explore_gap_frequency` unchanged. Commit `feat(mcp): explore_trends answers six analytics views`.

### Task 2: `get_career_context(format=...)`

**Files:** `server.py` (`get_career_context(format: Literal["json", "markdown"] = "json")`; delete `get_career_export`), `client.py` (keep `get_career_export()` as the markdown read or fold it), `profiles.py` (`PROFILE_TOOLS` drops `get_career_export`). Docstring: json = structured context (no IDs; `kb_list_entities` for IDs), markdown = the exact portable career.md text. Tests first: both formats hit the right route; markdown returns the text unchanged; `get_career_export` registered nowhere. Commit `feat(mcp): career context in JSON or as career.md`.

### Task 3: `attach_evidence(image_base64 | file_path)`

**Files:** `server.py` (`attach_evidence(proposal_id, step, label, kind="step", image_base64=None, file_path=None)`; delete `attach_evidence_file`), `client.py` (keep both upload paths behind the tool), `profiles.py` (`APPLY_TOOLS` drops `attach_evidence_file`). Exactly one input: both or neither → `ToolError` naming the rule, no request. Keep `attach_evidence_file`'s path checks (what files are allowed, size, where) for the `file_path` branch exactly. Docstring within budget (the evidence kinds stay documented). Tests first: inline image, file path, both, neither; the old name registered nowhere; the existing evidence tests ported. Commit `feat(mcp): attach_evidence takes an image or a file`.

### Task 4: approve-only `kb_approve_points`

**Files:** `server.py` (drop `state`; title "Approve Career Points", `destructive=False`; docstring: approves drafts, use `kb_retire_points` to retire), tests in `mcp_server/tests/` that passed `state="retired"` move to `kb_retire_points`. Check the client sends `state="approved"` to the same REST call. Tests first: no `state` parameter in the tool's input schema; it always approves. Commit `feat(mcp): kb_approve_points only approves`.

### Task 5: removed names say what replaced them

**Files:** a map in `mcp_server` (e.g. `profiles.REPLACED = {"explore_top_skills": 'explore_trends(view="top_skills")', "explore_skill_heatmap": 'explore_trends(view="heatmap")', "explore_role_mix_over_time": 'explore_trends(view="role_mix")', "explore_fit_distribution": 'explore_trends(view="fit_distribution")', "explore_ats_over_time": 'explore_trends(view="ats_over_time")', "explore_tailoring_lift": 'explore_trends(view="tailoring_lift")', "get_career_export": 'get_career_context(format="markdown")', "attach_evidence_file": "attach_evidence(file_path=...)", "quick_tailor": "create_tailoring_session(use_presets=true)", "tailor_application": "a tailoring session (create_tailoring_session, then tailor_session), or edit_application for the current draft"}` and a helper `replaced_message(name) -> str | None` → `"<name> was replaced by <replacement>."`).
- HTTP (`http.py` `_call_tool`): before raising "Unknown tool", if the name is in the map, raise `ToolError(replaced_message(name))`. Covers scoped sets and `full` (for `full`, FastMCP's own unknown-tool path: check the name first).
- stdio (`server.main` / `apply_profile_filter`): make an unknown name in the map answer the same message (e.g. wrap the tool manager's `call_tool`, or register a FastMCP-level hook if the SDK has one; keep it small and tested with an in-process call).
- Map test: every key is registered in no set; every replacement's tool name(s) (the identifier before `(` or named in the text) is registered.
- Extend Phase 3a's removed-names denylist (`test_removed_tools_are_named_nowhere_an_agent_reads` in `test_server.py`, `test_no_hint_names_a_removed_tool` in `test_workflow.py`) to all map keys.

Tests first: an in-process HTTP call (the existing `test_http.py` pattern) to `explore_top_skills` on `/mcp/track` and on `/mcp/full` returns the message; stdio likewise; an unknown name not in the map keeps the plain error. Commit `feat(mcp): a removed tool name says what replaced it`.

### Task 6: everything that names the old tools

- Playbooks: `backend/app/automations/skills/agent-apply-execution/SKILL.md` (~71, `attach_evidence_file`), any other SKILL.md naming a removed tool (the playbook scans in `tests/test_automations_service.py` will fail first).
- Hints and instructions: `mcp_server/workflow.py`, `orientation.py` (grep; the denylist test catches them).
- Counts: `tests/test_mcp_http_loopback.py` (92), `mcp_server/tests/test_profiles.py` sizes (`profile` 38, `apply` 34, `track` 13), CI's profile loop needs no change.
- Frontend: grep `frontend/` for the removed names (e.g. a tool-name list in `connected-agents-card.tsx`).
Full backend suite with xdist. Commit `chore(mcp): playbooks, hints and counts follow the merged tools`.

### Task 7: docs

SYSTEM.md §3/§7 counts (92; profile 38, apply 34, track 13) within the byte budget; `docs/agent-surfaces.md` (tool lists, explore views, career export, evidence, approve/retire, the replaced-by rule); `docs/entities/others.md` (MCP tool coverage); `docs/playbooks/agent-apply.md` (~327, ~351, ~373 `attach_evidence_file`); `backend/mcp_server/README.md` (tool table, counts); `plugins/maestro-career-studio/README.md`, `backend/mcp_server/codex_config.example.toml`, `mcpb/manifest.json`, `README.md`, `KNOWN_ISSUES.md`, `docs/GETTING_STARTED.md`, `docs/USING_MAESTRO.md` (counts); `CHANGELOG.md` Unreleased breaking: each removed name → its replacement, `kb_approve_points` no longer retires, 92 tools (update the earlier "99 tools" bullets). `python3 scripts/check_system_md.py` OK. Commit `docs: the merged MCP tools and what replaced each removed name`.

### Task 8: verification

1. Full backend suite (xdist), frontend `tsc`/`lint`/`build` and the CI node tests if `frontend/` changed, SYSTEM.md gate, slop ratchets (backend, frontend, extension; re-baseline only with a stated reason per SYSTEM.md §9).
2. Live on a scratch backend (spare port, scratch home): each `explore_trends` view on `/mcp/track` with and without filters (and a refused filter), `get_career_context` both formats on `/mcp/profile`, `attach_evidence` both inputs on `/mcp/apply`, `kb_approve_points` on `/mcp/profile`, and an old name (`explore_top_skills`, `quick_tailor`) on its old set and on `full`.
3. Whole-branch review (fresh Opus reviewer) over `git diff main...HEAD`; fix findings with tests; rerun the suite.
4. Report; merge only on the owner's word.

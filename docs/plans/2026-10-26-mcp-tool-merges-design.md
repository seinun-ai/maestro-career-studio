# Merging near-duplicate MCP tools (audit Phase 3b): design

Date: 2026-10-26. Owner-approved in conversation. Follows Phase 3a (who writes over MCP, tailoring without Maestro's AI; on main 07431ba3). Phase 3c (coverage holes) gets its own design.

## Goal

Fewer near-duplicate choices for an agent, with no capability lost: 99 tools → 92. An agent or an old saved prompt that calls a removed name is told what replaced it.

## Owner decisions

- Merge the analytics tools (7 → 2), two pairs (career context/export, evidence image/file), and make `kb_approve_points` approve-only.
- Keep `list_jobs` and `export_jobs` apart: they take different filters (`without_application` and source vs role, level, date and skill), so one tool would carry parameters that work in only one mode.
- Keep apart: `archive_base_resume`/`unarchive_base_resume`, `get_proposal`/`get_final_review` (the final review is the consent bundle), `get_rendered_pdf`/`get_rendered_pdf_page_image` (the page image is an explicit opt-in to a large payload).
- A removed name answers with its replacement, not a bare "Unknown tool". The same map covers Phase 3a's `quick_tailor` and `tailor_application`.

## 1. Analytics: `explore_trends`

`explore_trends(view, role_category=None, level=None, employment_type=None, limit=None)` replaces `explore_top_skills`, `explore_skill_heatmap`, `explore_role_mix_over_time`, `explore_fit_distribution`, `explore_ats_over_time`, `explore_tailoring_lift`. Each view calls the REST route its old tool called (`/api/explore/top-skills`, `/heatmap`, `/role-mix-over-time`, `/fit-distribution`, `/ats-over-time`, `/tailoring-lift`), so answers are unchanged.

| view | filters | limit |
|---|---|---|
| `top_skills` | role_category, level, employment_type | 1–100 |
| `heatmap` | none | 1–100 |
| `role_mix` | none | none |
| `fit_distribution` | none | none |
| `ats_over_time` | role_category, level, employment_type | none |
| `tailoring_lift` | role_category, level, employment_type | none |

A filter or `limit` a view doesn't take is refused with a plain sentence ("role_mix takes no filters"), not ignored. The per-view detail lives in the `view` parameter's description so the tool description stays within the budget. `explore_gap_frequency` is unchanged. The track set drops 18 → 13.

## 2. Two pairs

- `get_career_context(format="json")`: `format="markdown"` returns the career.md text `get_career_export` returned (`GET /api/exports/career`). `get_career_export` is removed. Profile 39 → 38.
- `attach_evidence(proposal_id, step, label, kind="step", image_base64=None, file_path=None)`: exactly one of `image_base64` (inline) or `file_path` (a file already on this machine) is required; both or neither is refused plainly. `attach_evidence_file` is removed. Apply 35 → 34.

## 3. Approve-only

`kb_approve_points(point_ids)` loses `state`; `kb_retire_points` is the one way to retire. Approve is annotated non-destructive; retire keeps its annotation.

## 4. Removed names say what replaced them

One map in the MCP package from each removed name to its replacement (the six analytics names, `get_career_export`, `attach_evidence_file`, `quick_tailor`, `tailor_application`). Calling a removed name over HTTP (any set) or stdio returns, e.g., `explore_top_skills was replaced by explore_trends(view="top_skills").` A test keeps the map honest: every key is unregistered and every replacement names a registered tool.

## Totals

92 tools: profile 38, hunt 22, tailor 31, apply 34, track 13, templates 13.

## Testing

TDD per change: each view's route, filters and refusals; `format` both ways; `attach_evidence` both inputs and the two refusals; `kb_approve_points` with no `state`; the replaced-by message on both transports and in scoped sets; the map test; set sizes; the removed-names denylist, set-scope and playbook scans from Phase 3a extended to the new names. Then the full backend suite, frontend gates, SYSTEM.md gate, slop ratchets, a live MCP check of each merged tool and an old name's message, and a whole-branch review.

## Docs

The apply technique (`agent-apply-execution/SKILL.md`) and `docs/playbooks/agent-apply.md` (`attach_evidence_file`), SYSTEM.md (§3/§7 counts), `docs/agent-surfaces.md`, `docs/entities/others.md`, the MCP and plugin READMEs, the example configs and manifest counts, README/USING_MAESTRO/GETTING_STARTED/KNOWN_ISSUES counts, CHANGELOG (breaking: the removed names and their replacements).

## Changed during review (2026-10-26)

- `heatmap` and `role_mix` take the role_category, level and employment_type filters too: their REST routes accept them and the web uses them. Only `fit_distribution` refuses filters ("fit_distribution takes no filters").
- A replaced-by answer names the set that serves the replacement when the caller's set doesn't ("…, in the track set.").
- `kb_approve_points` refuses an old `state` other than "approved": FastMCP drops undeclared arguments, so an old retire call would otherwise approve.
- `McpEndpoint` takes only the server's FastMCP subclass, which holds the replaced-by answer and that guard for every transport.

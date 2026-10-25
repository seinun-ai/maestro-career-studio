# MCP orientation (audit Phase 2): design

Date: 2026-10-24. Owner-approved in conversation. Follows the MCP audit (Phase 1, the safety fixes, is on main at 19792c38).

## Goal

A connected agent, with no web app and no AI key in Maestro, should always know where setup stands, which tool set holds what it needs, and what Maestro's tailoring presets are, without Maestro scripting the conversation.

## Principle

Maestro supplies the facts and the rules: career history, the job's gaps, the user's presets, the guardrails (unproven skills only in the skills list, no third-person lines, saved keywords always land). The agent owns the conversation: how it explains, asks (multiple choice, one at a time, anything) and decides with the user. Keep our side tidy: data and static text, no new conversation logic.

## 1. Tool sets, split the way an agent would look for them

Each set is the job in the user's own words, ordered like the journey. Every set's server instructions say what it does, what it does not, and which set has the rest.

| Set | Use when the user says | Holds | Tools |
|---|---|---|---|
| `profile` (was `career`) | "set me up", "import my resume", "add a project", "make a resume for data roles" | career history, base resumes and anchors, health check, versions, form answers, preferences, markets, persona | 39 |
| `hunt` | "find me jobs" | search brief, capture, score, propose | 22 |
| `tailor` (new) | "tailor my resume for this job" | look up or capture the job, score, gaps, tailored resume, PDF, health check, undo, the tailoring presets | 32 |
| `apply` (slimmed) | "apply to this job", "work my queue" | cover letter and answers, form answers, proposal, evidence, consent, submit, career context for writing | 34 |
| `track` (was `explore`) | "update my statuses", "how's my search going" | applications and statuses, referrals, analytics | 18 |
| `templates` | "make a resume design" | unchanged | 13 |
| `full` | power users; Claude Code (loads names only) | everything | 101 |

Exact allowlists:

- **profile**: get_setup_status, get_career_context, get_career_export, get_job_search_brief, kb_ingest_resume, kb_add_points, kb_capture, kb_approve_points, kb_retire_points, kb_combine_points, kb_groom_entity, kb_create_entity, kb_edit_entity, kb_edit_point, kb_edit_profile, kb_get_entity, kb_list_entities, kb_list_points, kb_sync_base, list_base_resumes, get_base_resume, create_base_resume_from_kb, set_base_resume_identity, edit_base_resume, archive_base_resume, unarchive_base_resume, list_resume_versions, restore_resume_version, render_pdf, get_rendered_pdf, run_health_check, get_health_report, judge_health_bullets, waive_health_gate, get_autofill_profile, set_autofill_profile, set_job_preferences, set_markets, set_persona.
- **hunt**: today's 21 plus get_setup_status.
- **tailor**: get_setup_status, get_tailoring_options, get_career_context, list_base_resumes, get_base_resume, store_extracted_jd, find_job_by_url, get_job, list_jobs, score_ats, compare_ats, create_tailoring_session, quick_tailor, get_tailoring_session, list_tailoring_sessions, resolve_gaps, close_tailoring_session, tailor_session, edit_application, get_application, render_pdf, get_rendered_pdf, get_rendered_pdf_page_image, run_health_check, get_health_report, judge_health_bullets, waive_health_gate, list_resume_versions, restore_resume_version, list_proposals, propose_application, record_run.
- **apply**: get_setup_status, get_career_context, list_proposals, get_proposal, get_final_review, propose_application, record_decision, request_decision, resume_proposal, record_triage, report_failure, record_consent, mark_submitted, attach_evidence, attach_evidence_file, record_filled_answers, get_job_site_login, get_autofill_profile, set_autofill_profile, prepare_application_pdf_upload, get_rendered_pdf, get_rendered_pdf_page_image, generate_cover_letter, store_cover_letter, generate_qa_answers, store_qa_answers, list_qa_entries, edit_application, get_application, update_application, get_job, list_referrals, record_run, sync_now.
- **track**: get_setup_status, list_applications, get_application, update_application, list_jobs, get_job, export_jobs, list_proposals, list_referrals, get_job_search_brief, the seven explore_* tools, record_run.
- **templates**: unchanged.

`tailor_application` leaves every scoped set (it skips the session's checks); it stays in `full`. Each automation playbook fits one set: job-hunt and referral-pages → hunt, tailor-run → tailor, apply-session, apply-auto and agent-apply-execution → apply, mail-status → track, customize-job-skills → hunt. A test pins that every tool a playbook names is in its set.

**Aliases.** `/mcp/career` serves `profile` and `/mcp/explore` serves `track` for one release; `MAESTRO_CS_MCP_PROFILE` accepts both. `/mcp/apply` keeps its name with the slimmer list (a breaking change, in the changelog: tailoring moved to `tailor`).

## 2. `get_setup_status` (read-only, in every set but templates)

Wraps `GET /api/setup/status` and adds, for an agent:

- `ai_key`: whether Maestro has an AI key (pick `generate_*` or `store_*`, `kb_capture` or `kb_add_points`).
- `demo_bases`: base resume slugs that are the shipped demo (`seeding.DEMO_SLUG`), never the user's. A new `demo_bases` field on the REST status, so the web and MCP read one definition.
- `next_step`: the first step an agent can do that is not done, in order: career history, form answers, job preferences, persona; each names the tool set that does it. The AI key and the default template are the user's, in the app, and are reported but never a next step. Computed in `workflow.py` (pure).
- `tool_sets`: one line per set (from the same table the instructions use).

## 3. Server instructions per set

One module, `mcp_server/orientation.py`, holds the ordered set table (name, use when, holds). `instructions_for(profile)` builds, under Claude Code's 4,096-character cut: one line on Maestro, this set's job and what it leaves out, the other sets in one line each, "start with get_setup_status", and the principle that the guardrails hold however the agent works. `full` gets the whole map. `http.build_profile_server` passes each set its own text; the stdio FastMCP keeps the `full` text.

## 4. `get_tailoring_options` (read-only, in tailor and full)

The Quick tailor presets as data an agent can explain: each switch with `on` and a plain `means` (from `Field(description=...)` on `QuickTailorProfile`, one source), the standing instruction, the persona, and a short note that `quick_tailor` follows the presets while a custom tailor walks the gaps with the user and saves decisions with `resolve_gaps`. No writes: the presets stay the user's, in the app.

## 5. The automation playbooks as MCP prompts

Each per-set server answers `prompts/list` and `prompts/get` from the existing `automations/skills/*/SKILL.md`: a playbook appears in the set its frontmatter names (`metadata.toolset`) and in `full`. The text is exactly what the web's Copy prompt gives (`automations._prompt`), so it exists once. Claude Code shows them as `/maestro-career-studio:<name>` commands. The Copy prompt's wrapper names the set to connect.

## Dropped and deferred

- Dropped: extending the next-step hint chain. Setup status and the instructions cover orientation with fewer moving parts.
- Deferred to Phase 3 (with the tailoring tool consolidation): key-less `tailor-run` (mechanical tailoring or not) and whether unattended runs may add unclaimed skills.

## Testing

TDD per task. Pins: the allowlists (counts, the playbook-in-its-set rule, get_setup_status in every set but templates, tailor_application only in full), aliases over HTTP and stdio, per-set instructions (length, names every other set, no tool outside the set), prompts per set, the pure next-step function, the REST `demo_bases` field, client calls (respx), the Connect card's set list, CI's profile loop. Full backend suite, frontend gates, SYSTEM.md gate, slop ratchets, then a live no-key walk over the new sets.

## Docs

SYSTEM.md §7 (counts, set names), docs/agent-surfaces.md, docs/entities/others.md (MCP tool coverage), the MCP and plugin READMEs, USING_MAESTRO, GETTING_STARTED, the Codex and Claude example configs, the `.mcpb` manifest, `maestro connect` help text, CHANGELOG (breaking: apply slimmed, new sets, aliases).

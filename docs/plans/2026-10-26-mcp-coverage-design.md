# Closing the MCP coverage holes (audit Phase 3c): design

Date: 2026-10-26. Owner-approved in conversation. Follows Phase 3b (tool merges, 92 tools; on main 32a864ff). Closes the audit's remaining coverage holes (static audit §2 and §6.3) for a user who works only through an agent app.

## Goal

An MCP-only user can correct what they saved, keep what they chose, and trust that an agent's saves never erase another writer's, with as few new tools as possible: 92 → 94.

## Principle

Extend an existing tool with a parameter wherever the job is the same; add a tool only for a new write with its own consent weight. Nothing changes for a call that doesn't use the new parameter. Maestro supplies facts and rules; the agent owns the conversation.

## 1. Jobs and resumes

- **Correct a saved job.** `store_extracted_jd(..., update=false)`. With `update=true` and a posting already saved (same text or URL), the new extraction replaces its fields and skills through the same mapping a new capture uses, instead of returning the saved row unchanged. The response names what changed. Saved match scores for that job are marked out of date so the next `score_ats` recomputes them; a tailored resume or an open gap analysis is left alone and named in the response. Without `update`, a repeat capture returns the saved job unchanged, as today, and the description says so.
- **The application link.** `store_extracted_jd` takes `apply_url` (an application address that differs from the posting); `find_job_by_url` on it then finds the job.
- **Keep a chosen design.** `render_pdf(..., template_id=None, formatting=None, keep=false)`. With `keep=true` the template and look settings are saved on that base resume or tailored resume, so later edits re-render in them. Without `keep`, rendering stays a one-off preview, as today.
- **Archived bases.** `list_base_resumes(include_archived=false)`.

## 2. Applying and tracking

- **Cover letter upload.** `prepare_application_pdf_upload(application_id, document="resume")`; `document="cover_letter"` stages the stored letter's PDF under the same rules (same upload directory, same integrity fields). With no letter stored, it says so.
- **Clearing.** `update_application(..., clear=[])` takes `"notes"` and/or `"referral_id"`; a field can't be set and cleared in one call.
- **`save_referral(company, careers_url=None, contact_name=None, notes=None, referral_id=None)`.** Creates a referral, or updates one when `referral_id` is given (`POST`/`PUT /api/referrals`). Served in hunt, apply and track (the sets that list referrals).

## 3. Search context, in `get_job_search_brief`

- **Work permits per country.** The answers for each country the user applies in, labelled by country. The old home-market `work_auth` stays for one release, labelled with its country, so readers don't break. The job-hunt playbook reads the per-country answers.
- **Last runs.** When each automation last ran (`GET /api/agent-runs/latest`), which job hunt and mail status start from.
- **The role list.** The 27 role categories with their names. `set_job_preferences` and `create_base_resume_from_kb` refusals for an unknown role name the closest roles (`role_categories.match_free_text` or the catalog's own matcher).

## 4. Data safety

- **Conflict-safe profile writes.** Server-side merge routes for form answers, job preferences and markets (with money) that read, merge and write in one transaction, replacing the MCP client's read-then-PUT. `set_markets` becomes one call. The web app's own PUTs are unchanged. Merge semantics are exactly today's client-side ones (`_merged_autofill`, the lists that replace whole), moved to the server.
- **`kb_merge_entities(keep_id, merge_id)`.** Folds an item an import split off into the one to keep (`POST /api/kb/entities/{id}/merge`); annotated destructive; profile set.

## Totals

94 tools: profile 39, hunt 23, tailor 31, apply 35, track 14, templates 13.

## Testing

TDD per item, including the unchanged paths (a repeat capture without `update`, a render without `keep`, the web's PUTs). Pins for the merge routes under a concurrent write (a Companion learn between the agent's read and write no longer lost). Then the full backend suite, frontend gates if touched, SYSTEM.md gate, slop ratchets, a live MCP check of every item, and a whole-branch review.

## Docs

SYSTEM.md (§3/§7 counts; an invariant line if the merge routes become the rule for agent profile writes), `docs/agent-surfaces.md`, `docs/entities/others.md` and the job/referral/settings entity docs, the MCP and plugin READMEs, counts everywhere, the job-hunt playbook (per-country permits, last run), CHANGELOG (Added; no breaking change expected).

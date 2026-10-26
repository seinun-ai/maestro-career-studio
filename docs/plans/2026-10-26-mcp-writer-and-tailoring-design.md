# Who writes over MCP, and tailoring without Maestro's AI (audit Phase 3a): design

Date: 2026-10-26. Owner-approved in conversation. Follows Phase 2 (tool sets and orientation, on main b60e656e). Phase 3b (other tool merges) and 3c (coverage holes) get their own designs.

## Goal

A user can predict, before they connect an agent app, who does the writing over MCP and who pays for it. Tailoring works end to end without Maestro's own AI key, attended or unattended, and the tailoring tools say plainly what each does.

## Principle

Maestro supplies the facts, the rules and the records. The writing (wording a tailored resume, a letter, an answer, a career note, a judgment on a bullet) is done by one side the user chose. Whoever writes, Maestro's rules hold: implied first person, a skill the user has not shown only in the skills list, saved keywords always land, structure checks on every edit. Keep Maestro's side tidy: one setting, one enforcement point, no new conversation logic.

## Owner decisions

- One setting for every feature, not per feature. Default: the agent app writes.
- Unattended runs write no new wording when the agent app writes.
- Unattended Tailor runs follow the user's Quick tailor presets for job skills the user has never shown, and the digest names each one it added.
- Two tool merges, keeping today's names: `quick_tailor` folds into `create_tailoring_session`; `tailor_application` is removed.

## 1. The setting

`McpWorkflowSettings` (the saved `mcp_workflow` setting, which holds the hints switch) gains `writer: Literal["agent", "maestro"] = "agent"`.

- Settings › Agent apps: "When an agent app is connected, who writes?" with **Your agent app** (uses its own AI; Maestro's key is not used for agent requests) or **Maestro's AI** (uses your API key; the agent app steers). Choosing Maestro's AI with no key configured shows that it needs one.
- The user sets it in the app. No MCP tool writes it.
- `get_setup_status` returns `writer`; each set's instructions tell the agent to check it.

## 2. One enforcement point, at the backend

A request is an agent request when its write-origin header is `mcp` (`app/write_origin.py`, the same header the first-person rule reads). When the setting says the agent app writes, every route an MCP tool reaches that would call Maestro's AI refuses an agent request with 409 and names the tool that takes the agent's own text:

| MCP tool | In agent mode |
|---|---|
| `generate_cover_letter` | refused: use `store_cover_letter` |
| `generate_qa_answers` | refused: use `store_qa_answers` |
| `kb_capture` | refused: use `kb_add_points` |
| `create_tailoring_session(enrich=True)` | refused: run it without `enrich` |
| `tailor_session` with neither `ops` nor `no_new_text` | refused: pass your edits as `ops`, or `no_new_text` |
| `run_health_check` | not refused: the judging is always handed to the agent (`judge_health_bullets`), even with a key |

- The web app and the Companion send no `mcp` origin, so they keep using the key as today.
- Tool lists are the same in both modes: clients cache the list when they connect, so a list filtered by the setting would go stale when the user changes it. The refusal is the source of truth; each affected tool's description says Maestro's AI writes it.

**Maestro's AI mode** is today's key-backed behaviour. Without a key the model routes fail as today, and the health check still hands judging to the agent, so a resume is never stuck ungraded.

**The same in both modes:** reading a job posting (`store_extracted_jd`) and importing a resume (`kb_ingest_resume`) stay with the agent, which is the one looking at them, and Maestro validates what it receives. Scoring, gap analysis, the presets, rendering, version history and every rule stay with Maestro, with no AI.

## 3. Tailoring tools

- **`create_tailoring_session(job_id, base_resume, enrich=False, use_presets=False)`.** `use_presets=True` creates the session and fills it from the user's Quick tailor presets in one call (today's `quick_tailor`). When the fill fails after the session was created, the error names that session id, so a retry never loses it (audit 6.6). `quick_tailor` is removed.
- **`tailor_application` is removed** from MCP (it skipped the session's evidence, keyword and voice checks). Its REST route stays for the web. `edit_application` changes a draft in place.
- **`tailor_session(..., no_new_text=False)`.** With `no_new_text=True`, Maestro writes no new wording and calls no model, in either mode: it applies only the saved answers that need none (an enabled entry, an approved career-history bullet, saved keywords into Skills) and returns the answers that need wording (`answers_left_to_ops`). Combined with `ops` it is refused. When nothing at all can be applied, it is refused with a plain reason.
- **`unbacked_skills`** on every tailor response: skills put in the skills list for missing-skill gaps (no career-history evidence behind them).
- **Descriptions tell the truth:** `tailor_session` renders the PDF; its next-step hint names `render_pdf` only when `pdf_ready` is false.

Known limit: a wording change that needs a rewritten bullet is not made with `no_new_text`; when the job's word is missing from the resume, keyword survival puts it in Skills.

## 4. Tailor run

- Reads `writer` (and `ai_key`) from `get_setup_status` once at the start.
- `create_tailoring_session(job_id, base_resume, use_presets=true)` replaces `quick_tailor`.
- Maestro's AI: `tailor_session` with no `ops`, as today. Agent app: `tailor_session(no_new_text=true)`.
- The digest lists, per job, the unbacked skills it added and the answers left for the user. A missing key no longer fails the run in agent mode.

## Testing

TDD per task. Pins: the setting's shape and default; each guarded route in both modes and from both origins (MCP refused, web unchanged); the health check in agent mode with a key configured; `no_new_text` (applies the three no-text answers, makes no model call with a key configured, lists what is left, refuses with `ops`, refuses when nothing applies); the merged create (presets fill, fill failure names the session); the removed tools; `unbacked_skills`; the Settings choice; the Tailor run text and its tools in the tailor set. Then the full backend suite, frontend gates, SYSTEM.md gate, slop ratchets, and a live check over MCP: agent mode with no key (Tailor run to a linked, rendered resume) and agent mode with a stub key (no model call).

## Docs

SYSTEM.md (§7 counts, the writer rule as an invariant), docs/agent-surfaces.md, docs/entities/tailoring-session.md, docs/entities/others.md, the MCP and plugin READMEs, approval lists that name removed tools, the Tailor run SKILL.md, CHANGELOG (breaking: the default writer, the two removed tools).

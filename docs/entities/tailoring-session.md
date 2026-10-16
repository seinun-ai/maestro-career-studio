# TailoringSession (`models/tailoring_session.py`)

> Reference tier, extracted from [SYSTEM.md](../../SYSTEM.md) (§4 Core entities). The header contract there governs this file too: integrate don't append, present tense, no dates outside the ledgers, update in the same change that alters the behaviour described.

Status machine: `open → tailored` (successful tailor) | `superseded` (a newer
session for the same job+base was created — e.g. "Start over") | `abandoned`
(`POST /tailoring-sessions/{id}/close` — e.g. after "use base as-is").
`gaps_json` is FROZEN at creation; resolutions accumulate against it.

**KB-grounded auto-resolution.** At creation, `gap_enrichment.stamp_library_candidates`
receives a structured Career-KB snapshot + the base's disabled entries;
it SELF-NOMINATES every library item per missing-skills gap and gates all
proposals deterministically (`kb_resolver.verify_candidate`: approved point +
literal `term_in_text` containment + canonical target ⇒ `auto`; else suggestion
chip — LLM proposals are additive only, unreliable even for literal hits).
**This gating pass is LLM-FREE and runs unconditionally** — whether or not
enrichment ran, and whether or not it failed. It used to sit downstream of
`llm.call_openai` INSIDE `enrich_gaps`, which meant `enrich=false` or a provider
outage silently cost KB coverage detection; that was code placement, not design.
`enrich_gaps` now only merges prose and stashes its raw, ungated nominations
under the private `_LLM_PROPOSALS_KEY`, which the gating pass consumes and pops.
The pop is what keeps that private key out of the frozen `gaps_json`: both the
stash and the pop are gated on the same `kb_snapshot is None` test, and
`create_session` re-scrubs via `gap_enrichment.pop_stash` if gating raises. A failure in the
gating pass DEGRADES (warn + ungated gaps), matching the snapshot-load and
enrichment branches either side of it — KB library evidence is an enhancement,
and session creation has already paid for a full engine run.
Verified candidates stamp
`library_candidates`; auto-eligible ones pre-store resolutions with
`payload.provenance` (`library_auto`/`kb_auto`/`kb_profile` — system-planned,
NOT user work; quick tailor's in-progress guard ignores them). `enable_entry`
and `port_kb_point` are exempt from the add_keyword skills-only honesty rule
ONLY because `save_resolutions` re-runs the evidence gate server-side (point
text, wording, and entry text must literally contain the gap's JD skill); a
port may target an entry whose enable is pending in the same projected set
(replace-mode omission revokes it). **Wording autos.** `mirror_wording` gaps
(skill already evidenced; only the literal JD token missing) auto-resolve with
NO KB: `kb_resolver._wording_auto_resolution` plans an `add_keyword` of the
exact token into the enrichment-suggested skills group (else "Additional
Skills"), provenance `wording_auto`. Deliberately NOT extended to `dual_place`
(the fix is prose corroboration) or `absent` (honesty rule — user consent
required). Auto planning runs AFTER the enrichment try-block, so wording autos
survive `enrich=false` and enrichment failure — and so do KB/library autos,
since the gating pass above is unconditional. Only the LLM's *additive*
proposals depend on `enrich=true`. Quick tailor's `mirror_wording` switch governs wording
autos, `keywords_into_skills` governs `kb_profile` autos; the diff endpoint
collapses `wording_auto` into the `kb_auto` label.

**JD Coverage Signal & Non-Latin Script Refusal.**
- **Script guard** (`services/script_guard.py`): text predominantly written in non-Latin scripts (CJK, Cyrillic, Arabic, Hebrew, Devanagari, Thai, Lao) is refused loudly with `UnsupportedScriptError` (HTTP 422) when `non_latin >= 8` characters AND `ratio >= 10%`. Accented Latin (`Zürich`, `Nestlé`) and mathematical Greek symbols are explicitly permitted; the README carries the scope statement.
- **Coverage signal** (`LOW_COVERAGE_THRESHOLD = 0.25`): `AtsResult` computes `jd_skills_extracted_count`, `jd_skills_matched_count`, `coverage_ratio`, and `coverage_warning` ("I could not read this posting — treat this score as unreliable").
- **Persistence**: carried through `subscores_json` without database migration, exposed via `AtsScoreRead` schema property getters on `AtsScore`, and returned in `gaps_json` from `gap_analysis.build_gaps`.
- **Warning banner**: the frontend score panel (`ats-score-panel.tsx`) and gap page render a prominent warning banner when `coverage_warning` is present, preventing vocabulary misses from reading as "no gaps found" or "Strong match".

**Quick tailor from the review checkpoint.** The gap page's "Quick tailor"
(shown only when open gaps remain) POSTs the normal tailor endpoint with
`apply_profile: true`. `quick_tailor.fill_checkpoint_session` plans
resolutions from the saved profile over the frozen gaps, drops every gap_id
that already has a resolution (existing resolutions — the user's and
pre-stored autos alike — always win), and saves the rest through
`save_resolutions` before `tailor()` — deliberately BEFORE, because
`save_resolutions` commits while `tailor()`'s transaction boundary is
`score_target`; routing the fill through `save_resolutions` keeps the honesty
gate. The router only maps its typed errors to HTTP. The profile's standing
`instruction` is a FALLBACK
user_prompt only when the session carries no note of its own (the extension's
Fast tailor passes it too — one saved setting must not mean two things).
Because the fill commits BEFORE
`tailor()`, a failed quick tailor can leave resolutions the gap page never
saw — the page refetches and drops its local copy on any `apply_profile`
error. Custom remains the default entry point; the checkpoint is the only
place the mode is decided.

**The tailor pipeline** (`POST /tailoring-sessions/{id}/tailor`, `tailor()`). Deterministic
pre-ops run first (`enable_entry` → `toggle_entry`, `port_kb_point` → `add_bullet` plus a
`KBPortLog` row; deduped per point and entry); the remaining non-skip resolutions then go to the
smart model, whose typed edit ops are applied. A keyword-survival check follows (one retry, then an
`add_skill_item` fallback; LLM path only), then the voice check (one retry, then repair in code;
**Voice** below). The application is reused or inserted, a version row is written, and substantive
`user_input` answers are written back as draft KBPoints (`origin=gap_elicitation`). Every skipped
write-back returns on the response as `kb_writeback_skips` with a reason (`too_short`,
`wrong_section`, `no_entity_match`, `duplicate`, or `profile_owned_elsewhere`: on the always-on
copy tailoring skips draft career-history points), and the gap page toasts a quiet note, so
flywheel drops are never silent. The session goes `tailored` and the tailored score is staged, all
in ONE transaction: `tailor()` commits once at its end and `score_target` stages on the same
session. A pre-op-only session tailors with zero LLM calls; MCP can pass caller ops to skip the
backend LLM. After a tailor the web UI lands in review mode (`?review=1`): a provenance-labeled
structural diff (`GET /applications/{id}/resume-diff`, hunks attributed `kb_auto`/`user`/`llm`),
revert per hunk through the normal edit path, and an on-demand, read-only coherence lint
(`POST .../coherence-check`).

**Voice.** A resume is the owner's own, in implied first person (SYSTEM.md §6 `inv-resume-voice`). Every rewrite prompt carries the VOICE
rule, built in code beside the avoid-words line (`prompt_assembly._skill_preamble`; `guarded_rewrite` and the chat prompt carry it too, the chat's
scoped to resume and Career KB text), so a customised prompt row keeps it. `services/resume_voice.py` (pure; word boundaries) finds BLOCKING shapes:
a clause-initial He/She/I followed by a verb, `, where he/she/I + verb`, his/her/my directly modifying a noun in the owner's role, the full contact name
(not inside a company name on the resume), and a given name opening a clause or acting as a surname ("Shah built"). They/their, he/she after a noun or
relative word, a capitalised mid-sentence She, a "which has/built" founder clause and a "Builds" opener are FLAGGED only (the health advisory
`voice.third_person`, a note on the summary or a bullet, with the code's repair offered as the suggestion when the rewrite guards accept it). In
`_llm_customized` a blocking hit in the summary or a changed bullet triggers one corrective retry (the same call as the keyword-survival retry); what
is still a hit is repaired in code just before the draft is saved, on EVERY tailoring path (a pre-ops-only edit included): text the model or a caller
wrote is strict (rewrite `He built X` to `Built X`, `, where he built X` to `; built X`, strip a leading name before a past-tense verb, otherwise drop
the sentence or bullet it cannot clean, never join across a subordinator), while a line already on the base gets only mechanical repairs (a
sentence-initial pronoun, the full name; a line that is about other people is stored byte for byte) and is never cut or dropped. State participles
(been, done, seen) are not repaired. A keyword only a repaired line carried is added back to the skills list. The tailor response lists the repaired
paths as `voice_repairs` (`TailorResponse`; the web UI does not show them yet). MCP `tailor_session` ops that write a hit (a changed summary or bullet,
or a bad base line copied into one) return 400 with the lines quoted and a sentence telling the agent to write in implied first person; an
unchanged base line is repaired instead. Check wording (`health_guards.guard_violations`) rejects a rewrite with a blocking hit, including pronouns
the original had. Known limits: a given name that is an ordinary word (Max, Chase, Grant) blocks in model-written text; a path that copies the base as it is
(**Use resume as is**, the Companion's Apply with the base resume, quick tailor's nothing-to-tailor result) runs no voice repair, so a third-person
base summary reaches the PDF: the health check flags it, and the fix belongs in the base resume.

Creation order matters (`services/tailoring_session.create_session`):
health-gate check first (cheap, 409 via `HealthGateBlockedError`), then ONE
engine run whose result both builds the gaps and stages the "before" score
(`score_target(..., result=...)`), then prior open sessions for the
(job, base) are marked superseded, then optional LLM gap enrichment (failure
swallowed → unenriched gaps), then ONE commit covering score row + supersede +
session row — a failure anywhere before it leaves no committed trace. A sub-55 health score sets a
transient `health_warning` on the create response (a toast in the web UI).
- **Quick tailor** (`POST /api/jobs/{job_id}/quick-tailor`): one-shot
  `quick_tailor.run_for_job` — guard (an open session with HAND-MADE
  resolutions 409s; system-planned autos don't count) → create_session →
  preference-driven auto-resolution (`plan_resolutions`; profile
  `quick_tailor_profile` at `GET/PUT /api/settings/quick-tailor`,
  autofill_profile storage pattern) → save_resolutions →
  tailor(user_prompt=profile instruction) → compare + render (each failure
  degrades the outcome — `compare:null` / `pdf_ready:false` — never fails the
  committed tailor). The jobs router is a thin adapter mapping typed
  exceptions to statuses. Honesty invariant preserved: absent-evidence
  keywords are only ever planned into skills. Zero actionable gaps → 200
  `nothing_to_tailor:true`, session left open. Rendering itself is
  `services/application_render.render_resume` (persists `render_error`, then
  re-raises; the applications router's render endpoint is its other adapter).


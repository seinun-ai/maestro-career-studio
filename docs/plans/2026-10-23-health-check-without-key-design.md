# Health check without a model key — design

Approved by the owner 2026-10-23. Goal: with no in-app AI key, a connected agent working over MCP gets a stored
health report that is honest about what was judged, and can judge the bullets itself by the app's own
criteria (`docs/health-check-rubric.md`, the `resume_bullet_classify` prompt, `RUBRIC_VERSION`).

## The problem

`POST /api/resume-lint/{kind}/{key}/run` returns 502 "No API key is set" whenever a bullet has no cached
judgment: `bullet_classify.classify_items` → `evaluate_uncached` → `llm.call_openai` has no fallback. The web
**Check** button fails the same way. `run_report(use_llm=False)` exists but nothing calls it, and it scores
0 / F on a sound resume (no levels → `compute_score([]) == 0`), which misleads.

## Owner decisions

- **Both paths.** A structure-only floor (no score or grade while bullets are unjudged) AND an agent-judged
  path that reaches a real grade.
- **Key wins.** With a key, the app's own model judges as today; the agent write path refuses (409). Without
  a key, any stored judgment at the current `RUBRIC_VERSION` counts, whoever made it, and the report names
  the judges.

## Backend

- **The run's judge.** Keyed (`llm.any_model_key_configured()`): unchanged. Keyless: no model call;
  `classify_items(..., stored_only=True)` returns overrides, disputes and cached rows at the current rubric
  version from ANY model; the rest are pending (absent from the result). `use_llm=False` now means "stored
  judgments only"; the default is "a key is configured".
- **Report fields.** `judged: {done, pending, by}` (by = the judges' model ids, sorted). While any scored
  bullet is pending, `score`, `grade` and `next_grade` are null and `score_breakdown` is absent. Gates
  S1–S5, C2, gap asks, wording and rule notes, and findings on judged bullets stay. C1 is computed only
  when every hot location is judged. `insufficient_evidence` counts every scored bullet, judged or pending;
  a finding's `gain` divides by that same count.
- **Already-degrading paths**: the verifier is skipped and rewrites become asks.
- **Tailoring guard**: the low-score warning skips a null score; the fatal-gate 409 is unchanged (gates
  are still computed).

## Agent path

- **The brief.** With no key and bullets pending, the run response carries
  `judging: {rubric_version, pending_ids, prompt}`, where `prompt` is `resume_bullet_classify` filled with
  the pending items — the exact text the in-app model would receive.
- **The write.** `POST /api/resume-lint/{kind}/{key}/judgments` `{judge, classifications}`; MCP
  `judge_health_bullets(kind, key, classifications)` sends the client's `clientInfo.name` as `judge`.
  Each entry must name a pending id and pass `bullet_classify._validate`; accepted entries are stored with
  `model = "agent:<client>"` (or `"agent"`), `rubric_version = RUBRIC_VERSION`. The report is rebuilt and
  returned with `accepted`, `rejected [{id, reason}]`, and `judging` while bullets remain pending.
  With a key: 409. Same profiles as `run_health_check`.
- **No `RUBRIC_VERSION` bump**: the prompt contract is unchanged.

## Web

`score`/`grade` nullable in `lib/types.ts`. Summary band: a "Not graded" tile and a line saying how many
bullets wait for judging and that a model key or a connected agent can judge them. Badges read "Not
graded"; the run-to-run delta is skipped when either side is ungraded; the toast reads "Check done.
Bullets not judged yet." An agent judge shows as "Bullets judged by Claude, a connected agent"
(`lib/agent-name.ts`).

## Out of scope

Disputes stay web-only and keyed. Today's "resumes to health check" does not list ungraded reports.

# AtsScore (`models/ats_score.py`)

> Reference tier, extracted from [SYSTEM.md](../../SYSTEM.md) (§4 Core entities). The header contract there governs this file too: integrate don't append, present tense, no dates outside the ledgers, update in the same change that alters the behaviour described.

`phase="base"` rows are **upsert singletons** per (job, target) — a partial
unique index enforces it; `phase="tailored"` rows **append** (history).
`compare()` backfills missing rows on demand and refuses to compare rows from
different engine/config versions (422 → UI offers re-score). The engine
(`services/ats/`) is deterministic and LLM-free — re-scoring is cheap; the
studio auto-rescores after every save→render chain. **Transaction ownership:**
`score_target` / `score_all_bases` commit only when they OWN the session
(callers passing one commit themselves — the ATS router does; `tailor()` and
`create_session` ride their own single commit). `compare` / `best_base` commit
exactly their backfill; never call them with staged caller state.

**"LLM-free" describes the ENGINE, not the pipeline.** `score_resume` is a
pure function of (resume_json, extracted_json, config), but `extracted_json`
is LLM output (`services/jd_extraction.py` → `prompts/extract_jd.txt`) frozen
before scoring; L6 and the per-skill semantic fallback use a pinned local
embedding model. Keep the LLM at that boundary: an in-engine "veto" of a bad
match is non-monotone (`l1_keyword` is `got/total`, so vetoing an unmatched
required row RAISES the score), and stable base→tailored deltas depend on the
engine being a pure function.

**Evidence tiers** (`placement_multipliers` + two feature-gated blocks in
`data/weights.yaml`): `dual` 1.5 > `experience_only` 1.0 > `extra_only` 0.8 >
`credential_only` 0.5 > `skills_list_only` = `undated_only` 0.4.
`certifications` index as undated `section="credential"` entries — never a
recency/tenure/recent-role signal, and `is_keyword_channel=True` so they
cannot corroborate the L5 stuffing lint. Education content is deliberately
NOT evidence: a presence bit in `l5_format` plus an ADVISORY `l4_gate` degree
warning (`services/ats/degrees.py`) outside the composite, because every ATS
platform surveyed enforces education via an application-form question.

**"Still in this role" is single-source** (`services/resume_dates`). The ATS
indexer and health gate S3 both call `resume_dates.is_open_ended`: a blank or
missing end date, or a whole-string current token, means the role is ongoing.
The tokens are `present`/`current`/`now`/`ongoing` plus `currently`/`to date`/
`till date`/`to present`, ordinary in UK and Indian CVs. Matching is
WHOLE-STRING: "Present" is current, "Present day rotation" is not.

**Readable-for-the-gate is not creditable-for-the-score.**
`health_zones.parse_ym` reads seasonal (`Summer 2022`), quarter (`Q3 2021`),
year-only and `YYYY-MM` dates; `ats/resume_indexer.parse_month_year`
deliberately does NOT — recency credit comes from precise months. The split
is the point: the gate must not call a correct academic or UK CV defective,
and the engine must not invent precision it does not have. Trap: `parse_ym`'s
month-name branch falls THROUGH on an unrecognized word instead of returning
None — an early return would shadow the season pattern.

**Rank markers are domain data.** The L3 title tier strips tokens that say how
senior a role is without changing WHAT it is. That vocabulary lives in
`role_categories.yaml`'s `seniority:` block ("add a domain, change no code"),
read by `role_categories.seniority_terms()` — never a hardcoded set in code (a
hardcoded set once missed `iv`, and how the employer spelled the level cost 10
composite points). **The block is TWO lists, because some rank words are also
head nouns.** `always:` is removed anywhere — "Senior", "IV" are never a job.
`prefix_only:` (`associate`, `principal`, `staff`, `lead`) is removed ONLY when
it leads the title — stripped in suffix position, "Tech Lead" reduces to "tech"
and the tier collapses to `none`. `_strip_seniority` runs phrases
longest-first, then always-tokens, then the prefix pass, and **never reduces to
an empty core** ("Senior Associate" keeps `associate`). `role_titles` applies
the same split so display labels and match cores cannot diverge. **Known limit,
deliberately unfixed:** "Associate Professor"/"Associate Director" are PREFIX
uses where the word IS the rank, so they still score a false `direct` — fixing
that needs per-domain packs; do not fake it with a special case. **Do not merge
this list with `role_titles._SENIORITY_PATTERN`** — they are different
concepts, NOT a subset relation. `role_titles` produces DISPLAY labels and may
strip management level too; the ENGINE may not:
`manager`/`director`/`head`/`vp` name a different job, and stripping them would
score an IC resume `direct` for a people-management JD. Management terms live
in `role_titles._MANAGEMENT_PATTERN`, composed on top of the shared vocabulary;
both directions are pinned in `tests/ats/test_layers.py`.

**Any input that can move a score must enter the `config_version` hash.**
`load_config` hashes an EXPLICIT dict (`weights`, `aliases`, `adjacency`,
`families`, `seniority`) — not the data directory — so a new YAML key must be
added by hand; left out, scores shift while the version stays fixed and
`compare()`'s guard waves through incomparable rows. Stored rows below the
current version are refused for comparison until re-scored (cheap by design).

**One placement-classification site** — `_select_placement`. The semantic
path's `classify()` DELEGATES to it with exactly one evidence flag set (so
`dual` stays impossible there); contract pinned in `tests/ats/test_layers.py`.
Ranking is by EFFECTIVE MULTIPLIER, not branch order or raw cosine — cosine
alone once let a certification line out-score the dated bullet.

**Containment is directional** (`matching.py`). Resume-more-specific
(`"apache spark"` covers JD `"Spark"`) keeps credit 1.0 as `fuzzy`;
JD-more-specific (`"aws"` against `"AWS SageMaker"`) returns `broader` at
`adjacency_max_credit` and routes to an adjacency gap (paying it 1.0 offered a
one-click add of the JD's literal product name). Vendor qualifiers and generic
modifier nouns are exempt (`"Microsoft Teams"` over `"teams"` is the same
skill; `"AWS Redshift"` over `"aws"` is not).

**Latin accents fold before lexical matching** (`matching.normalize_term`):
NFKD decomposition + combining-mark stripping make spelling variants
symmetric (`Zürich`/`Zurich`, `Nestlé`/`Nestle`) before the ASCII allowlist.
The punctuation contract is unchanged: `+`, `#`, `.`, `/` survive, `-`
becomes a space; non-Latin scripts normalize to empty (separate refusal
lane). Matching-behavior changes bump `ENGINE_VERSION` (scoring code), never
`config_version` (data only) — keep the two axes distinct.

`broader` is FALLBACK-grade: `resolve_evidence` defers it until the prose and
semantic stages miss, and it never earns a skills-list placement (never
`dual`) — left inline it short-circuits the semantic stage, so adding a true
skill would LOSE points. Stage order: lexical(full-credit) → prose → semantic
→ broader → adjacency.

**Monotonicity is the property that matters** — the composite is an ordinal
instrument, so a direction error beats an absolute-accuracy error. Adding
true evidence must never lower it: `scripts/ats_calibration.py monotonicity`
asserts this over the whole corpus; `tests/test_ats_monotonicity.py` pins it
hermetically. Two drops are CORRECT and excluded: padding the skills list
with an uncorroborated term (the L5 stuffing lint punishes that — also the
non-vacuity control), and diluting a dated entry's embedding with unrelated
prose.


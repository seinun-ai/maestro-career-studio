# FilledAnswer — the answer receipt (`models/filled_answer.py`)

> Reference tier, extracted from [SYSTEM.md](../../SYSTEM.md) (§4 Core entities). The header contract there governs this file too: integrate don't append, present tense, no dates outside the ledgers, update in the same change that alters the behaviour described.

One row per page run of a job's application form: `job_id`, `application_id` (nullable, linked
late), `channel` (`companion` | `agent`), `host`, `step` (a page number or the URL path),
`captured_at`, and `fields`, a list of `{question, section, required, answer, options_count,
source, slot, eeo, edited_by_you, eeo_answered, version}`. The values live here and nowhere else
(SYSTEM.md §6 `{#inv-filled-answers-local}`).

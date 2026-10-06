# Agent runs

> Reference tier, indexed from [SYSTEM.md](../../SYSTEM.md) §4. Its header contract governs this file too: integrate, present tense, no dated history, and update alongside the behavior described.

One `agent_runs` row records a finished automation run reported by the user's agent.
It feeds the Agent inbox's **Recent runs** panel and the Automations cards' **Last ran** line.
The model is `backend/app/models/agent_run.py`; the SQLite revision is `7d3c1a9e5b20`.

## Stored fields

| Field | Contract |
|---|---|
| `id` | UUID, generated on write. |
| `automation` | Card id (`mail-status`, `job-hunt`, `referral-pages`, `tailor-run`, `apply-session`) or a custom automation's own name; non-blank, input length 1–40 characters, whitespace stripped. |
| `outcome` | `ok`, `partial` or `failed`; the agent reports whether all, some or none of the work succeeded. |
| `agent` | Nullable raw MCP client name from the origin-detail header, only for an MCP origin; other HTTP writes store null. A display label, not authenticated identity. |
| `finished_at` | UTC time assigned when the record is written. There is no `started_at` or `created_at`; this is a completion record, not a live run tracker. |
| `counts` | JSON object, default `{}`. Known keys: `found`, `proposed`, `skipped`, `tailored`, `updated`, `needs_you`. Backend values are strict non-negative integers: booleans, strings and fractions are refused. |
| `digest` | Plain text, default `""`; whitespace stripped, capped at 2,000 characters. An over-long digest keeps its first 1,999 characters plus `…`, so the ellipsis fits the cap. |
| `job_ids` | JSON list, default `[]`. UUIDs de-duplicated in input order, first 50 distinct ids kept, then unknown ids dropped. Dropping unknowns does not refill the 50-id window. |

## Writing and retention

- **Run writes**: MCP `record_run(automation, outcome, report={counts?, digest?, job_ids?})`
  calls `POST /api/agent-runs` (201). `report` may be omitted or null; each report field also
  accepts null and is dropped by the MCP client, leaving the backend default. Empty objects,
  strings and lists are kept. The HTTP body is flat (`automation`, `outcome`, `counts`,
  `digest`, `job_ids`), not nested under `report`; explicit null values for these HTTP report
  fields are invalid. No web write UI, edit endpoint, delete endpoint, edit tool or delete
  tool exists. `record_run` is available in `full`, `hunt` and `apply` profiles.
- **Report validation**: the MCP `RunReport` and `RunCounts` schemas use `extra=forbid`;
  unknown report or count keys are refused before an HTTP call. The backend also refuses
  unknown body or count keys with 422 (`schemas/agent_runs.py`). Invalid UUIDs and outcomes
  are refused; long digests and job lists are trimmed instead of losing the run.
- **Retention**: at most 200 rows, pruned on each write (`services/agent_runs.py`). A new run
  is never pruned by its own write, even if older rows have future timestamps: keep it plus
  the newest 199 other rows, ordered by `finished_at` descending then UUID descending.

## Reading and prompts

- **Run reads**: `GET /api/agent-runs?limit=` returns newest first (default 20, range 1–200);
  `GET /api/agent-runs/latest` returns one newest retained run per automation, newest first.
  Both return `{items: [...]}`. `title` is resolved at read time from the catalog, or falls
  back to the custom name. Reads return `jobs` with id/title/company rather than `job_ids`;
  a job deleted since recording is omitted. There is no MCP read tool for the run log.
- **Recent runs**: one expandable line per automation shows its title, relative finish time,
  agent label, outcome and counts; expanding shows the digest and job links. Outcomes read
  **Done**, **Partly done**, **Failed**. Counts have a fixed order and omit zeros; all-zero
  counts read **Nothing to report**. The empty state is **No runs yet. Set one up on
  Automations.** A failed read says **Couldn't load recent runs.**
- **Automations cards**: a successful latest-runs read shows **Last ran** plus relative time,
  or **Not run yet** when that automation has no retained record. When the read never
  produced data, no line appears. A failed background refetch keeps the cached Last ran
  line; it does not erase the last known time.
- **Automation prompts**: each of the five run prompts ends with `record_run`;
  `customize-job-skills` tells custom automations to record under their own name. `job-hunt`
  saves jobs with `source='agent'` and the posting's `source_url`. Newly hunted jobs therefore
  pass through the existing open-proposal gate for execute helpers, like `referral-pages`
  jobs; `find_job_by_url` can recognize jobs saved by earlier hunts.
- **Mail-status digest**: `report.digest` is a separate short version written for Maestro:
  counts and company-and-role lines only, never email text (no subjects, senders or bodies).
  Unmatched emails appear only in `counts.skipped`. The digest shown to the user is unchanged.

## Limits for phase 4

- **Readiness PDF mark**: `tailored` is `bool(pdf_path)` on the linked application, not a
  check that the file is on disk. Auto-submit must check the file before uploading it.
- **Readiness knock-out mark**: only a scan with status `conflict` contributes a knock-out;
  `incomplete_profile` and `warning` checks count as no knock-out, as do `clear` and
  `unstated`. Readiness alone therefore does not establish a complete or passing profile.
- **Readiness country mark**: `base_country` is set when the linked application's base resume
  lists countries that exclude the job's, and a set mark is not ready. A job with no known
  country, no application, or no eligible base at all (the fallback) carries none.
  The full rule lives in `inbox_readiness.is_ready`; see [proposals](others.md).
- **Run digest**: unverified agent text. The mail-status prompt forbids copying email text,
  but Maestro cannot verify that the digest obeys it or that its account of the run is true.
- **Run timing**: there is no overdue logic or scheduler; Maestro does not know the user's
  schedule. A run that crashes before recording leaves the previous time. An absent record
  cannot distinguish an automation never run from one whose record was pruned.

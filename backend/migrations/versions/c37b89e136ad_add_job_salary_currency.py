"""add job salary_currency and salary_source_url; resync extract_jd

Revision ID: c37b89e136ad
Revises: 0d9eb8e7abd8
Create Date: 2026-08-06

Nullable currency + optional pay-page URL. Existing salary numbers keep their
values; rows that already have a salary amount but no currency are backfilled
from HOME_CURRENCY (default USD) so analytics are not left with ambiguous
bare numbers. Do not hard-code USD in the SQL — read the env at upgrade time.

Also re-syncs an *untouched* `prompt.extract_jd` settings row to the new file
default (day/week periods, salary_currency, salary_source_url, null-pay-is-
normal rules). Customized rows are left alone.
"""

from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c37b89e136ad"
down_revision: Union[str, Sequence[str], None] = "0d9eb8e7abd8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_EXTRACT_JD = """Extract structured job-description data from the raw posting below.

Return ONLY valid JSON with this shape:
{
  "company": "<company or null>",
  "title": "<job title or null>",
  "role_category": "<$role_options>",
  "level": "<intern|entry|mid|senior|lead|unknown>",
  "employment_type": "<full_time|part_time|contract|internship|unknown>",
  "work_mode": "<remote|hybrid|onsite|unknown>",
  "city": "<city name or null>",
  "state": "<2-letter US state code if US, full state/region name otherwise, or null>",
  "country": "<ISO 3166-1 alpha-2 code (e.g. US, CA, GB) or null>",
  "requisition_id": "<the posting's requisition/job ID (e.g. R-12345, JR0087, 7381794002) or null>",
  "location_raw": "<original location string verbatim, or null>",
  "salary_min": <number or null>,
  "salary_max": <number or null>,
  "salary_period": "<hour|year|month|unknown|null>",
  "work_authorization": "<sponsorship_available|no_sponsorship|citizen_or_gc_required|unstated>",
  "opt_accepted": "<yes|stem_opt_ok|no|unstated>",
  "years_experience_min": <integer or null>,
  "years_experience_max": <integer or null>,
  "skills": [
    {
      "skill_name": "<specific skill>",
      "skill_category": "<language|framework|cloud|database|tool|methodology|domain|certification|other>",
      "requirement_level": "<required|preferred|mentioned>"
    }
  ],
  "responsibilities": ["<short responsibility>"],
  "qualifications": ["<short qualification>"]
}

Rules:
- Normalize obvious synonyms, but preserve concrete tool names exactly.
- Extract only skills actually present in the job description.
- Use null for missing scalar fields.
- `requisition_id`: the ATS requisition/job identifier when the posting shows one (Workday "R-12345"/"JR…", Greenhouse/Lever numeric or slug ids, "Req ID", "Job ID", "Requisition Number"). Copy it verbatim. Use null when the posting names none. Never invent or derive one.
- `location_raw` must preserve the original location phrase verbatim (e.g. "Austin, TX (Hybrid)"); `city`/`state`/`country` are best-effort parses, null when ambiguous.
- `work_authorization`: use `no_sponsorship` when the posting says sponsorship is not provided — e.g. "no sponsorship", "will not sponsor", "unable to sponsor", "we do not provide sponsorship now or in the future", "must be authorized to work in the US without sponsorship"; `citizen_or_gc_required` when US citizenship, a green card, a security clearance, or US-person status is required — e.g. "US citizens only", "US citizenship required", "active security clearance required", "must be a US person"; `sponsorship_available` when visa sponsorship is explicitly offered; otherwise `unstated`. Do not infer `citizen_or_gc_required` from inclusive language like "US citizens are encouraged to apply".
- `opt_accepted`: `yes` if any OPT is acceptable, `stem_opt_ok` if only STEM OPT is mentioned as acceptable, `no` if OPT is explicitly excluded; otherwise `unstated`.
- `years_experience_min`/`max`: extract from phrases like "3-5 years" (min=3, max=5) or "5+ years" (min=5, max=null) or "minimum 7 years" (min=7, max=null). Use null when unstated.
- Named certifications, licenses and clearances are skills: emit each as a skills row with `skill_category` "certification" and the FULL official name in `skill_name` (e.g. "AWS Certified Solutions Architect - Associate", not "SAA-C03" and not "AWS cert"). Emit one ONLY when the posting names it; never infer a certification from seniority, role type or the tools mentioned. Most postings name none — an empty result is correct.
- Degree and education requirements are NOT skills. Leave them in `qualifications` verbatim (e.g. "MS in Computer Science required"); do not turn them into skills rows.
- Return a single JSON object. No markdown fences.

RAW JOB DESCRIPTION:
${raw_jd}
"""

NEW_EXTRACT_JD = """Extract structured job-description data from the raw posting below.

Return ONLY valid JSON with this shape:
{
  "company": "<company or null>",
  "title": "<job title or null>",
  "role_category": "<$role_options>",
  "level": "<intern|entry|mid|senior|lead|unknown>",
  "employment_type": "<full_time|part_time|contract|internship|unknown>",
  "work_mode": "<remote|hybrid|onsite|unknown>",
  "city": "<city name or null>",
  "state": "<2-letter US state code if US, full state/region name otherwise, or null>",
  "country": "<ISO 3166-1 alpha-2 code (e.g. US, CA, GB) or null>",
  "requisition_id": "<the posting's requisition/job ID (e.g. R-12345, JR0087, 7381794002) or null>",
  "location_raw": "<original location string verbatim, or null>",
  "salary_min": <number or null>,
  "salary_max": <number or null>,
  "salary_period": "<hour|day|week|month|year|unknown|null>",
  "salary_currency": "<ISO 4217 code (USD, GBP, EUR, INR, …) or null>",
  "salary_source_url": "<URL of a linked pay-scale/benefits page when the posting hyperlinks pay instead of stating numbers, else null>",
  "work_authorization": "<sponsorship_available|no_sponsorship|citizen_or_gc_required|unstated>",
  "opt_accepted": "<yes|stem_opt_ok|no|unstated>",
  "years_experience_min": <integer or null>,
  "years_experience_max": <integer or null>,
  "skills": [
    {
      "skill_name": "<specific skill>",
      "skill_category": "<language|framework|cloud|database|tool|methodology|domain|certification|other>",
      "requirement_level": "<required|preferred|mentioned>"
    }
  ],
  "responsibilities": ["<short responsibility>"],
  "qualifications": ["<short qualification>"]
}

Rules:
- Normalize obvious synonyms, but preserve concrete tool names exactly.
- Extract only skills actually present in the job description.
- Use null for missing scalar fields.
- `requisition_id`: the ATS requisition/job identifier when the posting shows one (Workday "R-12345"/"JR…", Greenhouse/Lever numeric or slug ids, "Req ID", "Job ID", "Requisition Number"). Copy it verbatim. Use null when the posting names none. Never invent or derive one.
- `location_raw` must preserve the original location phrase verbatim (e.g. "Austin, TX (Hybrid)"); `city`/`state`/`country` are best-effort parses, null when ambiguous.
- Salary is OPTIONAL. Most postings state no pay at all (~40%+ of US, ~88% of German). A null `salary_min`/`salary_max` is the correct, complete answer — never invent numbers, never treat absence as a failure. When the posting only hyperlinks a publicly viewable pay-scale/benefits page (common under Illinois 820 ILCS 112/10(b-25)), set `salary_source_url` to that URL and leave min/max null.
- `salary_currency`: ISO 4217 from the posting's stated currency or unambiguous symbol (£→GBP, €→EUR, $ alone is ambiguous across countries — prefer null over guessing when the country is not US). Null when there is no salary amount. Never invent a currency for a null salary.
- `salary_period`: include `day` and `week` for contractor day/week rates (UK/EU). Use `hour`/`month`/`year` when those are stated.
- `work_authorization`: use `no_sponsorship` when the posting says sponsorship is not provided — e.g. "no sponsorship", "will not sponsor", "unable to sponsor", "we do not provide sponsorship now or in the future", "must be authorized to work in the US without sponsorship"; `citizen_or_gc_required` when US citizenship, a green card, a security clearance, or US-person status is required — e.g. "US citizens only", "US citizenship required", "active security clearance required", "must be a US person"; `sponsorship_available` when visa sponsorship is explicitly offered; otherwise `unstated`. Do not infer `citizen_or_gc_required` from inclusive language like "US citizens are encouraged to apply".
- `opt_accepted`: `yes` if any OPT is acceptable, `stem_opt_ok` if only STEM OPT is mentioned as acceptable, `no` if OPT is explicitly excluded; otherwise `unstated`.
- `years_experience_min`/`max`: extract from phrases like "3-5 years" (min=3, max=5) or "5+ years" (min=5, max=null) or "minimum 7 years" (min=7, max=null). Use null when unstated.
- Named certifications, licenses and clearances are skills: emit each as a skills row with `skill_category` "certification" and the FULL official name in `skill_name` (e.g. "AWS Certified Solutions Architect - Associate", not "SAA-C03" and not "AWS cert"). Emit one ONLY when the posting names it; never infer a certification from seniority, role type or the tools mentioned. Most postings name none — an empty result is correct.
- Degree and education requirements are NOT skills. Leave them in `qualifications` verbatim (e.g. "MS in Computer Science required"); do not turn them into skills rows.
- Return a single JSON object. No markdown fences.

RAW JOB DESCRIPTION:
${raw_jd}
"""


def upgrade() -> None:
    op.add_column("jobs", sa.Column("salary_currency", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("salary_source_url", sa.Text(), nullable=True))

    home = (os.environ.get("HOME_CURRENCY") or "USD").strip().upper() or "USD"
    op.execute(
        sa.text(
            "UPDATE jobs SET salary_currency = :home "
            "WHERE salary_currency IS NULL "
            "AND (salary_min IS NOT NULL OR salary_max IS NOT NULL)"
        ).bindparams(home=home)
    )

    # Re-sync only if the stored prompt still matches the pre-edit default.
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT value FROM settings WHERE key = 'prompt.extract_jd'")
    ).fetchone()
    if row is not None and row[0] == OLD_EXTRACT_JD:
        conn.execute(
            sa.text(
                "UPDATE settings SET value = :new WHERE key = 'prompt.extract_jd'"
            ).bindparams(new=NEW_EXTRACT_JD)
        )


def downgrade() -> None:
    # Prompt resync is intentionally not reversed (same as d4e5f6a7b8c9).
    op.drop_column("jobs", "salary_source_url")
    op.drop_column("jobs", "salary_currency")

"""re-sync an untouched qa prompt row; drop the orphaned cold_message prompt row

Prompt rows (`settings` key `prompt.<key>`) seed once and then shadow the
prompt FILE forever (see d4e5f6a7b8c9 for the precedent and full rationale).
The 2026-07-21 cold-message removal (design doc Item 1) added
`${referral_section}` and the anti-fabrication rule to qa.txt — without this
resync no already-seeded environment ever sees them (safe_substitute silently
drops the unknown placeholder in old rows). Only an untouched row (value ==
pre-edit file default, captured below via
`git show 3afd17a:backend/app/prompts/qa.txt`) is replaced.

This branch also deletes prompts/cold_message.txt and removes `cold_message`
from VALID_PROMPTS; the stale `prompt.cold_message` settings row is dropped
here so it does not linger orphaned.

downgrade() is a no-op (same reasoning as d4e5f6a7b8c9).

Revision ID: 14133e25da5f
Revises: e92b791871d1
Create Date: 2026-07-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "14133e25da5f"
down_revision: Union[str, Sequence[str], None] = "e92b791871d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_QA = """Answer these job application questions based on the resume, job description, and memory below.

RESUME JSON:
${resume_json}

JOB DESCRIPTION JSON:
${jd_json}

MEMORY:
${memory}

QUESTIONS:
${questions}

For each question:
- Be specific and reference real experience from the resume.
- Tailor the answer to the job description.
- Keep answers concise but substantive.
- For years-of-experience questions, derive from resume dates.
- For why-this-role questions, connect resume experience to JD requirements.

Return answers numbered to match the questions above.
"""


def upgrade() -> None:
    from app.services import prompts

    bind = op.get_bind()
    row = bind.execute(
        sa.text("SELECT value FROM settings WHERE key = 'prompt.qa'")
    ).first()
    if row is not None and row[0] == OLD_QA:
        new = (prompts.PROMPT_DIR / "qa.txt").read_text(encoding="utf-8")
        bind.execute(
            sa.text("UPDATE settings SET value = :v WHERE key = 'prompt.qa'"),
            {"v": new},
        )
    bind.execute(sa.text("DELETE FROM settings WHERE key = 'prompt.cold_message'"))


def downgrade() -> None:
    # No-op: see module docstring.
    pass

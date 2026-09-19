"""drop the orphaned extract_jd_fields prompt row

SYSTEM.md §13 row `jd-fields-chain`, cut 2026-08-02: the reduced-prompt
backfill chain (extract_jd_fields / merge_jd_fields / JobFieldsExtraction /
scripts/backfill_jd_fields.py) is deleted — `POST /jobs/{id}/re-extract`
superseded it and `jobs.work_authorization` has zero NULLs. Prompt rows
(`settings` key `prompt.<key>`) seed once and then shadow the prompt FILE
forever (see 14133e25da5f for the precedent), so the stale
`prompt.extract_jd_fields` row is dropped here rather than left orphaned.

downgrade() is a no-op (same reasoning as 14133e25da5f: the seeded value is
regenerable from the deleted file's git history if ever needed).

Revision ID: be7f98929817
Revises: 103c6edd3352
Create Date: 2026-08-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "be7f98929817"
down_revision: Union[str, Sequence[str], None] = "103c6edd3352"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text("DELETE FROM settings WHERE key = 'prompt.extract_jd_fields'")
    )


def downgrade() -> None:
    pass

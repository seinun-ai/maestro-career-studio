"""drop the frozen master base resume and the legacy memory blob

SYSTEM.md §13 rows `master-base-resume` and `memory-blob-store`, cut
2026-08-03. Both were pre-Career-KB storage kept frozen as backups after the
2026-07-15 KB migration; the KB has been the source of truth since, and
`kb.seeded` is set.

Deleting the `master` ROW here is load-bearing, not cosmetic: the ~10
reserved-slug guards that kept it out of lists, chat, analytics and tailoring
are deleted in the same commit. A surviving row with no guards would
un-freeze the retired profile back into every one of those surfaces.

The memory blob was reconciled into `kb_profile.notes` / `kb_entities.notes`
by the one-time seed. Both blobs were archived outside the app before this
landed (see the row notes in the deleting commit).

`prompt.kb_memory_reconcile` is dropped for the reason in be7f98929817:
prompt rows seed once and then shadow the prompt FILE forever, so a stale row
whose file is gone would keep shadowing nothing.

downgrade() is a no-op — the deleted content is user data held in an external
archive, not something a migration can regenerate.

Revision ID: aa323ad849bf
Revises: be7f98929817
Create Date: 2026-08-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "aa323ad849bf"
down_revision: Union[str, Sequence[str], None] = "be7f98929817"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM resume_versions "
            "WHERE resume_kind = 'base' AND resume_key = 'master'"
        )
    )
    op.execute(sa.text("DELETE FROM base_resumes WHERE slug = 'master'"))
    op.execute(
        sa.text(
            "DELETE FROM settings "
            "WHERE key IN ('memory', 'prompt.kb_memory_reconcile')"
        )
    )


def downgrade() -> None:
    pass

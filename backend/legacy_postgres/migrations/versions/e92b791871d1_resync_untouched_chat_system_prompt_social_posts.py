"""re-sync an untouched chat_system prompt row after the social-posts edit

Prompt rows (`settings` key `prompt.<key>`) seed once and then shadow the
prompt FILE forever (see d4e5f6a7b8c9 / 86ac8658395f for the precedent).
The 2026-07-21 edit appended the "Writing social posts" section
(get_career_context grounding, LinkedIn conventions, single-block output) —
without this resync no already-seeded environment ever sees it.

Matches the stored row against the sha256 of EVERY previously shipped file
default; only an untouched row is replaced — user customizations are never
overwritten.

  (carried forward from 86ac8658395f)
  3100d1c5dcae031e5c34a9a188650848b4e6cee4c37805546f7a9595c62e58ee
  74417c4c11738cba476d307a2b3fc93829c15118a76c14ed448678ed5627941b
  71555263645431168d38a20946a8661cdd4770fb24084de4fd4fb41eea9057c4
  (file default immediately before this edit)
  ff5f9b1e14d989d5ce93219395415b75bab303e8bc51ea7f64f8d591f1590eb0

downgrade() is a no-op (same reasoning as d4e5f6a7b8c9).

Revision ID: e92b791871d1
Revises: 86ac8658395f
Create Date: 2026-07-21
"""
import hashlib
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e92b791871d1"
down_revision: Union[str, Sequence[str], None] = "86ac8658395f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_DEFAULT_SHA256 = {
    "3100d1c5dcae031e5c34a9a188650848b4e6cee4c37805546f7a9595c62e58ee",
    "74417c4c11738cba476d307a2b3fc93829c15118a76c14ed448678ed5627941b",
    "71555263645431168d38a20946a8661cdd4770fb24084de4fd4fb41eea9057c4",
    "ff5f9b1e14d989d5ce93219395415b75bab303e8bc51ea7f64f8d591f1590eb0",
}


def upgrade() -> None:
    from app.services import prompts

    bind = op.get_bind()
    row = bind.execute(
        sa.text("SELECT value FROM settings WHERE key = 'prompt.chat_system'")
    ).first()
    if row is None:
        return  # no row yet: get_prompt lazy-seeds the current file default
    digest = hashlib.sha256(row[0].encode("utf-8")).hexdigest()
    if digest in _OLD_DEFAULT_SHA256:
        new = (prompts.PROMPT_DIR / "chat_system.txt").read_text(encoding="utf-8")
        bind.execute(
            sa.text("UPDATE settings SET value = :v WHERE key = 'prompt.chat_system'"),
            {"v": new},
        )


def downgrade() -> None:
    # No-op: see module docstring.
    pass

"""re-sync an untouched chat_system prompt row to the current file default

Prompt rows (`settings` key `prompt.<key>`) seed once and then shadow the
prompt FILE forever (see d4e5f6a7b8c9 for the precedent and full rationale).
The 2026-07-17 chat interaction upgrade rewrote chat_system.txt (propose_edits
suggestions rule, KB-pin guidance, analytics tools, markdown) — without this
resync no already-seeded environment ever sees those rules, and the old row
actively instructs auto-apply, suppressing the new approval-card behavior.

Matches the stored row against the sha256 of EVERY previously shipped file
default (the row may predate earlier un-resynced edits too); only an
untouched row is replaced — user customizations are never overwritten.

  e0661e1 3100d1c5dcae031e5c34a9a188650848b4e6cee4c37805546f7a9595c62e58ee
  4419284 74417c4c11738cba476d307a2b3fc93829c15118a76c14ed448678ed5627941b
  bdad119 71555263645431168d38a20946a8661cdd4770fb24084de4fd4fb41eea9057c4

downgrade() is a no-op (same reasoning as d4e5f6a7b8c9).

Revision ID: 86ac8658395f
Revises: 53855dff79bc
Create Date: 2026-07-17
"""
import hashlib
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "86ac8658395f"
down_revision: Union[str, Sequence[str], None] = "53855dff79bc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_DEFAULT_SHA256 = {
    "3100d1c5dcae031e5c34a9a188650848b4e6cee4c37805546f7a9595c62e58ee",
    "74417c4c11738cba476d307a2b3fc93829c15118a76c14ed448678ed5627941b",
    "71555263645431168d38a20946a8661cdd4770fb24084de4fd4fb41eea9057c4",
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

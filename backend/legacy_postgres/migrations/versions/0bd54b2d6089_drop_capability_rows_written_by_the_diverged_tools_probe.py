"""drop capability rows the old tools probe measured with the wrong call

`llm_capabilities._probe_tools` used to build its own
`chat.completions.create` call instead of the one `chat_agent.run_turn` makes.
Two kinds of row came out wrong:

  * a gpt-5.6 model 400s on function tools unless `reasoning_effort="none"`,
    which the chat agent sends and the probe did not — so a model whose chat
    works was stored as tools=False, and `chat.require` then 422'd every
    message. Signature: "reasoning_effort" in the tools error.
  * a Gemini model id went to the OpenAI client (Gemini inference goes over
    `llm._call_gemini`), so the row said the model "does not exist". The
    verdict was right, the reason was not.

A stored row shadows the probe forever, so the code fix alone leaves the false
No in place. Deleting is safe: `llm_capabilities.require` lets an UNPROBED
model through, and Settings shows "Not tested" with a Test button. Only rows
carrying a bug signature go — a genuine measured No (a local 3B that really
cannot call tools) is left alone.

downgrade() is a no-op: the rows are a cache of a measurement, and re-probing
is the only thing that can restore them honestly.

Revision ID: 0bd54b2d6089
Revises: 9c0e9f35864f
Create Date: 2026-08-13
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0bd54b2d6089"
down_revision: Union[str, Sequence[str], None] = "9c0e9f35864f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PREFIX = "llm.capabilities."


def _was_measured_by_the_broken_probe(key: str, value: str | None) -> bool:
    model = key[len(_PREFIX) :]
    if model.removeprefix("models/").startswith("gemini-"):
        return True
    try:
        report = json.loads(value or "")
    except json.JSONDecodeError:
        return False
    return "reasoning_effort" in (report.get("errors") or {}).get("tools", "")


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT key, value FROM settings WHERE key LIKE :prefix"),
        {"prefix": f"{_PREFIX}%"},
    ).fetchall()
    stale = [key for key, value in rows if _was_measured_by_the_broken_probe(key, value)]
    if stale:
        bind.execute(
            sa.text("DELETE FROM settings WHERE key = ANY(:keys)"), {"keys": stale}
        )


def downgrade() -> None:
    pass

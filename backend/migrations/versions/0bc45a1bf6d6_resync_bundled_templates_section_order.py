"""resync untouched bundled templates for the section_order knob

Seeded template rows override their files, so a template change reaches existing
installs only through a migration, and only when the stored source still matches
the exact previous bundle. Customized rows remain untouched (they keep rendering
in their own fixed order, which is what their author asked for). Resynced parse
evidence describes the old source and must be cleared for lazy re-certification.

Also seeds harshibar's explicit `default_formatting.section_order`. That row's
`default_formatting` is user-editable, so it is only written when the row has no
`section_order` of its own.

Revision ID: 0bc45a1bf6d6
Revises: c84a19d2e7f0
Create Date: 2026-08-14
"""
import hashlib
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0bc45a1bf6d6"
down_revision: Union[str, Sequence[str], None] = "c84a19d2e7f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# sha256 of each bundled source as it stood BEFORE the section_order refactor.
_OLD_TEMPLATE_SOURCES: dict[str, tuple[str, str]] = {
    "default": (
        "resume.tex.j2",
        "1a7350623f5d5a005eb66f91986c54819da18885444a09b357a2695ded647aaf",
    ),
    "typst-classic": (
        "typst_classic.typ",
        "38629f95698a1873fcc8d4383680d595e804f7a9c604e29c25916f8bdc0b6767",
    ),
    "xcharter_serif": (
        "user/xcharter_serif.tex.j2",
        "6fbbb40605eaefd3994104866540dc297a827292edcb955709db05f637a7f979",
    ),
    "xcharter_serif_typst": (
        "user/xcharter_serif.typ",
        "a7b7253c50466d05938c55ecb5d99123028a8846094b084620144b85aaee81bf",
    ),
    "carlito_dense": (
        "user/carlito_dense.tex.j2",
        "32a6aef985681c89664187cfc70c53de0f642e53335574ec541e3ce894b9af20",
    ),
    "harshibar": (
        "user/harshibar.tex.j2",
        "b3dc762c7e52b134cc39f98d584eeef329086673045c51efcb0a460a0813498f",
    ),
}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _resync(bind: sa.engine.Connection) -> None:
    """Replace only unchanged bundled source rows with their current files."""
    from app.services import pdf_render

    for template_id, (filename, old_hash) in _OLD_TEMPLATE_SOURCES.items():
        row = bind.execute(
            sa.text("SELECT source FROM templates WHERE id = :template_id"),
            {"template_id": template_id},
        ).first()
        if row is None or _sha256(row[0]) != old_hash:
            continue
        source = (pdf_render.TEMPLATE_DIR / filename).read_text(encoding="utf-8")
        bind.execute(
            sa.text(
                "UPDATE templates SET source = :source, parse_certified = NULL, "
                "parse_report_json = NULL, validated_at = NULL WHERE id = :template_id"
            ),
            {"source": source, "template_id": template_id},
        )


def _seed_harshibar_order(bind: sa.engine.Connection) -> None:
    """Give the harshibar row its native order, without clobbering a user's."""
    from app.services.template_registry import HARSHIBAR_DEFAULT_FORMATTING

    row = bind.execute(
        sa.text("SELECT default_formatting FROM templates WHERE id = 'harshibar'")
    ).first()
    if row is None:
        return
    stored = row[0]
    if isinstance(stored, str):  # a JSON (not JSONB) column round-trips as text
        stored = json.loads(stored)
    stored = dict(stored or {})
    if "section_order" in stored:
        return
    stored.update(HARSHIBAR_DEFAULT_FORMATTING)
    bind.execute(
        sa.text(
            "UPDATE templates SET default_formatting = :formatting "
            "WHERE id = 'harshibar'"
        ),
        {"formatting": json.dumps(stored)},
    )


def upgrade() -> None:
    bind = op.get_bind()
    _resync(bind)
    _seed_harshibar_order(bind)


def downgrade() -> None:
    pass

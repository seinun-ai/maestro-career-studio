"""resync untouched bundled templates for ongoing-role Present dates

Seeded template rows override their files, so this update reaches existing
installs only when the stored source still matches the exact base default.
Customized rows remain untouched. Resynced parse evidence describes the old
source and must be cleared for lazy re-certification.

Revision ID: c84a19d2e7f0
Revises: 0bd54b2d6089
Create Date: 2026-08-13
"""
import hashlib
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c84a19d2e7f0"
down_revision: Union[str, Sequence[str], None] = "0bd54b2d6089"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_TEMPLATE_SOURCES: dict[str, tuple[str, str]] = {
    "default": (
        "resume.tex.j2",
        "0657e3937030a7ff6b2f9d5cdb9f80ad12578defeaff2c67f83fc8d7af6dc3d6",
    ),
    "typst-classic": (
        "typst_classic.typ",
        "2adc943ffc6937b33014bec9a7646022a0c9ed5e22b38ecdce849565da427c76",
    ),
    "xcharter_serif": (
        "user/xcharter_serif.tex.j2",
        "3b69c685a8f9ca528886432fc16a71bd36b4ae3720cd39f99b8f306915aae0a6",
    ),
    "xcharter_serif_typst": (
        "user/xcharter_serif.typ",
        "2d719b919988f2d59bd42048853413fb84d6b2a7dcdf07c3c6827f3eed2c23cd",
    ),
    "carlito_dense": (
        "user/carlito_dense.tex.j2",
        "a7de33995feedd47bf8021b9ab89d3c74614477ce7d20c1c22a6f7692b55f29b",
    ),
    "harshibar": (
        "user/harshibar.tex.j2",
        "a676b9f7f9a44fb8e3f77fc1c5beddc419ff3efff24fff452e3d85a45ed3c546",
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


def upgrade() -> None:
    _resync(op.get_bind())


def downgrade() -> None:
    pass

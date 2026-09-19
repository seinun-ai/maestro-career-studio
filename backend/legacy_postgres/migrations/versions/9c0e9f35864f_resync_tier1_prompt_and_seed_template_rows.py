"""re-sync untouched prompt rows AND seed-template sources for the Tier 1 round

Two prompt rows and two seed-template rows were superseded on disk this round;
none of the four reaches an already-seeded install without a resync, because a
stored row always beats its file (prompts: see 86ac8658395f / d4e5f6a7b8c9;
templates: `ensure_seed_templates` inserts only when the row is MISSING, so an
existing `default` / `typst-classic` row keeps its old source forever).

- `prompt.kb_resume_parse`: extras-aware parsing (extra_sections routing,
  optional start_date/degree) — without the resync, uploaded resumes keep
  losing Publications/Licenses/Volunteer content on seeded installs.
- `prompt.chat_system`: the Typst data-contract bullet.
- templates `default` + `typst-classic`: render guards for undated experience
  and degree-less education entries.

Untouched-row rule, same as every prompt resync: a row is replaced ONLY when
its current content sha256-matches a PREVIOUSLY SHIPPED default (every one in
this repo's history), so user customizations are never overwritten. A resynced
template row also gets parse_certified/parse_report_json/validated_at cleared —
the certification belongs to the OLD source, and structure_gates re-certifies
lazily on the next health run (a gate you didn't run is not a gate you passed).

downgrade() is a no-op (see d4e5f6a7b8c9).

Revision ID: 9c0e9f35864f
Revises: 8ba1429dca29
Create Date: 2026-08-12
"""
import hashlib
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9c0e9f35864f"
down_revision: Union[str, Sequence[str], None] = "8ba1429dca29"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# sha256 of every previously shipped default, from `git log -- <file>`
# (current texts deliberately excluded — matching them would be a no-op anyway).
_OLD_PROMPT_DEFAULTS: dict[str, tuple[str, set[str]]] = {
    "prompt.kb_resume_parse": (
        "kb_resume_parse.txt",
        {
            "0df967ed4ffb5794d9f95826cc51531faa85e6ce4a0494c863b1b1f453eb9a0a",
        },
    ),
    "prompt.chat_system": (
        "chat_system.txt",
        {
            "3100d1c5dcae031e5c34a9a188650848b4e6cee4c37805546f7a9595c62e58ee",
            "3159ecb858e2769b44eefe995bcd493836074f3e36322ca1acd94bb305f26358",
            "34107f01f07862921e522f93b5cdef0134152f88f61a7836ac140e4e4b04ea3e",
            "4b5407482ee040e69ced2e5bb302ffe8b0da986f53e0dfe4f8c8766727c8238b",
            "71555263645431168d38a20946a8661cdd4770fb24084de4fd4fb41eea9057c4",
            "74417c4c11738cba476d307a2b3fc93829c15118a76c14ed448678ed5627941b",
            "a5b5b3082972c4e90a45cad97076d88bd72d9e41e540c00041d8e48c427a0649",
            "ff5f9b1e14d989d5ce93219395415b75bab303e8bc51ea7f64f8d591f1590eb0",
        },
    ),
}

_OLD_TEMPLATE_SOURCES: dict[str, tuple[str, set[str]]] = {
    "default": (
        "resume.tex.j2",
        {
            "2fb24ac236c54bdf81b07ccdc67fc74999516d9b44325fde08117264f515ad1a",
            "5cf032c7f930a2526c30f7cab72ba482ccd422f9ae845fbace599e5955157f7e",
            "9d7c3ec8ba7903412fafd1b81c0792c6b00021767ab5bb5cc565063cfd3871bf",
            "abba04679c464b623c5c31e27f1d8518f3cce94476739def18c16b12451764de",
            "bf63dc937871049272a2c7d70264b53eb115d184ef24060a1160df91dc20ca05",
            "e7ad60a02fe34a24f30611a26ff9ae8f3b46565e86d8e89938837f089d42857f",
            "eb8f3b2d5b09125776f6c95c01757c73899602d255f495cc38167d61efc4a6ea",
            "f8a50d30986905bc27e3b33cde87012224cb21168532e9134d464cc63e4fd33b",
        },
    ),
    "typst-classic": (
        "typst_classic.typ",
        {
            "355f2c4ebed0cbbc928a4006dfbd94fbd77e2d8b37f40e436aebe64b9bfdce48",
            "d40c093d066067d58edb1540b54b6cbc0c57822ff8de2c9e05763fcb0e925841",
        },
    ),
}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _resync(bind: sa.engine.Connection) -> None:
    """Testable core: replace untouched rows with the current file defaults."""
    from app.services import prompts

    template_dir = prompts.PROMPT_DIR.parent / "templates"

    for key, (filename, old_hashes) in _OLD_PROMPT_DEFAULTS.items():
        row = bind.execute(
            sa.text("SELECT value FROM settings WHERE key = :k"), {"k": key}
        ).first()
        if row is None:
            continue  # no row yet: get_prompt lazy-seeds the current file default
        if _sha256(row[0]) in old_hashes:
            new = (prompts.PROMPT_DIR / filename).read_text(encoding="utf-8")
            bind.execute(
                sa.text("UPDATE settings SET value = :v WHERE key = :k"),
                {"v": new, "k": key},
            )

    for template_id, (filename, old_hashes) in _OLD_TEMPLATE_SOURCES.items():
        row = bind.execute(
            sa.text("SELECT source FROM templates WHERE id = :i"), {"i": template_id}
        ).first()
        if row is None:
            continue  # never seeded: ensure_seed_templates mints the current file
        if _sha256(row[0]) in old_hashes:
            new = (template_dir / filename).read_text(encoding="utf-8")
            bind.execute(
                sa.text(
                    "UPDATE templates SET source = :v, parse_certified = NULL, "
                    "parse_report_json = NULL, validated_at = NULL WHERE id = :i"
                ),
                {"v": new, "i": template_id},
            )


def upgrade() -> None:
    _resync(op.get_bind())


def downgrade() -> None:
    # No-op: see module docstring.
    pass

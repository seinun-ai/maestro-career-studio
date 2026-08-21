"""Push the bundled user-template sources into their existing DB rows.

Usage (review-time, against the dev DB), run from ``backend/``::

    unset TEST_DATABASE_URL   # app.db PREFERS it over DATABASE_URL; see main()
    DATABASE_URL=postgresql://app:app@127.0.0.1:55432/maestro_cs \
    BASE_RESUMES_DIR=../base_resumes \
    PATH="/Library/TeX/texbin:$PATH" \
    TYPST_FONT_PATHS=... python -m scripts.apply_template_sources

``BASE_RESUMES_DIR`` is not optional on a host: validating a template writes a
preview PDF under ``$BASE_RESUMES_DIR/template_previews/``, and the default is
the container path ``/app/base_resumes``, which a host user cannot create.

Idempotent, and recoverable. ``update_draft`` commits the new source and marks
the row a DRAFT before validation runs, so a validation that dies part-way
leaves a poisoned row -- one whose source already matches the bundle but whose
status does not say "ready", while the default template keeps serving that
unvalidated source. Re-running the script repairs such a row ("revalidated")
instead of skipping it as unchanged, and one row's failure never stops the
next row from being processed.

Never touches engine, is_default, or display names.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.template import Template
from app.services import template_registry, template_validation


BUNDLED = {
    "xcharter_serif": ("latex", "xcharter_serif.tex.j2"),
    "typst-classic_copy": ("typst", "xcharter_serif.typ"),
}
_BUNDLED_DIR = Path(__file__).resolve().parents[1] / "app" / "templates" / "user"

# Outcomes that leave a row in the state this script exists to produce.
# Anything else -- "missing", "engine-mismatch", "error" -- fails the run.
_SUCCESS_OUTCOMES = frozenset({"updated", "unchanged", "revalidated"})


def apply_bundled_sources(session: Session) -> dict[str, str]:
    report: dict[str, str] = {}
    rows: dict[str, Template | None] = {}
    for template_id, (expected_engine, _) in BUNDLED.items():
        row = session.get(Template, template_id)
        rows[template_id] = row
        if row is None:
            report[template_id] = "missing"
            continue
        if row.engine != expected_engine:
            report[template_id] = "engine-mismatch"
            continue
        report[template_id] = "unchanged"

    if any(
        outcome in {"missing", "engine-mismatch"}
        for outcome in report.values()
    ):
        return report

    for template_id, (_, filename) in BUNDLED.items():
        row = rows[template_id]
        source = (_BUNDLED_DIR / filename).read_text(encoding="utf-8")
        try:
            if row.source != source:
                template_registry.update_draft(session, template_id, source=source)
                template_validation.validate_template(template_id, session)
                report[template_id] = "updated"
            elif row.status != "ready":
                # The recovery path. A matching source is NOT evidence the row
                # is usable: a previous run may have committed this source and
                # then died before validation. Re-validate rather than skip,
                # or the row stays poisoned forever while the script keeps
                # reporting "unchanged" and exiting nonzero.
                template_validation.validate_template(template_id, session)
                report[template_id] = "revalidated"
        except Exception as exc:
            # Isolated per row: the second template must still get its chance,
            # and the operator must still get a report. The exception CLASS
            # only -- a message or traceback here can carry resume text and
            # filesystem paths into the log.
            session.rollback()
            report[template_id] = "error"
            print(f"{template_id}: {type(exc).__name__}", file=sys.stderr)

    return report


def main() -> int:
    if os.environ.get("TEST_DATABASE_URL"):
        # app.db resolves TEST_DATABASE_URL BEFORE settings.database_url, so a
        # shell that has it exported (any shell that has run pytest) would
        # silently rewrite the TEST database here while printing "updated" and
        # exiting 0. No override flag: the variable is the bug, so unset it.
        print(
            "refusing to run: TEST_DATABASE_URL is set. app.db prefers it over "
            "DATABASE_URL, so this MUTATING script would rewrite the test "
            "database and report success. unset TEST_DATABASE_URL and re-run.",
            file=sys.stderr,
        )
        return 2

    with SessionLocal() as session:
        report = apply_bundled_sources(session)
        for template_id, outcome in report.items():
            print(f"{template_id}: {outcome}")

        failed = any(
            outcome not in _SUCCESS_OUTCOMES for outcome in report.values()
        ) or any(
            (row := session.get(Template, template_id)) is None
            or row.status != "ready"
            for template_id in report
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

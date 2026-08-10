import os
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path

import pytest

from app.models.template import Template
from app.services import template_validation
from scripts import apply_template_sources as script


apply_bundled_sources = script.apply_bundled_sources


FIXTURES = Path(__file__).parent / "fixtures"
BACKEND_DIR = Path(__file__).resolve().parents[1]
BUNDLED_SOURCE_DIR = BACKEND_DIR / "app" / "templates" / "user"


def _bundled(filename):
    return (BUNDLED_SOURCE_DIR / filename).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def unset_test_database_url(monkeypatch):
    """Drop TEST_DATABASE_URL for every in-process ``main()`` call here.

    ``main()`` refuses to run while that variable is set, because app.db
    prefers it over DATABASE_URL and the script would rewrite the TEST
    database. The pytest process always has it set, so the in-process tests
    below have to clear it; the refusal itself is covered by a subprocess test
    that sets it back explicitly. This cannot re-point the session the tests
    use: app.db read the variable at import time, long before now.

    Returns the original value so the subprocess test can restore it.
    """
    url = os.environ.get("TEST_DATABASE_URL")
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    return url


def _seed_stale_rows(session):
    """Both bundled rows present, ready, and carrying out-of-date sources."""
    session.add(
        Template(
            id="xcharter_serif",
            display_name="XCharter Serif",
            source=(FIXTURES / "xcharter_serif_original.tex.j2").read_text(),
            status="ready",
            origin="mcp",
            engine="latex",
            is_default=True,
        )
    )
    session.add(
        Template(
            id="typst-classic_copy",
            display_name="XCharter Serif (Typst)",
            source='#set page(paper: "us-letter")\nstale',
            status="ready",
            origin="frontend",
            engine="typst",
            is_default=False,
        )
    )
    session.commit()


def test_apply_updates_rows_and_is_idempotent(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(template_validation.settings, "base_resumes_dir", tmp_path)
    stale_latex = (FIXTURES / "xcharter_serif_original.tex.j2").read_text()
    db_session.add(
        Template(
            id="xcharter_serif",
            display_name="XCharter Serif",
            source=stale_latex,
            status="ready",
            origin="mcp",
            engine="latex",
            is_default=True,
        )
    )
    db_session.add(
        Template(
            id="typst-classic_copy",
            display_name="XCharter Serif (Typst)",
            source='#set page(paper: "us-letter")\nstale',
            status="ready",
            origin="frontend",
            engine="typst",
            is_default=False,
        )
    )
    db_session.commit()

    report = apply_bundled_sources(db_session)

    assert report == {
        "xcharter_serif": "updated",
        "typst-classic_copy": "updated",
    }
    for template_id, (filename, expected_metadata) in {
        "xcharter_serif": (
            "xcharter_serif.tex.j2",
            ("latex", True, "XCharter Serif"),
        ),
        "typst-classic_copy": (
            "xcharter_serif.typ",
            ("typst", False, "XCharter Serif (Typst)"),
        ),
    }.items():
        row = db_session.get(Template, template_id)
        expected_source = (BUNDLED_SOURCE_DIR / filename).read_text(encoding="utf-8")
        assert row.source == expected_source
        assert row.status == "ready"
        assert row.parse_certified is True
        assert (row.engine, row.is_default, row.display_name) == expected_metadata

    assert apply_bundled_sources(db_session) == {
        "xcharter_serif": "unchanged",
        "typst-classic_copy": "unchanged",
    }


def test_apply_reports_missing_rows(db_session):
    assert apply_bundled_sources(db_session) == {
        "xcharter_serif": "missing",
        "typst-classic_copy": "missing",
    }


def test_apply_reports_engine_mismatch_without_mutating_row(db_session):
    row = Template(
        id="xcharter_serif",
        display_name="Do Not Change",
        source="sentinel source",
        status="ready",
        origin="frontend",
        engine="typst",
        is_default=True,
        last_error="sentinel error",
        parse_certified=True,
        parse_report_json={"sentinel": True},
    )
    db_session.add(row)
    db_session.commit()
    before = (
        row.display_name,
        row.source,
        row.status,
        row.origin,
        row.engine,
        row.is_default,
        row.last_error,
        row.validated_at,
        row.parse_certified,
        row.parse_report_json,
    )

    assert apply_bundled_sources(db_session) == {
        "xcharter_serif": "engine-mismatch",
        "typst-classic_copy": "missing",
    }
    db_session.refresh(row)
    assert (
        row.display_name,
        row.source,
        row.status,
        row.origin,
        row.engine,
        row.is_default,
        row.last_error,
        row.validated_at,
        row.parse_certified,
        row.parse_report_json,
    ) == before


def test_apply_preflights_all_rows_before_updating_any_source(db_session):
    stale_source = (FIXTURES / "xcharter_serif_original.tex.j2").read_text()
    latex = Template(
        id="xcharter_serif",
        display_name="XCharter Serif",
        source=stale_source,
        status="ready",
        origin="mcp",
        engine="latex",
        is_default=True,
    )
    db_session.add(latex)
    db_session.commit()

    assert apply_bundled_sources(db_session) == {
        "xcharter_serif": "unchanged",
        "typst-classic_copy": "missing",
    }
    db_session.refresh(latex)
    assert latex.source == stale_source


def test_apply_preflight_engine_mismatch_prevents_other_update(db_session):
    stale_source = (FIXTURES / "xcharter_serif_original.tex.j2").read_text()
    latex = Template(
        id="xcharter_serif",
        display_name="XCharter Serif",
        source=stale_source,
        status="ready",
        origin="mcp",
        engine="latex",
        is_default=True,
    )
    typst = Template(
        id="typst-classic_copy",
        display_name="Wrong Engine",
        source="sentinel source",
        status="ready",
        origin="frontend",
        engine="latex",
        is_default=False,
    )
    db_session.add_all([latex, typst])
    db_session.commit()

    assert apply_bundled_sources(db_session) == {
        "xcharter_serif": "unchanged",
        "typst-classic_copy": "engine-mismatch",
    }
    db_session.refresh(latex)
    assert latex.source == stale_source


def test_cli_exits_nonzero_when_unchanged_bundled_row_is_not_ready(
    db_session, monkeypatch, capsys
):
    bundled_source = (BUNDLED_SOURCE_DIR / "xcharter_serif.tex.j2").read_text(
        encoding="utf-8"
    )
    db_session.add(
        Template(
            id="xcharter_serif",
            display_name="XCharter Serif",
            source=bundled_source,
            status="draft",
            origin="mcp",
            engine="latex",
            is_default=True,
        )
    )
    db_session.commit()
    monkeypatch.setattr(script, "SessionLocal", lambda: nullcontext(db_session))

    exit_code = script.main()

    assert capsys.readouterr().out.splitlines() == [
        "xcharter_serif: unchanged",
        "typst-classic_copy: missing",
    ]
    assert exit_code == 1


def test_cli_exits_nonzero_when_engine_mismatch_row_is_not_ready(
    db_session, monkeypatch, capsys
):
    db_session.add(
        Template(
            id="xcharter_serif",
            display_name="Wrong Engine Draft",
            source="sentinel source",
            status="draft",
            origin="mcp",
            engine="typst",
            is_default=True,
        )
    )
    db_session.commit()
    monkeypatch.setattr(script, "SessionLocal", lambda: nullcontext(db_session))

    exit_code = script.main()

    assert capsys.readouterr().out.splitlines() == [
        "xcharter_serif: engine-mismatch",
        "typst-classic_copy: missing",
    ]
    assert exit_code == 1


def test_cli_exits_nonzero_for_missing_rows(db_session, monkeypatch, capsys):
    monkeypatch.setattr(script, "SessionLocal", lambda: nullcontext(db_session))

    exit_code = script.main()

    assert capsys.readouterr().out.splitlines() == [
        "xcharter_serif: missing",
        "typst-classic_copy: missing",
    ]
    assert exit_code == 1


def test_cli_updates_both_rows_and_exits_zero(
    db_session, tmp_path, monkeypatch, capsys
):
    """The happy path, through main() rather than the library function."""
    monkeypatch.setattr(template_validation.settings, "base_resumes_dir", tmp_path)
    _seed_stale_rows(db_session)
    monkeypatch.setattr(script, "SessionLocal", lambda: nullcontext(db_session))

    exit_code = script.main()

    assert capsys.readouterr().out.splitlines() == [
        "xcharter_serif: updated",
        "typst-classic_copy: updated",
    ]
    assert exit_code == 0
    for template_id, filename in (
        ("xcharter_serif", "xcharter_serif.tex.j2"),
        ("typst-classic_copy", "xcharter_serif.typ"),
    ):
        row = db_session.get(Template, template_id)
        assert row.status == "ready"
        assert row.source == _bundled(filename)


def test_apply_revalidates_a_draft_row_whose_source_already_matches(
    db_session, tmp_path, monkeypatch
):
    """The poisoned row's way out.

    A row can hold the bundled source and still not be ready: update_draft
    commits the source and marks the row a draft BEFORE validation runs, so a
    validation that dies part-way leaves exactly this state. Matching the
    source is therefore not grounds to skip the row.
    """
    monkeypatch.setattr(template_validation.settings, "base_resumes_dir", tmp_path)
    db_session.add(
        Template(
            id="xcharter_serif",
            display_name="XCharter Serif",
            source=_bundled("xcharter_serif.tex.j2"),
            status="draft",
            origin="mcp",
            engine="latex",
            is_default=True,
        )
    )
    db_session.add(
        Template(
            id="typst-classic_copy",
            display_name="XCharter Serif (Typst)",
            source=_bundled("xcharter_serif.typ"),
            status="ready",
            origin="frontend",
            engine="typst",
            is_default=False,
        )
    )
    db_session.commit()

    report = apply_bundled_sources(db_session)

    assert report == {
        "xcharter_serif": "revalidated",
        "typst-classic_copy": "unchanged",
    }
    assert db_session.get(Template, "xcharter_serif").status == "ready"


def test_apply_isolates_a_row_failure_and_recovers_on_a_later_run(
    db_session, tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(template_validation.settings, "base_resumes_dir", tmp_path)
    _seed_stale_rows(db_session)
    monkeypatch.setattr(script, "SessionLocal", lambda: nullcontext(db_session))
    real_validate = template_validation.validate_template

    def failing_validate(template_id, session):
        if template_id == "xcharter_serif":
            # What actually happens on a host with BASE_RESUMES_DIR unset: the
            # preview write goes to the container path and is denied.
            raise PermissionError(
                13, "Permission denied", "/app/base_resumes/template_previews/x.pdf"
            )
        return real_validate(template_id, session)

    monkeypatch.setattr(template_validation, "validate_template", failing_validate)

    assert script.main() == 1
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "xcharter_serif: error",
        "typst-classic_copy: updated",
    ]
    # The exception CLASS and nothing else: no message, no path, no traceback.
    assert captured.err.splitlines() == ["xcharter_serif: PermissionError"]
    assert "/app/base_resumes" not in captured.err
    # The failure did not stop the second row from being processed.
    assert db_session.get(Template, "typst-classic_copy").status == "ready"
    # And the first row is now in exactly the poisoned state: bundled source
    # committed, status still draft.
    poisoned = db_session.get(Template, "xcharter_serif")
    assert poisoned.source == _bundled("xcharter_serif.tex.j2")
    assert poisoned.status == "draft"

    monkeypatch.setattr(template_validation, "validate_template", real_validate)

    assert script.main() == 0
    assert capsys.readouterr().out.splitlines() == [
        "xcharter_serif: revalidated",
        "typst-classic_copy: unchanged",
    ]
    assert db_session.get(Template, "xcharter_serif").status == "ready"


def test_cli_refuses_to_run_against_the_test_database(
    db_session, unset_test_database_url
):
    """TEST_DATABASE_URL outranks DATABASE_URL in app.db — for a MUTATING
    script that means a pytest shell would rewrite the test database and
    report success. It must refuse, and refuse before touching anything."""
    db_session.add(
        Template(
            id="xcharter_serif",
            display_name="Sentinel",
            source="sentinel source",
            status="ready",
            origin="mcp",
            engine="latex",
            is_default=True,
        )
    )
    db_session.commit()
    env = os.environ.copy()
    env["TEST_DATABASE_URL"] = unset_test_database_url

    result = subprocess.run(
        [sys.executable, "-m", "scripts.apply_template_sources"],
        capture_output=True,
        text=True,
        env=env,
        cwd=BACKEND_DIR,
        check=False,
    )

    assert result.returncode == 2
    assert "TEST_DATABASE_URL" in result.stderr
    assert result.stdout == ""
    db_session.expire_all()
    untouched = db_session.get(Template, "xcharter_serif")
    assert (untouched.source, untouched.status) == ("sentinel source", "ready")


def test_cli_exits_nonzero_for_ready_engine_mismatch(
    db_session, monkeypatch, capsys
):
    db_session.add(
        Template(
            id="xcharter_serif",
            display_name="Wrong Engine Ready",
            source="sentinel source",
            status="ready",
            origin="mcp",
            engine="typst",
            is_default=True,
        )
    )
    db_session.commit()
    monkeypatch.setattr(script, "SessionLocal", lambda: nullcontext(db_session))

    exit_code = script.main()

    assert capsys.readouterr().out.splitlines() == [
        "xcharter_serif: engine-mismatch",
        "typst-classic_copy: missing",
    ]
    assert exit_code == 1

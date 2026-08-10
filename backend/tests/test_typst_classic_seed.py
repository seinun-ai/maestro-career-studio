import copy
import json
from pathlib import Path

import pytest

from app.services import pdf_render, template_registry as reg, template_validation as tv
from app.services.template_validation import SAMPLE_RESUME

pytest.importorskip("typst")
pytest.importorskip("pdfplumber")

# Real XCharter install used for the font-resolution assertion below. When it is
# absent (portable CI without texlive), the seed still compiles via typst's
# embedded fallback, but the "no fallback font" check is meaningless, so skip it.
_XCHARTER_DIR = Path(
    "/usr/local/texlive/2025/texmf-dist/fonts/opentype/public/xcharter"
)
# Keyed to the shipped synthetic resume, NOT a personal one: the previous
# target (base_resumes/data_scientist.json) was deleted in the OSS identity
# scrub, which silently turned this regression guard into a permanent skip.
_EXAMPLE_RESUME = Path(__file__).resolve().parents[2] / "base_resumes" / "example.json"


def _seed_source() -> str:
    return (pdf_render.TEMPLATE_DIR / "typst_classic.typ").read_text(encoding="utf-8")


def _pdf_text(pdf_path: Path) -> str:
    import pdfplumber

    with pdfplumber.open(pdf_path) as doc:
        return " ".join((p.extract_text() or "") for p in doc.pages)


def _pdf_fonts(pdf_path: Path) -> set[str]:
    """Basefont names used anywhere in the PDF.

    pdfplumber reports per-character fontnames, which carry the same subset
    prefix (`ABCDEF+Name`) that PyMuPDF's basefont did, so callers that match
    on a substring keep working.
    """
    import pdfplumber

    fonts: set[str] = set()
    with pdfplumber.open(str(pdf_path)) as doc:
        for page in doc.pages:
            fonts.update(char["fontname"] for char in page.chars)
    return fonts


@pytest.mark.skipif(
    not _XCHARTER_DIR.is_dir() or not _EXAMPLE_RESUME.is_file(),
    reason="XCharter and base_resumes/example.json are required for the font-resolution check",
)
def test_typst_classic_seed_no_fallback_font(tmp_path, monkeypatch):
    """Every glyph in the seed compiled against a REAL resume resolves in
    XCharter with no LastResort/Libertinus fallback (the diamond-separator tofu
    regression). Uses the real XCharter install, not typst's embedded fonts."""
    monkeypatch.setattr(pdf_render.settings, "typst_font_paths", [_XCHARTER_DIR])
    data = json.loads(_EXAMPLE_RESUME.read_text(encoding="utf-8"))
    source = _seed_source()
    sys_inputs = pdf_render.build_typst_sys_inputs(source, data)
    pdf = pdf_render.compile_typst_pdf(source, tmp_path, sys_inputs=sys_inputs)
    fonts = _pdf_fonts(pdf)
    bad = [f for f in fonts if "LastResort" in f or "Libertinus" in f]
    assert not bad, f"fell back to non-XCharter fonts: {bad} (all: {sorted(fonts)})"


def test_typst_classic_gpa_rendered_raw(tmp_path):
    """gpa is stored already prefixed ("GPA 4.0/4.0"); the template must render
    it raw, not re-prefix it into "GPA: GPA 4.0/4.0"."""
    data = copy.deepcopy(SAMPLE_RESUME)
    data["education"][0]["gpa"] = "GPA 3.9/4.0"
    source = _seed_source()
    sys_inputs = pdf_render.build_typst_sys_inputs(source, data)
    pdf = pdf_render.compile_typst_pdf(source, tmp_path, sys_inputs=sys_inputs)
    text = _pdf_text(pdf).lower()
    assert "gpa 3.9/4.0" in text
    assert "gpa: gpa" not in text


def test_typst_classic_blank_optionals_equivalent_to_none(tmp_path):
    """Empty/whitespace-only optional strings behave exactly like nulls: the
    cleared-field editor writes '' where LaTeX Jinja truthiness treats it as
    falsy. The Typst path must match: no dangling separators, no empty Summary
    section. Proven by extracting identical text for '' vs None."""
    source = _seed_source()
    blank = copy.deepcopy(SAMPLE_RESUME)
    blank["summary"] = "   "
    blank["contact"]["location"] = ""
    nulled = copy.deepcopy(SAMPLE_RESUME)
    nulled["summary"] = None
    nulled["contact"]["location"] = None

    def _text(data, stem):
        si = pdf_render.build_typst_sys_inputs(source, data)
        pdf = pdf_render.compile_typst_pdf(source, tmp_path, stem=stem, sys_inputs=si)
        return _pdf_text(pdf)

    assert _text(blank, "blank") == _text(nulled, "nulled")


def test_typst_classic_certifies_through_existing_gate(db_session, tmp_path, monkeypatch):
    """THE acceptance test: the seed compiles SAMPLE_RESUME through the REAL
    validation pipeline and comes out parse_certified + extras-capable."""
    monkeypatch.setattr(tv.settings, "base_resumes_dir", tmp_path)
    reg.ensure_seed_templates(db_session)
    row = reg.get(db_session, reg.TYPST_CLASSIC_ID)
    assert row is not None
    assert row.engine == "typst" and row.origin == "seed"
    assert row.status == "ready"
    assert row.parse_certified is True
    report = row.parse_report_json
    assert report["extra_sections_supported"] is True
    assert report["email_ok"] is True
    assert report["headers_missing"] == []
    # MCP em-dash invariant on the seed's own compiled preview
    import pdfplumber

    with pdfplumber.open(tv._preview_path(reg.TYPST_CLASSIC_ID)) as doc:
        text = " ".join((p.extract_text() or "") for p in doc.pages)
    assert "—" not in text


def test_typst_classic_source_invariants():
    source = (pdf_render.TEMPLATE_DIR / "typst_classic.typ").read_text(encoding="utf-8")
    assert "—" not in source  # no em-dashes anywhere, comments included
    assert "(((" not in source and "((*" not in source  # no Jinja layer
    assert pdf_render.typst_source_references_extras(source)
    # all 13 knobs visible to the comment/string-aware typst fmt-key scan.
    # date_format lives only in a header COMMENT (dates are pre-formatted
    # server-side) but is credited because the typst path applies it for every
    # template; the other 12 are live fmt.<key> references.
    assert set(reg.supported_fmt_keys(source, "typst")) == {
        "font_size", "side_margins", "top_bottom_margin", "section_spacing",
        "entry_spacing", "line_spacing", "bullet_icon", "hide_divider",
        "header_align", "justify", "date_format", "education_order", "skills_layout",
    }


def test_typst_classic_knobs_alter_output(tmp_path):
    import pdfplumber

    source = (pdf_render.TEMPLATE_DIR / "typst_classic.typ").read_text(encoding="utf-8")
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    assert tv.compile_against_sample(source, keep_pdf_at=a, engine="typst") is None
    assert tv.compile_against_sample(
        source, keep_pdf_at=b,
        default_formatting={"font_size": 12, "side_margins": 1.0, "header_align": "left"},
        engine="typst",
    ) is None
    with pdfplumber.open(a) as d:
        size_a, x_a = d.pages[0].chars[0]["size"], d.pages[0].chars[0]["x0"]
    with pdfplumber.open(b) as d:
        size_b, x_b = d.pages[0].chars[0]["size"], d.pages[0].chars[0]["x0"]
    assert size_b > size_a          # font_size
    assert x_b != x_a               # margins + header_align moved the first glyph


def test_ensure_seed_templates_idempotent(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(tv.settings, "base_resumes_dir", tmp_path)
    reg.ensure_seed_templates(db_session)
    first = reg.get(db_session, reg.TYPST_CLASSIC_ID).validated_at
    reg.ensure_seed_templates(db_session)  # second call must not re-create/re-validate
    assert reg.get(db_session, reg.TYPST_CLASSIC_ID).validated_at == first


def test_bootstrap_typst_classic_survives_concurrent_insert(db_session, monkeypatch):
    """FIX-10: the row appearing between the existence check and the INSERT (a
    concurrent first load) recovers to the existing row instead of 500ing."""
    from app.models.template import Template

    # Pre-insert as if a competing request already created it (ready -> the
    # recovery path does not re-validate).
    db_session.add(
        Template(
            id=reg.TYPST_CLASSIC_ID, display_name="Typst Classic", source="#x",
            engine="typst", status="ready", origin="seed",
        )
    )
    db_session.commit()
    # Force the check-then-insert race: the initial existence check misses once.
    real_get = db_session.get
    state = {"first": True}

    def fake_get(model, ident, *args, **kwargs):
        if state["first"] and model is Template and ident == reg.TYPST_CLASSIC_ID:
            state["first"] = False
            return None
        return real_get(model, ident, *args, **kwargs)

    monkeypatch.setattr(db_session, "get", fake_get)
    row = reg._bootstrap_typst_classic(db_session)  # must not raise
    assert row is not None and row.id == reg.TYPST_CLASSIC_ID


def test_typst_classic_seed_records_validation_error(db_session, monkeypatch):
    """FIX-12: a first-boot validation failure records WHY on last_error instead
    of leaving it None (which gave no diagnosis and no retry signal)."""
    from app.services import template_validation

    def boom(tid, session):
        raise RuntimeError("preview dir unwritable")

    monkeypatch.setattr(template_validation, "validate_template", boom)
    reg.reset_seed_validation_attempts()  # a fresh boot: attempt validation
    reg._bootstrap_typst_classic(db_session)
    row = reg.get(db_session, reg.TYPST_CLASSIC_ID)
    assert row.status == "draft"
    assert row.last_error and "preview dir unwritable" in row.last_error


def test_typst_classic_seed_revalidates_stuck_draft(db_session, tmp_path, monkeypatch):
    """FIX-12: a seed row stranded non-ready is re-validated on the next ensure."""
    monkeypatch.setattr(tv.settings, "base_resumes_dir", tmp_path)
    reg.reset_seed_validation_attempts()
    reg.ensure_seed_templates(db_session)
    row = reg.get(db_session, reg.TYPST_CLASSIC_ID)
    assert row.status == "ready"
    # Strand it as a draft, as a failed first boot would leave it.
    row.status = "draft"
    row.last_error = "old failure"
    db_session.commit()
    reg.reset_seed_validation_attempts()  # i.e. the next boot
    reg.ensure_seed_templates(db_session)  # re-validates the non-ready seed
    assert reg.get(db_session, reg.TYPST_CLASSIC_ID).status == "ready"


def test_list_templates_seeds_typst_classic(db_session):
    from app.db import get_db
    from app.main import app
    from fastapi.testclient import TestClient

    def _inner():
        yield db_session

    app.dependency_overrides[get_db] = _inner
    try:
        r = TestClient(app).get("/api/templates")
    finally:
        app.dependency_overrides.clear()
    body = {t["id"]: t for t in r.json()}
    assert "default" in body
    assert "typst-classic" in body and body["typst-classic"]["engine"] == "typst"


def test_default_seed_earns_ready_by_rendering(db_session):
    """The default used to be INSERTed `ready` with validated_at=now() and no
    render ever attempted, so every fresh install showed its default template as
    "Not validated" with a 404 thumbnail. Status must be earned."""
    reg.reset_seed_validation_attempts()
    reg.ensure_seed_templates(db_session)
    from app.models.template import Template

    row = db_session.get(Template, reg.DEFAULT_ID)
    assert row.is_default is True
    if row.status == "ready":
        # Earned: validated_at set AND the preview the gallery asks for exists.
        from app.services import template_validation as _tv

        assert row.validated_at is not None
        assert _tv._preview_path(reg.DEFAULT_ID).exists()
    else:
        # Validation legitimately failed (e.g. no pdflatex on this host) — then
        # it must NOT claim a validated_at, and must carry a diagnosis.
        assert row.validated_at is None
        assert row.last_error


def test_a_ready_row_with_no_preview_is_revalidated(db_session):
    """The self-heal for installs already carrying the broken default: the flag
    says ready, the artifact is missing, so the next ensure renders it."""
    from app.services import template_validation

    reg.reset_seed_validation_attempts()
    reg.ensure_seed_templates(db_session)
    preview = template_validation._preview_path(reg.DEFAULT_ID)
    if not preview.exists():
        pytest.skip("default seed could not validate on this host")
    preview.unlink()

    reg.reset_seed_validation_attempts()  # i.e. the next boot
    reg.ensure_seed_templates(db_session)
    assert preview.exists(), "a ready row with a missing preview must re-validate"


def test_the_four_bundled_designs_seed(db_session):
    """They shipped inside the image from the start and never reached the
    database — ensure_seed_templates minted only the two classics."""
    reg.reset_seed_validation_attempts()
    reg.ensure_seed_templates(db_session)
    ids = {t.id for t in reg.list_all(db_session)}
    for template_id, _name, _engine, _file in reg.BUNDLED_TEMPLATES:
        assert template_id in ids, f"{template_id} did not seed"
    # and nothing arrives archived
    assert all(t.archived_at is None for t in reg.list_all(db_session))

import pytest

from app.services import template_registry as reg


def test_supported_fmt_keys_follows_bundled_partial():
    # header_align lives only in the included _header.tex.j2 partial.
    src = "((( fmt.font_size ))) ((* include '_header.tex.j2' *))"
    assert "header_align" in reg.supported_fmt_keys(src)
    assert "font_size" in reg.supported_fmt_keys(src)


def test_supported_fmt_keys_typst_is_comment_aware():
    # A knob named only in a // or /* */ comment must NOT be credited; a live
    # fmt.<key> is; and the server-applied date_format is always offered.
    src = (
        "// fmt.hide_divider is documented in this comment\n"
        "/* fmt.section_spacing also only mentioned here */\n"
        "#set text(size: fmt.font_size * 1pt)\n"
    )
    keys = set(reg.supported_fmt_keys(src, "typst"))
    assert "font_size" in keys
    assert "hide_divider" not in keys
    assert "section_spacing" not in keys
    assert "date_format" in keys  # applied server-side for every typst template


def test_supported_fmt_keys_latex_path_unchanged():
    # LaTeX default engine keeps its exact behavior (no comment stripping,
    # follows Jinja includes).
    src = "((( fmt.font_size ))) ((* include '_header.tex.j2' *))"
    assert reg.supported_fmt_keys(src) == reg.supported_fmt_keys(src, "latex")
    assert "font_size" in reg.supported_fmt_keys(src, "latex")


def test_supported_fmt_keys_rejects_path_traversal_includes(tmp_path):
    # A malicious template must never make supported_fmt_keys read files
    # outside the bundled template dir (absolute paths, .., separators, devices).
    secret = tmp_path / "secret.txt"
    secret.write_text("fmt.pwned", encoding="utf-8")
    for bad in (
        f"((* include '{secret}' *))",
        "((* include '/etc/passwd' *))",
        "((* include '../../../etc/passwd' *))",
        "((* include '/dev/zero' *))",
        "((* include 'sub/dir/file' *))",
    ):
        keys = reg.supported_fmt_keys(bad)
        assert "pwned" not in keys  # never read the traversal target
        assert keys == []  # nothing legitimate to report


def test_get_default_bootstraps_from_file(db_session):
    tmpl = reg.get_default(db_session)
    assert tmpl.id == "default"
    assert tmpl.is_default is True
    assert tmpl.status == "ready"
    assert "section" in tmpl.source.lower() or "documentclass" in tmpl.source.lower()


def test_bootstrap_default_uses_classic_display_name(db_session):
    from app.services import template_registry as reg
    tmpl = reg.get_default(db_session)
    assert tmpl.id == "default"
    assert tmpl.display_name == "Classic"
    assert tmpl.is_default is True


def test_create_draft_then_get(db_session):
    reg.get_default(db_session)
    t = reg.create_draft(db_session, id="minimal", display_name="Minimal", source="X", origin="mcp")
    assert t.status == "draft"
    assert reg.get(db_session, "minimal").display_name == "Minimal"


def test_create_draft_duplicate_raises(db_session):
    reg.create_draft(db_session, id="d", display_name="D", source="X", origin="mcp")
    with pytest.raises(ValueError):
        reg.create_draft(db_session, id="d", display_name="D2", source="Y", origin="mcp")


def test_usable_template_missing_falls_back_to_default(db_session):
    # Render stays tolerant: a persisted template_id that points at a deleted
    # template must not make the resume un-renderable — fall back to default.
    reg.get_default(db_session)  # ensure a default exists
    t = reg.get_usable_template("nope", db_session)
    assert t.id == "default" and t.is_default is True


def test_usable_template_not_ready_falls_back_to_default(db_session):
    # A being-edited (draft) template is likewise not usable for render; fall
    # back to default instead of raising.
    reg.get_default(db_session)
    reg.create_draft(db_session, id="d1", display_name="D", source="X", origin="mcp")
    t = reg.get_usable_template("d1", db_session)
    assert t.id == "default" and t.is_default is True


def test_usable_template_none_returns_default(db_session):
    d = reg.get_usable_template(None, db_session)
    assert d.id == "default" and d.is_default is True


def test_update_draft_resets_status(db_session):
    reg.create_draft(db_session, id="u", display_name="U", source="X", origin="mcp")
    t = reg.get(db_session, "u")
    t.status = "ready"
    db_session.commit()
    reg.update_draft(db_session, "u", source="NEW")
    after = reg.get(db_session, "u")
    assert after.source == "NEW"
    assert after.status == "draft"
    assert after.validated_at is None


def test_update_draft_source_change_resets_parse_certified(db_session):
    # A prior validate certified the (old) source's parse fidelity and stored a
    # parse report. Changing the source must invalidate BOTH until the next
    # validate, not leave a stale True/False or report attached to a different
    # source.
    reg.create_draft(db_session, id="pc", display_name="PC", source="X", origin="mcp")
    t = reg.get(db_session, "pc")
    t.status = "ready"
    t.parse_certified = True
    t.parse_report_json = {"extractor": "pdfplumber", "missing": []}
    db_session.commit()
    reg.update_draft(db_session, "pc", source="NEW")
    after = reg.get(db_session, "pc")
    assert after.parse_certified is None
    assert after.parse_report_json is None


def test_update_draft_display_only_keeps_parse_certified(db_session):
    # A display-name-only edit is not a source change, so certification and the
    # stored parse report both stand.
    reg.create_draft(db_session, id="pc2", display_name="PC2", source="X", origin="mcp")
    t = reg.get(db_session, "pc2")
    t.status = "ready"
    t.parse_certified = True
    t.parse_report_json = {"extractor": "pdfplumber", "missing": []}
    db_session.commit()
    reg.update_draft(db_session, "pc2", display_name="Renamed")
    after = reg.get(db_session, "pc2")
    assert after.parse_certified is True
    assert after.parse_report_json == {"extractor": "pdfplumber", "missing": []}


def test_bootstrap_default_never_creates_second_default(db_session):
    # A user re-points the default to their own template, then the seed 'default'
    # row is deleted. Seeding must NOT resurrect a second is_default=True row.
    from sqlalchemy import select
    from app.models.template import Template

    reg.get_default(db_session)  # seeds 'default' (is_default=True)
    reg.create_draft(db_session, id="mine", display_name="Mine", source="X", origin="frontend")
    m = reg.get(db_session, "mine")
    m.status = "ready"
    db_session.commit()
    reg.set_default(db_session, "mine")  # 'default' is no longer the default
    reg.delete(db_session, "default")    # allowed now that it is not default

    reg._bootstrap_default(db_session)   # must be a no-op, not a second default

    defaults = db_session.scalars(
        select(Template).where(Template.is_default.is_(True))
    ).all()
    assert [d.id for d in defaults] == ["mine"]


def test_set_default_moves_single_default(db_session):
    reg.get_default(db_session)  # 'default' is default
    reg.create_draft(db_session, id="t2", display_name="T2", source="X", origin="frontend")
    t2 = reg.get(db_session, "t2")
    t2.status = "ready"
    db_session.commit()
    reg.set_default(db_session, "t2")
    assert reg.get(db_session, "t2").is_default is True
    assert reg.get(db_session, "default").is_default is False


def test_set_default_requires_ready(db_session):
    reg.get_default(db_session)
    reg.create_draft(db_session, id="t3", display_name="T3", source="X", origin="frontend")
    with pytest.raises(ValueError):
        reg.set_default(db_session, "t3")


def test_delete_refuses_default_allows_other(db_session):
    reg.get_default(db_session)
    reg.create_draft(db_session, id="gone", display_name="G", source="X", origin="mcp")
    with pytest.raises(ValueError):
        reg.delete(db_session, "default")
    reg.delete(db_session, "gone")
    assert reg.get(db_session, "gone") is None


def test_list_all_includes_default(db_session):
    reg.get_default(db_session)
    reg.create_draft(db_session, id="z", display_name="Z", source="X", origin="mcp")
    ids = [t.id for t in reg.list_all(db_session)]
    assert "default" in ids and "z" in ids


def test_create_draft_engine_default_and_typst(db_session):
    lat = reg.create_draft(db_session, id="la", display_name="La", source="X", origin="mcp")
    assert lat.engine == "latex"
    ty = reg.create_draft(
        db_session, id="ty", display_name="Ty", source="#x", origin="mcp", engine="typst"
    )
    assert ty.engine == "typst"


def test_duplicate_copies_engine(db_session):
    reg.create_draft(db_session, id="ty", display_name="Ty", source="#x", origin="mcp", engine="typst")
    copy = reg.duplicate(db_session, "ty", "ty2")
    assert copy.engine == "typst"

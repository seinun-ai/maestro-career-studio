"""The base resume gallery: colour band, tinted footer, grouped by role (resume-colour plan, Task 7).

Source pins in the style of test_frontend_resume_swatch.py: the frontend has no component runner.
"""

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_GALLERY = (_FRONTEND / "components/base-resumes/base-resume-gallery.tsx").read_text(encoding="utf-8")
_PILLS = (_FRONTEND / "components/base-resumes/anchor-pills.tsx").read_text(encoding="utf-8")
_CARD = (_FRONTEND / "components/gallery/gallery-card.tsx").read_text(encoding="utf-8")


def _squash(src: str) -> str:
    return " ".join(src.split())


def _body() -> str:
    return _squash(_GALLERY[_GALLERY.index("function BaseResumeCardBody(") : _GALLERY.index("type RoleGroup")])


def test_the_card_is_a_six_pixel_band_then_the_full_size_thumbnail_then_a_tinted_footer():
    body = _body()
    band = body.index('<div aria-hidden="true" className="h-1.5 shrink-0 bg-resume" />')
    thumb = body.index("<BaseResumeThumbnail")
    footer = body.index("<CardHeader")
    assert band < thumb < footer
    # The thumbnail keeps its size and full bleed: only its top corners go square, under the band.
    assert 'className="rounded-none"' in body[thumb : thumb + 80]
    assert 'className="rounded-none bg-resume-container py-4 text-on-resume-container"' in body[footer:]


def test_the_card_root_carries_the_hue_and_the_footer_runs_to_the_bottom_edge():
    card = _squash(_GALLERY[_GALLERY.index("<GalleryCard") : _GALLERY.index("</GalleryCard>")])
    assert "style={resumeColorStyle(r.color_hue)}" in card
    assert 'cn("gap-0 pb-0", r.archived_at && "opacity-60")' in card
    assert "style?: CSSProperties;" in _CARD and "style={style}" in _CARD


def test_the_title_leads_with_the_square_and_the_footer_text_is_on_the_tint_not_muted():
    body = _body()
    assert body.index("<ResumeSwatch hue={resume.color_hue} />") < body.index('<span className="truncate">{name}</span>')
    meta = body[body.index("{formatLabeledAgo") - 200 :]
    assert "text-muted-foreground" not in body
    assert 'className="flex min-w-0 flex-wrap items-center gap-1.5 text-body-small"' in meta


def test_pills_on_the_tint_take_the_card_fill_so_their_shape_survives_in_light_mode():
    """Measured on all ten presets and a custom hue: every pill's text clears 7:1 on its own fill in light and dark,
    but the default secondary fill is 1.02:1 against the light footer, so the pill shape vanished."""
    assert 'const ON_TINT_PILL_CLASS = "bg-card text-card-foreground";' in _PILLS
    assert "onTint && ON_TINT_PILL_CLASS" in _PILLS
    assert 'variant="secondary" className="bg-card text-card-foreground"' in _squash(_GALLERY)  # Archived
    assert "border-on-resume-container/40" in _GALLERY  # Role not set keeps a border that shows


def test_the_role_pill_is_left_out_of_gallery_cards_only():
    assert "showRole = true" in _PILLS
    assert "showRole && roleSet ? displayRoleTag(" in _PILLS
    assert "showRole={false}" in _GALLERY


def test_cards_sit_under_a_plain_heading_per_role_in_first_seen_order_with_unset_last():
    assert "function groupByRole(" in _GALLERY
    group = _squash(_GALLERY[_GALLERY.index("function groupByRole(") : _GALLERY.index("function RoleSection(")])
    assert "return [...groups.values(), ...(unset.resumes.length > 0 ? [unset] : [])];" in group  # Map keeps insertion order
    assert 'if (r.role_category === "unknown" && !r.role_label) {' in group
    section = _squash(_GALLERY[_GALLERY.index("function RoleSection(") :])
    assert '<h2 id={headingId} className="text-title-small">' in section
    assert '{group.label ?? "Role not set"}' in section
    assert '<span className="text-label-small text-muted-foreground">' in section
    # An unset role keeps its badge on each card, and archived cards keep their place at opacity-60.
    assert "Role not set" in _body()
    assert 'r.archived_at && "opacity-60"' in section

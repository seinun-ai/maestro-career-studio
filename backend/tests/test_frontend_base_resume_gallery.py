"""The base resume gallery: colour band, tinted footer, grouped by role (resume-colour plan, Task 7).

Source pins in the style of test_frontend_resume_swatch.py: the frontend has no component runner. The grouping
itself is node-tested (`lib/role-groups.test.ts`).
"""

from pathlib import Path

from tests._jsx_pins import open_tag, squash, tokens
from tests.node_ts import run_node_test

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_GALLERY = (_FRONTEND / "components/base-resumes/base-resume-gallery.tsx").read_text(encoding="utf-8")
_PILLS = (_FRONTEND / "components/base-resumes/anchor-pills.tsx").read_text(encoding="utf-8")
_CARD = (_FRONTEND / "components/gallery/gallery-card.tsx").read_text(encoding="utf-8")
_PREVIEW = (_FRONTEND / "components/gallery/preview-thumbnail.tsx").read_text(encoding="utf-8")
_GROUPS = (_FRONTEND / "lib/role-groups.ts").read_text(encoding="utf-8")


def _body() -> str:
    return _GALLERY[_GALLERY.index("function BaseResumeCardBody(") : _GALLERY.index("function RoleSection(")]


def test_the_card_is_a_six_pixel_band_then_the_full_size_thumbnail_then_a_tinted_footer():
    body = _body()
    band = open_tag(body, "div")
    assert '"h-1.5 shrink-0 bg-resume"' in band and 'aria-hidden="true"' in band
    thumb_at, footer_at = body.index("<BaseResumeThumbnail"), body.index("<CardHeader")
    assert body.index("<div") < thumb_at < footer_at
    # The thumbnail keeps its size and full bleed: only its top corners go square, under the band.
    assert '"rounded-none"' in open_tag(body, "BaseResumeThumbnail")
    assert {"bg-resume-container", "text-on-resume-container", "rounded-none"} <= tokens(open_tag(body, "CardHeader"))


def test_the_card_root_carries_the_hue_and_the_footer_runs_to_the_bottom_edge():
    card = squash(open_tag(_GALLERY, "GalleryCard"))
    assert "style={resumeColorStyle(r.color_hue)}" in card
    assert 'className="gap-0 pb-0"' in card
    assert "style?: CSSProperties;" in _CARD and "style={style}" in _CARD


def test_the_title_leads_with_the_square_and_nothing_in_the_footer_is_muted():
    body = squash(_body())
    assert body.index("<ResumeSwatch hue={resume.color_hue} />") < body.index('<span className="truncate">{name}</span>')
    # Meta text inherits on-resume-container from the footer; a muted grey would drop below 4.5:1 on some tints.
    assert "text-muted-foreground" not in body


def test_pills_and_badges_on_the_tint_take_the_card_fill_so_their_shape_survives_in_light_mode():
    """Measured on all ten presets and a custom hue: every pill's text clears 7:1 on its own fill in light and dark,
    but the default secondary fill is 1.02:1 against the light footer, so the pill shape vanished."""
    assert 'export const ON_TINT_PILL_CLASS = "bg-card text-card-foreground";' in _PILLS
    assert "onTint && ON_TINT_PILL_CLASS" in _PILLS
    body = _body()
    archived = open_tag(body, "Badge", after="{isArchived && (")
    assert "className={ON_TINT_PILL_CLASS}" in archived


def test_an_archived_card_fades_only_the_picture_and_keeps_its_words_at_full_contrast():
    """The whole card at opacity-60 put the name and meta at about 3.0:1 on the tint (light). Now the band and the page
    image fade and the footer is untouched: measured 7.85:1 or more in light and 9.01:1 in dark on the real data."""
    body = _body()
    assert 'isArchived && "opacity-60"' in open_tag(body, "div")
    assert "dimmed={isArchived}" in open_tag(body, "BaseResumeThumbnail")
    assert 'loading ? "opacity-0" : dimmed && "opacity-60"' in _PREVIEW
    assert "opacity" not in open_tag(body, "CardHeader") + open_tag(_GALLERY, "GalleryCard")


def test_the_role_pill_is_left_out_of_gallery_cards_only():
    assert "showRole = true" in _PILLS
    assert "showRole && roleSet ? displayRoleTag(" in _PILLS
    pills = squash(open_tag(_body(), "AnchorPills"))
    assert "showRole={false}" in pills and "onTint" in pills


def test_unset_means_the_same_thing_in_the_pills_the_badge_and_the_grouping():
    assert "export function isRoleUnset(" in _GROUPS
    assert "const roleSet = !isRoleUnset(resume);" in _PILLS
    assert "const roleUnset = isRoleUnset(resume);" in _GALLERY
    assert "isRoleUnset(resume)" in _GROUPS.split("export function groupByRole", 1)[1]


def test_the_gallery_groups_through_the_pure_lib_and_names_each_group_by_its_heading_only():
    assert "role-category-picker" not in _GROUPS  # the lib never imports the picker
    assert "groupByRole(resumes, labelOf)" in squash(_GALLERY)
    section = _GALLERY[_GALLERY.index("function RoleSection(") :]
    assert "text-title-small" in tokens(open_tag(section, "h2"))
    # The count sits beside the heading, small and muted.
    assert {"text-label-small", "text-muted-foreground"} <= tokens(open_tag(section, "span"))
    # One heading per group, no region per group: a landmark for each role would crowd the page's landmark list.
    assert "<section" not in section and "aria-labelledby" not in section
    # The heading says "Role not set" once; the cards do not repeat it, and the way out is one muted hint beside it.
    assert "Role not set" not in _body()


def test_the_unset_group_carries_one_muted_hint_beside_its_heading():
    hint = _GALLERY.split("group.label === null")[1][:200]
    assert {"text-body-small", "text-muted-foreground"} <= tokens(open_tag(hint, "span"))
    assert "Set a role in each resume" in hint


def test_the_grouping_passes_its_node_tests():
    result = run_node_test("lib/role-groups.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_title_tooltip_names_the_role_the_heading_names():
    """A free-text role or a catalog label, not the bare category key; nothing for an unset role."""
    body = squash(_body())
    assert "const role = roleUnset ? null : displayRoleTag(resume.role_category, resume.role_label, options);" in body
    assert "title={role ? `${name}\\n${role}` : name}" in body
    assert "roleLabel(" not in body

"""A template id is a slug, and the preview it writes stays in the preview dir.

SEC-05, 2026-08-19 audit. `_SLUG_RE` lived on `TemplateCreate` alone, so it
guarded the REST door and nothing else. The chat tools hand `template_id` /
`new_template_id` straight to `template_registry.create_draft` / `duplicate`,
neither of which validated, and `Template.id` is a bare `Text` primary key with
no CHECK constraint — so `../../logs/pwned` persisted as a legitimate row id.
`template_validation._preview_path` then interpolated that id into a path which
`compile_against_sample` mkdir's and `shutil.copy`s into, writing a `.pdf`
wherever the id pointed.

Two independent fixes, because either alone leaves a hole:

* the registry validates, so EVERY surface (REST, chat, MCP, seeding) crosses
  the same gate rather than each door remembering to check;
* `_preview_path` contains, so an id that somehow gets stored cannot escape the
  preview directory when it is rendered.

The containment check is the one `template_registry._resolve_partial` already
uses for bundled partials — resolve, then `relative_to`. It was in the codebase
the whole time; this path just never called it.
"""

import pytest

from app.services import template_registry, template_validation


# Ids that must never reach the database. Each is a different escape shape.
HOSTILE_IDS = [
    ("../../logs/pwned", "parent traversal, the audit's own example"),
    ("../evil", "one level up is still out"),
    ("foo/bar", "a separator makes a subdirectory"),
    ("foo\\bar", "the Windows separator, in case the host is not POSIX"),
    ("/etc/passwd", "an absolute path"),
    ("..", "the parent directory itself"),
    (".", "the current directory"),
    (".hidden", "a dotfile"),
    ("foo%2Fbar", "URL-encoded separator, in case something decodes later"),
    ("foo bar", "a space is not in the slug alphabet"),
    ("Foo", "uppercase is not in the slug alphabet"),
    ("café", "a non-ASCII lookalike"),
    ("", "the empty id"),
]


@pytest.mark.parametrize("bad,why", HOSTILE_IDS)
def test_create_draft_refuses_a_non_slug_id(db_session, bad, why):
    with pytest.raises(ValueError):
        template_registry.create_draft(
            db_session, id=bad, display_name="x", source="x", origin="chat"
        )
    assert db_session.get(template_registry.Template, bad) is None, (
        f"a row was created for {bad!r} ({why})"
    )


@pytest.mark.parametrize("bad,why", HOSTILE_IDS)
def test_duplicate_refuses_a_non_slug_new_id(db_session, bad, why):
    template_registry.create_draft(
        db_session, id="legit-source", display_name="src", source="x", origin="chat"
    )

    with pytest.raises(ValueError):
        template_registry.duplicate(db_session, "legit-source", bad)
    assert db_session.get(template_registry.Template, bad) is None, why


def test_ordinary_slugs_still_work(db_session):
    """The gate must not cost the legitimate case."""
    made = template_registry.create_draft(
        db_session, id="my_template-2", display_name="ok", source="x", origin="chat"
    )

    assert made.id == "my_template-2"


@pytest.mark.parametrize("bad,why", HOSTILE_IDS)
def test_the_preview_path_cannot_leave_the_preview_directory(bad, why):
    """The second, independent gate: containment at the write site.

    Validation at the registry is what SHOULD stop these, but a stored row
    predating the gate, or a future caller that reaches the renderer another
    way, must not be able to write outside the preview root either.
    """
    with pytest.raises(ValueError):
        template_validation._preview_path(bad)


def test_the_preview_path_of_a_real_id_is_inside_the_preview_directory():
    path = template_validation._preview_path("xcharter_serif")

    assert path.parent.name == "template_previews"
    assert path.name == "xcharter_serif.pdf"

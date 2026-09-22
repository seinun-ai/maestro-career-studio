"""Template gallery previews are a synthetic resume, and the thumbnail says so.

A file-wide ``"sample"`` substring would already pass: the component comment
calls the preview a sample resume. The pin is the alt the image actually
exposes, plus ``mark="Sample"`` so the corner label is not optional (a bare
``mark=`` would accept ``mark={undefined}`` or ``mark=""``).
"""

from __future__ import annotations

import re
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_THUMB = (_FRONTEND / "components/templates/template-thumbnail.tsx").read_text()
_PREVIEW = (_FRONTEND / "components/gallery/preview-thumbnail.tsx").read_text()


def test_template_thumbnail_marks_the_preview_as_a_sample():
    assert 'mark="Sample"' in _THUMB, (
        'template-thumbnail.tsx must pass mark="Sample" so a ready preview is '
        "labelled; the image is not the user's resume."
    )
    alt = re.search(r"alt=\{`([^`]*)`\}", _THUMB)
    assert alt is not None, "template thumbnail alt must be a template string"
    assert "sample" in alt.group(1).lower(), (
        f"alt text must say the preview is a sample resume, got {alt.group(1)!r}"
    )


def test_preview_thumbnail_renders_the_mark_top_right():
    """The mark is what the image IS; the chip stays the degraded-state corner."""
    assert re.search(r"\bmark\??:", _PREVIEW), "PreviewThumbnail must accept mark"
    assert "top-1.5 right-1.5" in _PREVIEW
    assert "bottom-1.5 left-1.5" in _PREVIEW
    # The alt carries the words; the badge is visual only.
    assert 'aria-hidden="true"' in _PREVIEW


def test_preview_thumbnail_marks_only_a_showing_image():
    """The "Not validated" placeholder is not a sample resume; never label it one."""
    assert re.search(r"\{(showImage && mark|mark && showImage) && \(", _PREVIEW), (
        "PreviewThumbnail must render the mark only while the image shows"
    )


def test_template_picker_says_previews_are_a_sample():
    select = (_FRONTEND / "components/templates/template-select.tsx").read_text(encoding="utf-8")
    assert "<DialogDescription>Previews show a sample resume, not yours.</DialogDescription>" in select

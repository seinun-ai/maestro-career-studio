"""Synthesize PDFs for tests without PyMuPDF.

PyMuPDF (fitz) was the old fixture generator; it is AGPL-3.0 and was removed
from this project entirely (see THIRD_PARTY_NOTICES.md). These helpers build the
same shapes with `typst`, which is already a pinned runtime dependency, and
Pillow for raster bytes — so the test suite adds no new dependency and no
copyleft.

Shapes provided:
  text_pdf_bytes(text)            one page, a text layer, no images
  image_pdf_bytes(overlay, ...)   certificate shape: full-page image + short
                                  text overlay (drives the vision fallback)
  small_png(...)                  raster bytes for embedding or upload tests
"""

from __future__ import annotations

import io
import pathlib
import tempfile

import typst
from PIL import Image


def _typ_str(value: str) -> str:
    """Quote a Python string as a Typst string literal (code mode).

    Escaping only `\\` and `"` is enough because the value is emitted inside a
    literal, never as markup — so `#`, `*`, `_` and friends stay inert.
    """
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def small_png(width: int = 80, height: int = 60, color: tuple[int, int, int] = (200, 200, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def _compile(source: str, extra_files: dict[str, bytes] | None = None) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        for name, blob in (extra_files or {}).items():
            (root / name).write_bytes(blob)
        doc = root / "doc.typ"
        doc.write_text(source, encoding="utf-8")
        return typst.compile(str(doc))


def blank_pdf_bytes(pages: int = 1) -> bytes:
    """A real, rasterizable PDF with `pages` (near-)empty pages.

    Each page carries one invisible-width space rather than nothing at all:
    a truly empty Typst document produces zero pages.
    """
    body = "\n#pagebreak()\n".join("~" for _ in range(max(pages, 1)))
    return _compile(f"#set page(margin: 1cm)\n{body}\n")


def write_blank_pdf(path, pages: int = 1) -> None:
    """Write `blank_pdf_bytes` to `path`, creating parent dirs."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blank_pdf_bytes(pages))


def text_pdf_bytes(text: str = "Hello", *, size_pt: int = 11) -> bytes:
    """One page carrying `text` as a real, extractable text layer."""
    return _compile(
        f"#set page(margin: 1cm)\n"
        f"#set text(size: {size_pt}pt)\n"
        f"#let body = {_typ_str(text)}\n"
        f"#body\n"
    )


def multipage_text_pdf_bytes(texts: list[str], *, size_pt: int = 11) -> bytes:
    """One page per string. Non-ASCII punctuation round-trips through extraction."""
    pages = "\n#pagebreak()\n".join(f"#({_typ_str(t)})" for t in texts)
    return _compile(f"#set page(margin: 2cm)\n#set text(size: {size_pt}pt)\n{pages}\n")


def image_pdf_bytes(overlay_text: str, *, png: bytes | None = None) -> bytes:
    """Certificate shape: a full-page image with only a short text overlay.

    This is what makes `_pdf_has_images` true while the text layer stays under
    VISION_TEXT_THRESHOLD, so the vision transcription path engages.
    """
    return _compile(
        "#set page(margin: 0cm)\n"
        '#place(top + left, image("bg.png", width: 100%, height: 100%))\n'
        f"#let body = {_typ_str(overlay_text)}\n"
        "#place(top + left, dx: 1cm, dy: 1cm, text(size: 11pt, body))\n",
        {"bg.png": png or small_png(600, 800)},
    )


def text_rich_image_pdf_bytes(long_text: str, *, png: bytes | None = None) -> bytes:
    """An image AND enough text that the vision path must NOT engage."""
    return _compile(
        "#set page(margin: 1cm)\n"
        '#image("bg.png", width: 3cm)\n'
        f"#let body = {_typ_str(long_text)}\n"
        "#text(size: 10pt, body)\n",
        {"bg.png": png or small_png(100, 100)},
    )

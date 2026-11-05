"""Extract text from uploaded documents (PDF / DOCX / PPTX / Markdown / text / images).

Extraction is text-only and lossy by design: the output feeds an LLM that
drafts structured entries, staged for user review before any merge.

Image-based documents (certificates, scans, photo exports) carry their real
content as pixels, not a text layer — a certificate PDF often extracts to just
the recipient's name. For those, a vision-model transcription pass turns the
rendered pages into text so every downstream consumer (KB ingest, chat
attachments, entity documents) sees the actual content. The transcription
degrades to the raw text layer when the provider is unavailable.

PDF text comes from pdfplumber (MIT, already the parse-certification engine),
PDF rasterization from pypdfium2 (BSD-3-Clause/Apache-2.0), and standalone
images from Pillow (MIT-CMU) — pypdfium2 is PDF-only. PyMuPDF is deliberately
NOT used anywhere: it is AGPL-3.0 and would relicense the whole project.
"""

import io
import logging
from collections.abc import Iterator
from pathlib import Path

from app.services.pdfium_lock import PDFIUM_LOCK
from app.services.script_guard import UnsupportedScriptError

logger = logging.getLogger(__name__)

_TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".tex"}
# A .tex is plain text; some browsers send x-tex mimes, others send an empty
# mime (routed by the .tex suffix above).
_TEXT_MIMES = {"text/plain", "text/markdown", "application/x-tex", "text/x-tex"}

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp"}

MAX_CHARS = 200_000
_OFFICE_XML_MAX_BYTES = 50 * 1024 * 1024
_PPTX_MAX_SLIDES = 1_000

# A PDF whose text layer is this sparse AND that embeds images is treated as
# image-based (scanned page, generated certificate) and sent to vision.
VISION_TEXT_THRESHOLD = 150
VISION_MAX_PAGES = 5
VISION_MARKER = "[Transcribed from document images]"

_TRANSCRIBE_PROMPT = (
    "Transcribe ALL text visible in the attached document page image(s), faithfully and "
    "completely: titles, headings, names, organizations, dates, credential IDs, URLs, and "
    "body text. Preserve the reading order. Output plain text only — no commentary, no "
    "markdown fences, no descriptions of decorative graphics."
)


def _pdf_text(data: bytes) -> str:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as doc:
        return "\n\n".join(page.extract_text() or "" for page in doc.pages)


def _pdf_has_images(data: bytes) -> bool:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as doc:
        return any(page.images for page in doc.pages)


def _pdf_page_pngs(data: bytes, scale: float) -> list[bytes]:
    """Render up to VISION_MAX_PAGES PDF pages to PNG bytes."""
    import pypdfium2 as pdfium

    out: list[bytes] = []
    with PDFIUM_LOCK:  # PDFium is not thread-safe (see pdfium_lock)
        pdf = pdfium.PdfDocument(data)
        try:
            for i in range(min(len(pdf), VISION_MAX_PAGES)):
                buf = io.BytesIO()
                pdf[i].render(scale=scale).to_pil().save(buf, format="PNG")
                out.append(buf.getvalue())
        finally:
            pdf.close()
    return out


def _image_png(data: bytes) -> list[bytes]:
    """Normalize a standalone image to a single PNG.

    pypdfium2 is PDF-only, so images take the Pillow path. Opening here also
    validates the bytes — the caller turns a failure into a 4xx.
    """
    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        img.load()
        # PNG cannot hold CMYK and friends; normalize anything exotic.
        if img.mode not in ("1", "L", "LA", "P", "RGB", "RGBA"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
    return [buf.getvalue()]


def _transcribe_images(images: list[bytes], filename: str) -> str:
    """OCR-via-vision-model; returns "" on any failure so callers can degrade."""
    from app.services import llm, model_settings

    try:
        text = llm.call_openai(
            prompt=_TRANSCRIBE_PROMPT,
            model=model_settings.get_fast_model(),
            response_format="text",
            images=images,
            trace_name="doc-vision-transcribe",
        )
    except Exception as exc:  # noqa: BLE001 — degrade to the raw text layer
        logger.warning("Vision transcription failed for %r: %s", filename, exc)
        return ""
    return (text or "").strip()


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _w_text(node) -> str:
    """Read direct runs and hyperlinks; omit revisions and drawing content."""
    out: list[str] = []
    for child in node:
        runs = child.findall(f"{_W}r") if child.tag == f"{_W}hyperlink" else [child]
        for run in runs:
            if run.tag != f"{_W}r":
                continue
            for el in run:
                if el.tag == f"{_W}t":
                    out.append(el.text or "")
                elif el.tag in (f"{_W}tab", f"{_W}ptab"):
                    out.append("\t")
                elif el.tag == f"{_W}cr" or (
                    el.tag == f"{_W}br" and el.get(f"{_W}type", "textWrapping") == "textWrapping"
                ):
                    out.append("\n")
                elif el.tag == f"{_W}noBreakHyphen":
                    out.append("-")
    return "".join(out)


def _grid_value(node, default: str) -> int:
    """A gridSpan/gridBefore count; a non-numeric value is an unreadable file."""
    if node is None:
        return int(default)
    try:
        return int(node.get(f"{_W}val", default))
    except ValueError:
        raise UnreadableFile("This file isn't a readable Word document.") from None


def _docx_text(data: bytes) -> str:
    import zipfile
    import zlib
    from xml.etree import ElementTree

    try:
        return _docx_document_text(data)
    except (zipfile.BadZipFile, ElementTree.ParseError, KeyError, RecursionError,
            zlib.error, EOFError, NotImplementedError, RuntimeError) as exc:
        # A damaged or hand-made archive: corrupt deflate data, an encryption flag,
        # an unknown compression method. All are a file we can't read, never a 500.
        raise UnreadableFile("This file isn't a readable Word document.") from exc


def _docx_document_text(data: bytes) -> str:
    import posixpath
    import zipfile
    from xml.etree import ElementTree

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        part = "word/document.xml"
        try:
            rels = ElementTree.fromstring(archive.read("_rels/.rels"))
        except (KeyError, ElementTree.ParseError):
            pass
        else:
            for relationship in rels:
                if relationship.get("Type", "").endswith("/officeDocument"):
                    part = posixpath.normpath(
                        posixpath.join("/", relationship.get("Target", part))
                    ).lstrip("/")
                    break
        if archive.getinfo(part).file_size > _OFFICE_XML_MAX_BYTES:
            raise UnreadableFile("This Word file is too large to read.")
        root = ElementTree.fromstring(archive.read(part))
    body = root.find(f"{_W}body")
    if body is None:
        return ""
    parts = [_w_text(p) for p in body.findall(f"{_W}p")]
    for table in body.findall(f"{_W}tbl"):
        previous: dict[int, str] = {}
        for row in table.findall(f"{_W}tr"):
            before = row.find(f"{_W}trPr/{_W}gridBefore")
            column = _grid_value(before, "0")
            cells: list[str] = []
            current: dict[int, str] = {}
            for tc in row.findall(f"{_W}tc"):
                span_node = tc.find(f"{_W}tcPr/{_W}gridSpan")
                span = _grid_value(span_node, "1")
                merge = tc.find(f"{_W}tcPr/{_W}vMerge")
                # Horizontal spans repeat the cell; vertical continuations use the cell above.
                if merge is not None and merge.get(f"{_W}val", "continue") == "continue":
                    if column not in previous:
                        raise UnreadableFile("This file isn't a readable Word document.")
                    text = previous[column]
                else:
                    text = "\n".join(_w_text(p) for p in tc.findall(f"{_W}p"))
                cells.extend([text] * span)
                current.update(dict.fromkeys(range(column, column + span), text))
                column += span
            previous = current
            parts.append(" | ".join(cells))
    return "\n".join(parts)


_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"


def _pptx_nodes(node):
    """Walk one representation of alternate content, including inside runs and cells."""
    if node is None:
        return
    yield node
    children = node.findall(f"{_MC}Choice")[:1] if node.tag == f"{_MC}AlternateContent" else node
    for child in children:
        yield from _pptx_nodes(child)


def _a_text(paragraph) -> str:
    return "".join(
        "\n" if node.tag == f"{_A}br" else (node.text or "")
        for node in _pptx_nodes(paragraph) if node.tag in (f"{_A}t", f"{_A}br")
    )


def _pptx_table(node) -> Iterator[str]:
    for row in node.findall(f"{_A}tr"):
        cells = [
            "\n".join(_a_text(p) for p in _pptx_nodes(cell) if p.tag == f"{_A}p")
            for cell in row.findall(f"{_A}tc")
        ]
        if any(cell.strip() for cell in cells):
            yield " | ".join(cells)


def _pptx_skip_placeholder(node, notes: bool) -> bool:
    placeholder = node.find(f"{_P}nvSpPr/{_P}nvPr/{_P}ph")
    skipped = {"sldNum", "hdr", "ftr", "dt"} if notes else {"sldNum"}
    return placeholder is not None and placeholder.get("type") in skipped


def _pptx_content(node, *, notes: bool = False) -> Iterator[str]:
    """Yield shape/group text in order, keeping table rows and the first alternate choice."""
    if node is None or _pptx_skip_placeholder(node, notes):
        return
    if node.tag == f"{_MC}AlternateContent":
        yield from _pptx_content(node.find(f"{_MC}Choice"), notes=notes)
    elif node.tag == f"{_A}p":
        text = _a_text(node)
        if text.strip():
            yield text
    elif node.tag == f"{_A}tbl":
        yield from _pptx_table(node)
    else:
        for child in node:
            yield from _pptx_content(child, notes=notes)


def _pptx_targets(archive, part: str, kind: str) -> dict[str, str]:
    import posixpath
    from xml.etree import ElementTree

    folder, name = posixpath.split(part)
    rels_part = posixpath.join(folder, "_rels", f"{name}.rels")
    try:
        rels_data = archive.read(rels_part)
    except KeyError:
        return {}
    rels = ElementTree.fromstring(rels_data)
    return {
        rel.get("Id"): _pptx_target(folder, rel.get("Target"))
        for rel in rels
        if rel.get("Type", "").endswith(f"/{kind}")
        and rel.get("TargetMode") != "External" and rel.get("Target") and rel.get("Id")
    }


def _pptx_target(folder: str, target: str) -> str:
    import posixpath

    part = posixpath.normpath(posixpath.join(folder, target)).lstrip("/")
    if not part.startswith("ppt/") or not part.endswith(".xml"):
        raise UnreadableFile("This file isn't a readable PowerPoint deck.")
    return part


def _pptx_slide_order(archive) -> list[str]:
    import re
    from xml.etree import ElementTree

    slides = sorted(
        (name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
        key=lambda name: int(re.search(r"slide(\d+)\.xml$", name).group(1)),
    )
    try:
        presentation_data = archive.read("ppt/presentation.xml")
    except KeyError:
        return _pptx_unique_slides(slides)
    presentation = ElementTree.fromstring(presentation_data)
    ids = presentation.findall(f"{_P}sldIdLst/{_P}sldId")
    targets = _pptx_targets(archive, "ppt/presentation.xml", "slide")
    if not ids or any(slide.get(f"{_R}id") not in targets for slide in ids):
        return _pptx_unique_slides(slides)
    return _pptx_unique_slides(targets[slide.get(f"{_R}id")] for slide in ids)


def _pptx_unique_slides(parts) -> list[str]:
    slides = list(dict.fromkeys(parts))
    if len(slides) > _PPTX_MAX_SLIDES:
        raise UnreadableFile("This PowerPoint file is too large to read.")
    return slides


def _pptx_part_content(archive, part: str, *, notes: bool = False) -> Iterator[str]:
    from xml.etree import ElementTree

    root = ElementTree.fromstring(archive.read(part))
    yield from _pptx_content(root.find(f"{_P}cSld/{_P}spTree"), notes=notes)


def _pptx_slide_content(archive, part: str, seen_notes: set[str]) -> Iterator[str]:
    yield from _pptx_part_content(archive, part)
    note_label = False
    for target in _pptx_targets(archive, part, "notesSlide").values():
        if target in seen_notes:
            continue
        seen_notes.add(target)
        for text in _pptx_part_content(archive, target, notes=True):
            if not note_label:
                yield "Notes:"
                note_label = True
            yield text


def _pptx_collect(archive) -> str:
    parts: list[str] = []
    total = 0
    seen_notes: set[str] = set()
    for number, part in enumerate(_pptx_slide_order(archive), 1):
        first = True
        for text in _pptx_slide_content(archive, part, seen_notes):
            prefix = "\n"
            if first:
                prefix = ("\n\n" if parts else "") + f"Slide {number}\n"
                first = False
            chunk = prefix + text
            parts.append(chunk[:MAX_CHARS - total])
            total += len(chunk)
            if total >= MAX_CHARS:
                return "".join(parts)
    return "".join(parts)


def _pptx_text(data: bytes) -> str:
    import zipfile
    import zlib
    from xml.etree import ElementTree

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            # Bound the whole deck's XML before decompressing any part, including notes/rels.
            xml_size = sum(
                part.file_size for part in archive.infolist()
                if part.filename.startswith("ppt/") and part.filename.endswith((".xml", ".rels"))
            )
            if xml_size > _OFFICE_XML_MAX_BYTES:
                raise UnreadableFile("This PowerPoint file is too large to read.")
            return _pptx_collect(archive)
    except (zipfile.BadZipFile, ElementTree.ParseError, KeyError, RecursionError,
            zlib.error, EOFError, NotImplementedError, RuntimeError) as exc:
        # A damaged or hand-made archive: corrupt deflate data, an encryption flag,
        # an unknown compression method. All are a file we can't read, never a 500.
        raise UnreadableFile("This file isn't a readable PowerPoint deck.") from exc


class UnreadableFile(ValueError):
    """A file this app cannot read, and its message is a sentence for the user
    (the Assistant's attachment 400, an import report's reason)."""


UNSUPPORTED_TYPE = "Use a PDF, Word, PowerPoint, text or image file."
# No file name inside a sentence: every surface that lists files already puts
# the name beside the reason ("scan.png: This file isn't a readable image."),
# and a name like "my_cv.pdf" is text the web app refuses to show
# (`isPlainSentence`), hiding the whole reason.
NOT_AN_IMAGE = "This file isn't a readable image."
NO_TEXT = "No text could be read in this file."
UPLOAD_UNREADABLE = "Couldn't read this file. Try again."


def plain_read_error(exc: Exception) -> str:
    """Why a file could not be read, as a sentence for the user: the error's
    own words when it was written for them, else the generic one. A wrapper's
    cause counts too: the resume parser re-raises a provider error as a
    RuntimeError, and with no key that sentence is the fix, not the file."""
    # lazy, as above: llm is heavy
    from app.services.llm import LLMProviderError
    from app.services.llm_capabilities import CapabilityMissing

    worded = (UnreadableFile, UnsupportedScriptError, LLMProviderError, CapabilityMissing)
    seen: BaseException | None = exc
    visited: set[int] = set()  # a third-party parser can leave a cycle in the chain
    while seen is not None and id(seen) not in visited:
        if isinstance(seen, worded):
            return str(seen)
        visited.add(id(seen))
        seen = seen.__cause__
    return "Couldn't read this file."


def extract_text(filename: str, mime: str | None, data: bytes) -> str:
    suffix = Path(filename or "").suffix.lower()
    mime = (mime or "").lower().split(";")[0].strip()

    supported_suffixes = {".pdf", ".docx", ".pptx", *_TEXT_SUFFIXES, *_IMAGE_SUFFIXES}
    if suffix == ".ppt" or (
        mime == "application/vnd.ms-powerpoint" and suffix not in supported_suffixes
    ):
        raise UnreadableFile("Save it as .pptx or PDF.")
    if suffix == ".pdf" or mime == "application/pdf":
        text = _pdf_text(data)
        if len(text.strip()) < VISION_TEXT_THRESHOLD and _pdf_has_images(data):
            transcript = _transcribe_images(_pdf_page_pngs(data, scale=2.0), filename)
            if transcript:
                text = f"{text.strip()}\n\n{VISION_MARKER}\n{transcript}"
    elif suffix == ".docx" or mime == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        text = _docx_text(data)
    elif suffix == ".pptx" or mime == (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ):
        text = _pptx_text(data)
    elif suffix in _IMAGE_SUFFIXES or mime in _IMAGE_MIMES:
        try:
            pages = _image_png(data)
        except Exception as exc:  # corrupt/undecodable image bytes
            raise UnreadableFile(NOT_AN_IMAGE) from exc
        transcript = _transcribe_images(pages, filename)
        text = f"{VISION_MARKER}\n{transcript}" if transcript else ""
    elif suffix in _TEXT_SUFFIXES or mime in _TEXT_MIMES:
        text = data.decode("utf-8", errors="replace")
    else:
        raise UnreadableFile(UNSUPPORTED_TYPE)

    text = text.strip()
    if not text:
        raise UnreadableFile(NO_TEXT)
    return text[:MAX_CHARS]

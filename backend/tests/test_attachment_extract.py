import io
from xml.etree import ElementTree
import zipfile

import pytest

from app.services.attachment_extract import extract_text
from tests.pdf_fixtures import (
    image_pdf_bytes,
    small_png,
    text_pdf_bytes,
    text_rich_image_pdf_bytes,
)


def _make_pdf_bytes(text: str) -> bytes:
    return text_pdf_bytes(text)


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    document = ElementTree.Element(f"{w}document")
    body = ElementTree.SubElement(document, f"{w}body")
    for p in paragraphs:
        paragraph = ElementTree.SubElement(body, f"{w}p")
        run = ElementTree.SubElement(paragraph, f"{w}r")
        ElementTree.SubElement(run, f"{w}t").text = p
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>',
        )
        archive.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="word/document.xml" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"/>'
            '</Relationships>',
        )
        archive.writestr("word/document.xml", ElementTree.tostring(document))
    return buf.getvalue()


def test_extract_pdf():
    data = _make_pdf_bytes("Churn prediction pipeline reduced attrition 12%")
    text = extract_text("slides.pdf", "application/pdf", data)
    assert "Churn prediction pipeline" in text


def test_extract_docx():
    data = _make_docx_bytes(["Project Report", "Built a RAG service."])
    text = extract_text(
        "report.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        data,
    )
    assert "Built a RAG service." in text


def test_extract_markdown_and_txt_passthrough():
    assert "# Title" in extract_text("notes.md", "text/markdown", b"# Title\nbody")
    assert extract_text("notes.txt", "text/plain", b"hello") == "hello"


def test_extract_tex():
    # A .tex is plain text (the documented chat style-reference workflow) and
    # should decode via the text branch: by x-tex mime, and by suffix when the
    # browser sends an empty/unknown mime for .tex.
    tex = r"\documentclass{article}\begin{document}Churn model\end{document}"
    body = tex.encode("utf-8")
    assert "Churn model" in extract_text("resume.tex", "application/x-tex", body)
    assert "Churn model" in extract_text("resume.tex", "text/x-tex", body)
    assert "Churn model" in extract_text("resume.tex", "", body)
    assert "Churn model" in extract_text("resume.tex", None, body)


def test_unsupported_type_raises():
    with pytest.raises(ValueError, match="Use a PDF, Word, PowerPoint, text or image file."):
        extract_text("archive.zip", "application/zip", b"PK\x03\x04")


def test_empty_extraction_raises():
    with pytest.raises(ValueError, match=r"^No text could be read in this file\.$"):
        extract_text("empty.txt", "text/plain", b"   ")


# --- vision fallback for image-based documents (certificates, scans) ---


def _small_png() -> bytes:
    return small_png()


def _make_certificate_pdf_bytes(overlay_text: str) -> bytes:
    """Certificate shape: a full-page image with only a short text overlay."""
    return image_pdf_bytes(overlay_text)


def _mock_vision(monkeypatch, transcript):
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        if isinstance(transcript, Exception):
            raise transcript
        return transcript

    monkeypatch.setattr("app.services.llm.call_openai", fake)
    monkeypatch.setattr("app.services.model_settings.get_fast_model", lambda session=None: "fast-model")
    return calls


def test_sparse_image_pdf_gets_vision_transcript(monkeypatch):
    calls = _mock_vision(
        monkeypatch,
        "Certificate of Completion\nClaude with the Claude Developer Platform\nAnthropic Academy",
    )
    data = _make_certificate_pdf_bytes("Riley Quill")

    text = extract_text("certificate.pdf", "application/pdf", data)

    assert "Riley Quill" in text  # text layer preserved
    assert "Anthropic Academy" in text  # transcript appended
    assert len(calls) == 1
    assert calls[0]["model"] == "fast-model"
    assert calls[0]["response_format"] == "text"
    images = calls[0]["images"]
    assert images and all(isinstance(i, bytes) for i in images)


def test_text_rich_pdf_skips_vision(monkeypatch):
    calls = _mock_vision(monkeypatch, "should never be called")
    long_text = "Churn prediction pipeline reduced attrition twelve percent. " * 10

    data = text_rich_image_pdf_bytes(long_text)

    text = extract_text("report.pdf", "application/pdf", data)
    assert "Churn prediction pipeline" in text
    assert calls == []


def test_sparse_text_only_pdf_skips_vision(monkeypatch):
    """No images in the PDF -> nothing to transcribe, even when text is short."""
    calls = _mock_vision(monkeypatch, "should never be called")
    data = _make_pdf_bytes("Churn prediction pipeline reduced attrition 12%")

    text = extract_text("slides.pdf", "application/pdf", data)
    assert "Churn prediction pipeline" in text
    assert calls == []


def test_image_attachment_transcribed(monkeypatch):
    calls = _mock_vision(monkeypatch, "AWS Certified Solutions Architect - Associate\nAmazon Web Services")
    text = extract_text("cert.png", "image/png", _small_png())

    assert "AWS Certified Solutions Architect" in text
    assert len(calls) == 1
    assert calls[0]["images"]


def test_sparse_pdf_vision_failure_degrades_to_layer_text(monkeypatch):
    _mock_vision(monkeypatch, RuntimeError("provider down"))
    data = _make_certificate_pdf_bytes("Riley Quill")

    text = extract_text("certificate.pdf", "application/pdf", data)
    assert text.strip() == "Riley Quill"


def test_image_attachment_vision_failure_raises(monkeypatch):
    _mock_vision(monkeypatch, RuntimeError("provider down"))
    with pytest.raises(ValueError, match=r"^No text could be read in this file\.$"):
        extract_text("cert.png", "image/png", _small_png())


def _timed_out():
    from app.services.llm_providers.errors import _TIMED_OUT, _no_answer

    return _no_answer(_TIMED_OUT, "request timed out")


def test_vision_call_is_bounded(monkeypatch):
    """One request with a time limit and no SDK retries, so a slow model cannot
    hold the upload for the SDK's 10-minute default."""
    from app.services.attachment_extract import VISION_TIMEOUT_SECONDS

    calls = _mock_vision(monkeypatch, "Transcript")
    extract_text("cert.png", "image/png", _small_png())

    assert calls[0]["timeout"] == VISION_TIMEOUT_SECONDS
    assert calls[0]["max_retries"] == 0


def test_image_attachment_vision_timeout_says_so(monkeypatch):
    _mock_vision(monkeypatch, _timed_out())
    with pytest.raises(ValueError, match=r"^Reading this file took too long\."):
        extract_text("cert.png", "image/png", _small_png())


def test_sparse_pdf_vision_timeout_keeps_layer_text(monkeypatch):
    _mock_vision(monkeypatch, _timed_out())
    data = _make_certificate_pdf_bytes("Riley Quill")

    assert extract_text("certificate.pdf", "application/pdf", data).strip() == "Riley Quill"


def test_imageonly_pdf_vision_timeout_says_so(monkeypatch):
    _mock_vision(monkeypatch, _timed_out())
    data = _make_certificate_pdf_bytes("")

    with pytest.raises(ValueError, match=r"^Reading this file took too long\."):
        extract_text("scan.pdf", "application/pdf", data)


def test_timeout_message_is_a_plain_sentence():
    """The web app shows an attachment's 400 only when it passes isPlainSentence."""
    import re

    from app.services.attachment_extract import READ_TIMED_OUT

    assert len(READ_TIMED_OUT) <= 240
    assert re.fullmatch(r"[A-Z][^{}\[\]<>_`|\\]*[.!?]", READ_TIMED_OUT)


def test_corrupt_image_raises_value_error(monkeypatch):
    _mock_vision(monkeypatch, "should never be called")
    with pytest.raises(ValueError):
        extract_text("x.png", "image/png", b"\x89PNG")


@pytest.mark.parametrize('filename,data', [
    ('deck.pptx', None), ('document.docx', _make_docx_bytes(['Readable Word'])),
    ('document.pdf', _make_pdf_bytes('Readable PDF')),
    ('notes.txt', b'Readable text'),
], ids=['pptx', 'docx', 'pdf', 'text'])
def test_supported_suffix_wins_over_legacy_powerpoint_mime(filename, data):
    if data is None:
        from tests.test_attachment_extract_pptx import _deck_parts, _zip
        data = _zip(_deck_parts())
    assert extract_text(filename, 'application/vnd.ms-powerpoint', data)

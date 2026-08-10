import io

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
    import docx

    document = docx.Document()
    for p in paragraphs:
        document.add_paragraph(p)
    buf = io.BytesIO()
    document.save(buf)
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
    with pytest.raises(ValueError, match="Unsupported"):
        extract_text("archive.zip", "application/zip", b"PK\x03\x04")


def test_empty_extraction_raises():
    with pytest.raises(ValueError, match="no extractable text"):
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
    with pytest.raises(ValueError, match="no extractable text"):
        extract_text("cert.png", "image/png", _small_png())


def test_corrupt_image_raises_value_error(monkeypatch):
    _mock_vision(monkeypatch, "should never be called")
    with pytest.raises(ValueError):
        extract_text("x.png", "image/png", b"\x89PNG")

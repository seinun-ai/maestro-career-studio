"""Every browser file picker offers exactly the formats the backend can read.

Reported 2026-09-01: a `.docx` could not be selected for the Career KB or the
chat attachment picker although the backend accepts it. The six `accept`
lists were hand-typed, extension-only, and no two alike; an OS dialog maps
each entry to a system type, and an extension-only list is what greys a file
out when that mapping is missing. `frontend/lib/upload-accept.ts` is now the
one list, carries the MIME types beside the extensions, and this test pins
it to `attachment_extract`'s branches so neither side can drift.
"""

import re
from pathlib import Path

from app.services import attachment_extract as ax

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
ACCEPT_TS = (FRONTEND / "lib" / "upload-accept.ts").read_text(encoding="utf-8")


def _list(name: str) -> list[str]:
    match = re.search(rf"const {name} = \[(.*?)\];", ACCEPT_TS, re.S)
    assert match, name
    return re.findall(r'"([^"]+)"', match.group(1))


def _backend_suffixes() -> set[str]:
    return {".pdf", ".docx", *ax._TEXT_SUFFIXES, *ax._IMAGE_SUFFIXES}


def test_every_extension_offered_is_one_the_extractor_reads():
    offered = set(_list("DOCUMENT_EXTS")) | set(_list("IMAGE_EXTS"))
    assert offered <= _backend_suffixes(), offered - _backend_suffixes()
    # …and the reverse: a format the backend learned to read must reach the
    # pickers, or it is a capability nobody can use from the browser.
    assert _backend_suffixes() <= offered, _backend_suffixes() - offered


def test_docx_is_offered_by_extension_and_by_mime_type():
    docx_mime = re.search(r'DOCX_MIME =\s*"([^"]+)"', ACCEPT_TS).group(1)
    assert docx_mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert ".docx" in _list("DOCUMENT_EXTS")
    assert "DOCX_MIME" in re.search(r"const DOCUMENT_MIMES = \[(.*?)\];", ACCEPT_TS, re.S).group(1)
    # The extractor recognises the same MIME, so a browser that reports it
    # instead of the extension still lands on the docx branch.
    assert docx_mime in ax.extract_text.__code__.co_consts or docx_mime in (
        (ROOT / "backend" / "app" / "services" / "attachment_extract.py").read_text()
    )


def test_every_file_picker_reads_the_shared_list():
    """No component may type its own accept string again."""
    offenders = []
    for path in (FRONTEND / "components").rglob("*.tsx"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r'accept=(\{[^}]*\}|"[^"]*")', text):
            value = match.group(1)
            # `Dropzone` forwards its own `accept` prop; the caller is the
            # site that has to name the shared constant.
            if value == "{accept}":
                continue
            if value.startswith('"') or "ACCEPT" not in value:
                offenders.append(f"{path.relative_to(ROOT)}: accept={value}")
        for match in re.finditer(r'const \w*ACCEPT\w* = ("[^"]*")', text):
            offenders.append(f"{path.relative_to(ROOT)}: {match.group(0)}")
    assert offenders == [], offenders


def test_the_pickers_that_take_documents_exist():
    """The four surfaces the report named, still wired to a file input."""
    expected = {
        "career/documents-panel.tsx": "DOCUMENT_ACCEPT",
        "career/capture-box.tsx": "DOCUMENT_ACCEPT",
        "chat/chat-page.tsx": "DOCUMENT_ACCEPT",
        "setup/upload-dialog.tsx": "DOCUMENT_ACCEPT",
        "career/resume-import-dialog.tsx": "RESUME_FILE_ACCEPT",
    }
    for rel, constant in expected.items():
        text = (FRONTEND / "components" / rel).read_text(encoding="utf-8")
        assert constant in text, rel

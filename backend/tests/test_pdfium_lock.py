"""PDFium is not thread-safe, and the backend calls it from threads.

FastAPI runs sync endpoints on a threadpool, so the /templates gallery fetching
previews in parallel put two `FPDF_LoadPage` calls in flight at once and the
backend segfaulted inside libpdfium (`CPDF_ColorSpace::
CreateBufAndSetDefaultColor`). pypdfium2 5.x takes no lock of its own. A second,
Python-level race rode along: two `ensure_page_images` calls on one PDF
unlinked and rewrote each other's PNGs.

The fix is ONE process-wide lock (`app.services.pdfium_lock.PDFIUM_LOCK`). The
first test pins that every PDFium touch under `app/` sits lexically inside a
`with PDFIUM_LOCK:` block; the second hammers the preview path from threads.
"""
import ast
import os
import threading
import time
from pathlib import Path

from PIL import Image

from app.services import pdf_preview
from tests.pdf_fixtures import image_pages_pdf_bytes

APP = Path(__file__).resolve().parents[1] / "app"
LOCK_NAME = "PDFIUM_LOCK"


def _lock_spans(tree: ast.AST) -> list[tuple[int, int]]:
    """Line spans of every `with PDFIUM_LOCK:` (bare or dotted) block."""
    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.With, ast.AsyncWith)):
            continue
        for item in node.items:
            expr = item.context_expr
            name = getattr(expr, "id", None) or getattr(expr, "attr", None)
            if name == LOCK_NAME:
                spans.append((node.lineno, node.end_lineno))
    return spans


def _bound_by(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Import):
        return {a.asname or a.name for a in node.names if a.name.startswith("pypdfium2")}
    if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("pypdfium2"):
        return {a.asname or a.name for a in node.names}
    return set()


def _imported_names(tree: ast.AST) -> set[str]:
    """Names bound to pypdfium2: the module, or anything imported from it."""
    return set().union(*(_bound_by(node) for node in ast.walk(tree)))


def _call_root(call: ast.Call) -> str | None:
    root = call.func
    while isinstance(root, ast.Attribute):
        root = root.value
    return getattr(root, "id", None)


def _pdfium_names(tree: ast.AST) -> set[str]:
    """The imported names plus every variable assigned from a call on one of
    them — the document handles, whose page loads and renders are the calls
    that crashed."""
    names = _imported_names(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if _call_root(node.value) in names:
                names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return names


def _unlocked_pdfium_uses() -> tuple[list[str], int]:
    offenders: list[str] = []
    checked = 0
    for path in sorted(APP.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "pypdfium2" not in source:
            continue
        tree = ast.parse(source)
        names, spans = _pdfium_names(tree), _lock_spans(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in names:
                checked += 1
                if not any(lo <= node.lineno <= hi for lo, hi in spans):
                    offenders.append(f"{path.relative_to(APP.parent)}:{node.lineno} {node.id}")
    return offenders, checked


def test_every_pdfium_use_holds_the_one_lock():
    offenders, checked = _unlocked_pdfium_uses()
    # Non-vacuous: pdf_preview and attachment_extract both open documents.
    assert checked >= 4, checked
    assert not offenders, (
        "PDFium used outside `with PDFIUM_LOCK:` (app/services/pdfium_lock.py) — "
        "it is not thread-safe and the threadpool WILL call it concurrently: "
        + ", ".join(offenders)
    )


# --- The preview path under threads ------------------------------------------

THREADS = 8
ROUNDS = 4


def _hammer(pdf_path: Path) -> tuple[list[list[str]], list[BaseException]]:
    results: list[list[str]] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(THREADS)

    def worker():
        try:
            barrier.wait()
            results.append([p.name for p in pdf_preview.ensure_page_images(pdf_path)])
        except BaseException as exc:  # noqa: BLE001 — collected, asserted below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results, errors


def test_concurrent_previews_of_one_pdf_agree(tmp_path):
    """Every round starts from a PDF newer than its PNGs, so all threads race
    to re-rasterize the same file — the gallery's parallel fetch, repeated.
    An image-bearing PDF on purpose: the crash was in colour-space setup."""
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(image_pages_pdf_bytes(3))
    expected = ["page-1.png", "page-2.png", "page-3.png"]
    for round_no in range(ROUNDS):
        stamp = time.time() + 10 * (round_no + 1)
        os.utime(pdf_path, (stamp, stamp))
        results, errors = _hammer(pdf_path)
        assert not errors, f"round {round_no}: {errors[0]!r}"
        assert results == [expected] * THREADS, f"round {round_no}"
        for name in expected:
            with Image.open(pdf_preview.pages_dir(pdf_path) / name) as img:
                img.load()  # a truncated or half-written PNG raises here

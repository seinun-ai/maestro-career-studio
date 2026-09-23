"""The ONE process-wide lock around PDFium.

PDFium is not thread-safe and pypdfium2 (5.x) takes no lock of its own, while
FastAPI runs every sync endpoint on a threadpool: the /templates gallery
fetching previews in parallel put two `FPDF_LoadPage` calls in flight and the
backend segfaulted inside libpdfium. So every PDFium touch under `app/` —
opening a document, loading or rendering a page, closing it — happens inside
`with PDFIUM_LOCK:`. Pinned by tests/test_pdfium_lock.py (an AST scan, so a
new call site outside the lock fails the suite).

A plain Lock, not an RLock: nothing that holds it calls back into another
PDFium user, and a nested acquire should deadlock loudly in a test rather than
quietly widen what the lock covers.
"""
import threading

PDFIUM_LOCK = threading.Lock()

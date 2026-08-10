"""Rasterize rendered PDFs to per-page PNGs for the frontend preview.

Uses pypdfium2 (BSD-3-Clause/Apache-2.0) rather than PyMuPDF: PyMuPDF is
AGPL-3.0, which this project cannot ship under a permissive license.
"""

from pathlib import Path

import pypdfium2 as pdfium

DPI = 150
# pypdfium2 renders at 72 DPI when scale=1. Note it ceils the pixel dimensions
# from a float, so US Letter comes out 1275x1651 where PyMuPDF gave 1275x1650 —
# the extra row is pure white padding, never clipped content. Verified against
# the old renderer: identical structure, differences confined to text
# antialiasing (0.03% of pixels after an 8x downsample).
_SCALE = DPI / 72


def pages_dir(pdf_path: Path) -> Path:
    return pdf_path.with_suffix(".pages")


def ensure_page_images(pdf_path: Path) -> list[Path]:
    """Return per-page PNGs, regenerating only when the PDF is newer."""
    out_dir = pages_dir(pdf_path)
    pdf_mtime = pdf_path.stat().st_mtime
    existing = sorted(out_dir.glob("page-*.png")) if out_dir.is_dir() else []
    if existing and all(p.stat().st_mtime >= pdf_mtime for p in existing):
        return existing

    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("page-*.png"):
        stale.unlink()
    paths: list[Path] = []
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        for i in range(len(pdf)):
            path = out_dir / f"page-{i + 1}.png"
            pdf[i].render(scale=_SCALE).to_pil().save(path)
            paths.append(path)
    finally:
        pdf.close()
    return paths

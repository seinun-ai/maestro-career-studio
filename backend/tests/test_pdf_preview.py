from app.services import pdf_preview, pdf_render


MINIMAL_TEX = r"""\documentclass{article}
\pagestyle{empty}
\begin{document}
Hello world
\end{document}
"""


def test_page_images_and_count(tmp_path):
    pdf_path = pdf_render.compile_pdf(MINIMAL_TEX, tmp_path, stem="doc")

    pages = pdf_preview.ensure_page_images(pdf_path)
    assert len(pages) == 1
    assert pages[0].exists() and pages[0].suffix == ".png"
    assert pages[0].name == "page-1.png"
    assert pages[0].parent == pdf_preview.pages_dir(pdf_path)

    # Cached: a second call must not re-rasterize (PNG mtimes unchanged).
    first_mtimes = {p: p.stat().st_mtime_ns for p in pages}
    pages_again = pdf_preview.ensure_page_images(pdf_path)
    assert pages_again == pages
    assert {p: p.stat().st_mtime_ns for p in pages_again} == first_mtimes

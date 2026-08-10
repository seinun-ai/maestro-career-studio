from pathlib import Path
from shutil import rmtree

from app.models.application import Application
from app.models.qa_entry import QAEntry
from app.services import pdf_preview


def remove_files(paths: list[Path]) -> None:
    """Best-effort disk removal for artifact paths — call AFTER the owning commit.

    PDFs take their preview-pages directory (<pdf>.pages/) with them; emptied
    parent folders are pruned.
    """
    parents: set[Path] = set()
    for path in paths:
        if path.suffix.lower() == ".pdf":
            rmtree(pdf_preview.pages_dir(path), ignore_errors=True)
        parents.add(path.parent)
        try:
            path.unlink()
        except OSError:
            pass
    for parent in parents:
        try:
            parent.rmdir()
        except OSError:
            pass


def stage_resume_artifact_removal(application: Application) -> list[Path]:
    """Clear the row's resume PDF/TeX references; return the old paths.

    No disk IO here: the caller removes the files with remove_files() after its
    transaction commits, so a rollback never leaves the DB pointing at deleted
    files.
    """
    stale = [Path(raw) for raw in (application.pdf_path, application.tex_path) if raw]
    application.pdf_path = None
    application.tex_path = None
    return stale


def collect_application_files(application: Application) -> list[Path]:
    """All files owned by the application (resume artifacts + Q&A PDFs)."""
    raws: list[str | None] = [application.pdf_path, application.tex_path]
    raws.extend(entry.pdf_path for entry in (application.qa_entries or []))
    return [Path(raw) for raw in raws if raw]


def cleanup_qa_entry_files(entry: QAEntry) -> None:
    if entry.pdf_path:
        remove_files([Path(entry.pdf_path)])

from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.application import Application
from app.schemas.resumes_folder import (
    ChosenFolder,
    ResumesFolderError,
    ResumesFolderSettings,
    ResumesFolderUpdate,
    ShownCopy,
)
from app.services import folder_opener, folder_picker
from app.services import resumes_folder as rf

router = APIRouter(tags=["resumes-folder"])

UNAVAILABLE = "This copy of Maestro keeps no resumes folder."
OFF = "Saving copies is turned off in Settings › Basics › Resume PDFs."
NO_PDF = "Create the PDF first."
NOT_SAVED = "Maestro couldn't save a copy to your resumes folder. Check Settings › Basics › Resume PDFs."
NOT_FOUND = "This application doesn't exist."
CANT_OPEN = "Maestro couldn't open the folder on this computer."  # no path: planning decision 9
PICKER_BUSY = "A folder dialog is already open."
PICKER_FAILED = "Maestro couldn't open the folder dialog."


def _state(db: Session) -> ResumesFolderSettings:
    reason = rf.availability()
    base = rf.root(db)
    err = rf.last_error(db)
    default = rf.app_settings.resumes_folder_default
    return ResumesFolderSettings(
        available=reason is None, reason=reason, enabled=rf.enabled(db),
        folder=str(base) if base else None,
        folder_display=rf.display(base) if base else None,
        default_folder=str(default) if default else None,
        custom=rf.is_custom(db), platform=rf.platform_name(),
        picker=reason is None and folder_picker.available(),
        last_error=ResumesFolderError(message=rf.ERROR_SENTENCES.get(err["code"], rf.ERROR_SENTENCES["write"]),
                                      at=err["at"]) if err else None,
    )


def _require_available() -> None:
    if rf.availability() is not None:
        raise HTTPException(409, detail=UNAVAILABLE)


@router.get("/api/settings/resumes-folder", response_model=ResumesFolderSettings)
def get_resumes_folder(db: Annotated[Session, Depends(get_db)]):
    return _state(db)


@router.put("/api/settings/resumes-folder", response_model=ResumesFolderSettings,
            dependencies=[Depends(_require_available)])
def put_resumes_folder(payload: ResumesFolderUpdate, db: Annotated[Session, Depends(get_db)]):
    before = (rf.enabled(db), rf.root(db))
    owed = rf.last_error(db) is not None  # Save after reconnecting a drive retries the failed copies
    if "folder" in payload.model_fields_set:
        try:
            chosen = rf.validate_folder(payload.folder) if payload.folder is not None else None
        except rf.FolderRefused as exc:
            raise HTTPException(422, detail=str(exc)) from None
        rf._put(db, rf.PATH_KEY, str(chosen) if chosen else None)
    if payload.enabled is not None:
        rf._put(db, rf.ENABLED_KEY, None if payload.enabled else "off")
    rf._put(db, rf.LAST_ERROR_KEY, None)  # a new choice starts with a clean slate
    db.flush()  # autoflush is off: the reads below must see the staged rows
    changed = owed or (rf.enabled(db), rf.root(db)) != before
    db.commit()
    if changed and rf.enabled(db):
        rf.start_backfill()
    return _state(db)


@router.post("/api/settings/resumes-folder/open", status_code=204,
             dependencies=[Depends(_require_available)])
def open_resumes_folder(db: Annotated[Session, Depends(get_db)]):
    base = rf.root(db)
    if rf.is_custom(db) and not folder_picker.is_dir(base):  # the opener would fail in its child, after we answered 204
        raise HTTPException(409, detail=rf.ERROR_SENTENCES["missing"])
    try:
        if not rf.is_custom(db):
            base.mkdir(parents=True, exist_ok=True)
        folder_opener.open_folder(base)
    except (OSError, folder_opener.OpenerUnavailable):
        raise HTTPException(409, detail=CANT_OPEN) from None


@router.post("/api/settings/resumes-folder/choose", response_model=ChosenFolder,
             dependencies=[Depends(_require_available)])
def choose_resumes_folder(db: Annotated[Session, Depends(get_db)]):
    """Show the OS folder dialog. Never saves: the user still presses Save, which validates the path."""
    if not folder_picker.available():
        raise HTTPException(409, detail=PICKER_FAILED)
    base = rf.root(db)
    start = base if base is not None and folder_picker.is_dir(base) else Path.home()
    try:
        chosen = folder_picker.choose(start)
    except folder_picker.PickerBusy:
        raise HTTPException(409, detail=PICKER_BUSY) from None
    except folder_picker.PickerFailed:
        raise HTTPException(409, detail=PICKER_FAILED) from None
    return ChosenFolder(folder=str(chosen) if chosen else None)


@router.post("/api/applications/{application_id}/show-copy", response_model=ShownCopy,
             dependencies=[Depends(_require_available)])
def show_copy(application_id: UUID, db: Annotated[Session, Depends(get_db)]):
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(404, detail=NOT_FOUND)
    if not rf.enabled(db):
        raise HTTPException(409, detail=OFF)
    if not application.pdf_path:
        raise HTTPException(409, detail=NO_PDF)
    path = rf.copy_application(application_id)  # heals a copy missed for any reason
    if path is None:
        raise HTTPException(409, detail=NOT_SAVED)
    try:
        folder_opener.reveal(path)
    except folder_opener.OpenerUnavailable:
        raise HTTPException(409, detail=CANT_OPEN) from None
    return ShownCopy(path=str(path))

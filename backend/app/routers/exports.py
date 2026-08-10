from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.exports import CareerExportMetadata
from app.services import exports as career_exports

router = APIRouter(prefix="/api/exports", tags=["exports"])


def _metadata(result: career_exports.CareerExportResult) -> CareerExportMetadata:
    return CareerExportMetadata(
        generated_at=result.generated_at,
        content_hash=result.content_hash,
    )


@router.get("", response_model=list[CareerExportMetadata])
def list_exports(db: Annotated[Session, Depends(get_db)]):
    return [_metadata(career_exports.get_career_export(db))]


@router.get("/career")
def download_career_export(db: Annotated[Session, Depends(get_db)]):
    result = career_exports.get_career_export(db)
    return Response(
        content=result.markdown,
        media_type="text/markdown",
        headers={
            "Content-Disposition": 'attachment; filename="career.md"',
            "X-Content-SHA256": result.content_hash,
        },
    )


@router.post("/career/refresh", response_model=CareerExportMetadata)
def refresh_career_export(db: Annotated[Session, Depends(get_db)]):
    return _metadata(career_exports.get_career_export(db, force=True))

"""GET /api/setup/status — derived getting-started state (read-only)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.setup_status import SetupStatus
from app.services import setup_status

router = APIRouter(prefix="/api/setup", tags=["setup"])


@router.get("/status", response_model=SetupStatus)
def get_status(db: Annotated[Session, Depends(get_db)]):
    return setup_status.build_status(db)

"""GET /api/automations reads only the full-automation switch."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import auto_apply_settings, automations
from app.services.automations import AutomationCatalog

router = APIRouter(prefix="/api/automations", tags=["automations"])


@router.get("", response_model=AutomationCatalog)
def get_automations(db: Annotated[Session, Depends(get_db)]) -> AutomationCatalog:
    """Reads one setting only, the full-automation switch (peek: never writes)."""
    return automations.catalog(
        full_automation=auto_apply_settings.peek_settings(db).full_automation)

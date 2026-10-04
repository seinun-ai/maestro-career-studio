"""GET /api/automations — the copy-prompt catalog for the Automations page.

Read-only and DB-free: the skill files are the source
(docs/plans/2026-10-04-automations-page-design.md).
"""

from fastapi import APIRouter

from app.services import automations
from app.services.automations import AutomationCatalog

router = APIRouter(prefix="/api/automations", tags=["automations"])


@router.get("", response_model=AutomationCatalog)
def get_automations() -> AutomationCatalog:
    return automations.catalog()

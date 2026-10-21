"""Today, the home page's one request (services/today.py). Read-only."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import today

router = APIRouter(prefix="/api/today", tags=["today"])


@router.get("")
def get_today(
    db: Annotated[Session, Depends(get_db)],
    tz: Annotated[str | None, Query(max_length=64, description="the browser's IANA time zone")] = None,
    utc_offset_minutes: Annotated[
        int | None,
        Query(ge=-720, le=840, description="the browser's offset from UTC, east positive"),
    ] = None,
):
    """Next up (an offer awaiting your answer, else the ready PDF with the best match, else a
    proposal's question), the counts behind it, and applied per local day for the last 7 days with
    this week's replies and interviews. Local days follow `tz`, else `utc_offset_minutes`, else UTC."""
    try:
        zone, label = today.local_zone(tz, utc_offset_minutes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return today.build(db, zone=zone, zone_label=label)

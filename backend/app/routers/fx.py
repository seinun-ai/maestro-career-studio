"""ECB reference rates for the browser (`services/fx_rates.py` holds the rules)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.money import FxRatesOut
from app.services import fx_rates

router = APIRouter(prefix="/api/fx", tags=["fx"])


def _out(cache: dict[str, Any] | None) -> FxRatesOut:
    cache = cache or {}
    return FxRatesOut(
        base=cache.get("base") or "EUR",
        date=cache.get("date"),
        rates={code: float(rate) for code, rate in (cache.get("rates") or {}).items()},
        fetched_at=cache.get("fetched_at"),
        source=fx_rates.SOURCE,
        source_url=fx_rates.ECB_URL,
    )


@router.get("/rates", response_model=FxRatesOut)
def get_rates(db: Annotated[Session, Depends(get_db)]):
    """The cached rates, fetched first when older than a day. Never an error for the network:
    offline answers with the last cache, or with no rates at all."""
    return _out(fx_rates.refresh(db))


@router.post("/rates/refresh", response_model=FxRatesOut)
def refresh_rates(db: Annotated[Session, Depends(get_db)]):
    """Fetch now (Settings › Money, Update). 502 when the ECB cannot be reached; the cache stays."""
    try:
        return _out(fx_rates.fetch_now(db))
    except fx_rates.FetchFailed:
        raise HTTPException(502, "Couldn't get today's rates from the European Central Bank.") from None

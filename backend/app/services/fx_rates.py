"""ECB daily reference rates: fetched at most once a day, cached on this machine, never invented.

Source: the European Central Bank's euro foreign exchange reference rates
(`ECB_URL`, about 29 currencies, published around 16:00 CET on working days, quoted as units
per euro). They are official and free; the ECB asks to be cited and says they are for
information only, so the UI names the source and the rate date. This is Maestro's one outbound
call that carries none of the user's data (PRIVACY.md, "Exchange rates").

The rules:

- **A page asks; nothing polls.** `refresh` fetches only when a caller (`GET /api/fx/rates`)
  asks and the cache is older than a day (`MAX_AGE`). A failed try waits `RETRY_AFTER` before
  the next, so an offline machine does not make every page wait out the 5 s timeout.
  `fetch_now` (`POST /api/fx/rates/refresh`, the Update button) fetches on request.
- **Offline keeps the last cache.** A failed or malformed answer leaves the stored rates as they
  were. With no cache at all `current` is None and `money.convert` has no rate: the posted
  amount shows and the job stays out of comparisons.
- **The cache is machine-local.** One `Setting` row, `fx_rates` (in
  `sync/registry.LOCAL_SETTING_PREFIXES`): each copy fetches its own, it is not the user's
  profile, so the always-on copy may write it and a profile bundle never carries it. No file
  mirror: it is a cache, refetched when lost. Rates are stored as the ECB's own text, so a
  figure is exact.
- **The fetch is injectable** (`fetch(url) -> text`) and the default goes through
  `http_client.new_client`, the one builder that survives a malformed NO_PROXY.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree import ElementTree

import httpx
from sqlalchemy.orm import Session

from app.models.setting import Setting
from app.services import http_client

logger = logging.getLogger(__name__)

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
SOURCE = "European Central Bank"
KEY = "fx_rates"  # machine-local: sync/registry.LOCAL_SETTING_PREFIXES
TIMEOUT_S = 5.0
MAX_AGE = timedelta(days=1)
RETRY_AFTER = timedelta(hours=1)
_CUBE = "{http://www.ecb.int/vocabulary/2002-08-01/eurofxref}Cube"
# One fetch at a time in this process: two pages asking at once share the first one's answer.
_LOCK = threading.RLock()

Fetch = Callable[[str], str]


class FetchFailed(Exception):
    """The ECB could not be reached, or answered with something that is not its rates file."""


def fetch_text(url: str) -> str:
    """GET `url` and return its text; raises on a network error or an error status."""
    with http_client.new_client(timeout=TIMEOUT_S, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def parse_ecb_xml(text: str) -> dict[str, Any]:
    """The ECB daily file as `{"base": "EUR", "date": "YYYY-MM-DD", "rates": {code: Decimal}}`.

    Raises ValueError for anything else: not XML, a DOCTYPE (the ECB file has none, so entity
    tricks never reach the parser), no dated day, or a rate that is not a positive number.
    """
    if "<!DOCTYPE" in text or "<!ENTITY" in text:
        raise ValueError("the ECB rates file has no DOCTYPE")
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise ValueError("not XML") from exc
    day = next((cube for cube in root.iter(_CUBE) if cube.get("time")), None)
    if day is None:
        raise ValueError("no dated day in the ECB file")
    when = str(day.get("time"))
    date.fromisoformat(when)  # ValueError for a malformed date
    rates: dict[str, Decimal] = {}
    for cube in day.iter(_CUBE):
        if cube is day:
            continue
        code = str(cube.get("currency") or "").strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise ValueError("a rate without an ISO 4217 code")
        try:
            rate = Decimal(str(cube.get("rate")))
        except InvalidOperation as exc:
            raise ValueError(f"{code} has no numeric rate") from exc
        if not rate.is_finite() or rate <= 0:
            raise ValueError(f"{code} has no positive rate")
        rates[code] = rate
    if not rates:
        raise ValueError("no rates in the ECB file")
    return {"base": "EUR", "date": when, "rates": rates}


def _load(session: Session) -> dict[str, Any]:
    row = session.get(Setting, KEY)
    if row is None or not row.value:
        return {}
    try:
        blob = json.loads(row.value)
    except json.JSONDecodeError:
        return {}
    return blob if isinstance(blob, dict) else {}


def _usable(blob: dict[str, Any]) -> dict[str, Any] | None:
    rates: dict[str, Decimal] = {}
    for code, value in (blob.get("rates") or {}).items():
        try:
            rate = Decimal(str(value))
        except InvalidOperation:
            continue
        if rate.is_finite() and rate > 0:
            rates[str(code).upper()] = rate
    if not rates or not blob.get("date"):
        return None
    return {"base": str(blob.get("base") or "EUR"), "date": str(blob["date"]), "rates": rates,
            "fetched_at": blob.get("fetched_at")}


def current(session: Session) -> dict[str, Any] | None:
    """The cached rates (`Decimal`, units per euro) with their date, or None when there are none.

    A read only: it never fetches and never writes (the peek pattern).
    """
    return _usable(_load(session))


def _when(value: Any) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _due(blob: dict[str, Any], now: datetime) -> bool:
    fetched, tried = _when(blob.get("fetched_at")), _when(blob.get("attempted_at"))
    if fetched is not None and now - fetched < MAX_AGE:
        return False
    return tried is None or now - tried >= RETRY_AFTER


def _write(session: Session, blob: dict[str, Any]) -> None:
    text = json.dumps(blob, sort_keys=True)
    row = session.get(Setting, KEY)
    if row is None:
        session.add(Setting(key=KEY, value=text))
    else:
        row.value = text
    session.commit()


def fetch_now(session: Session, fetch: Fetch | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    """Fetch the ECB file now and store it; raises FetchFailed and keeps the old cache when it
    cannot. Either way the try is recorded, so `refresh` waits before trying again."""
    now = now or datetime.now(UTC)
    with _LOCK:
        blob = _load(session)
        try:
            parsed = parse_ecb_xml((fetch or fetch_text)(ECB_URL))
        except (httpx.HTTPError, httpx.InvalidURL, ValueError, OSError) as exc:
            # The reason's type only: a response body or a proxy URL never reaches the log.
            logger.warning("ECB reference rates not fetched (%s); the last cache stays", type(exc).__name__)
            _write(session, {**blob, "attempted_at": now.isoformat()})
            raise FetchFailed from exc
        stamp = now.isoformat()
        _write(session, {
            "base": parsed["base"],
            "date": parsed["date"],
            "rates": {code: str(rate) for code, rate in parsed["rates"].items()},
            "fetched_at": stamp,
            "attempted_at": stamp,
        })
        return current(session)


def refresh(session: Session, fetch: Fetch | None = None, *, now: datetime | None = None) -> dict[str, Any] | None:
    """The rates a page should use: fetched first when the cache is older than a day (and no try
    failed within the hour), else the cache as it is. None when there has never been a cache."""
    now = now or datetime.now(UTC)
    with _LOCK:
        if _due(_load(session), now):
            try:
                fetch_now(session, fetch, now=now)
            except FetchFailed:
                pass
        return current(session)

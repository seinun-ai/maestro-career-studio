"""Explicit opt-in and one-use key enrollment. Only local sync.* settings are written."""

import json
import os
import threading
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import begin_write
from app.models.setting import Setting
from app.models.types import utcnow
from app.services import http_client
from app.services.sync import status

LOCK = threading.Lock()
WINDOW_KEY = "sync.pairing_until"
PAIRED_KEY = "sync.last_paired_at"
LIMIT_KEY = "sync.enrollment_limit"
WINDOW = timedelta(minutes=10)
CLOSED = "Pairing isn't open on your laptop. Click Allow pairing for 10 minutes there."
LIMITED = "Pairing was tried too often. Wait 10 minutes, then allow pairing again."
EXISTS = "This copy already has a sync key. Use the pair option to finish setup."
HOME_ONLY = "Allow pairing on your laptop, not on the always-on copy."
UNREADABLE_KEY = "The sync key file can't be read. Check it before pairing."
DISK = "Maestro couldn't save the sync key."
ANSWER = "Your laptop's answer wasn't what Maestro expected."
VERSION = "Update Maestro on both machines to the same version."
TUNNEL = "The laptop's address must be this machine's own tunnel (127.0.0.1)."


class Refused(Exception):
    """Fixed, safe words only; never pass exception text, a body, or key material."""

    def __init__(self, status_code: int, detail: str, reason: str = "pairing"):
        super().__init__(detail)
        self.status_code, self.detail, self.reason = status_code, detail, reason

    @property
    def outcome(self) -> str:
        return "transient" if self.status_code >= 500 or self.reason == "busy" else "needs_person"


def _get(db: Session, name: str) -> str | None:
    return db.scalar(select(Setting.value).where(Setting.key == name))


def _set(db: Session, name: str, value: str) -> None:
    row = db.get(Setting, name)
    if row is None:
        db.add(Setting(key=name, value=value))
    else:
        row.value = value


def _time(raw: object) -> datetime | None:
    try:
        value = datetime.fromisoformat(raw) if isinstance(raw, str) else None
        return value if value is not None and value.tzinfo is not None else None
    except ValueError:
        return None


def _open_until(db: Session) -> datetime | None:
    until = _time(_get(db, WINDOW_KEY))
    return until if until is not None and until > utcnow() else None


def window_status(db: Session) -> dict:
    if not status.enabled():
        return {"enabled": False, "open_until": None, "last_paired_at": None}
    until, paired = _open_until(db), _time(_get(db, PAIRED_KEY))
    return {"enabled": True, "open_until": until.isoformat() if until else None,
            "last_paired_at": paired.isoformat() if paired else None}


def open_window(db: Session) -> dict:
    if status.read_key() is None:
        try:
            status.create_key()
        except FileExistsError:
            raise Refused(409, UNREADABLE_KEY) from None
        except OSError:
            raise Refused(500, DISK) from None
    begin_write(db)
    until = (utcnow() + WINDOW).isoformat()
    _set(db, WINDOW_KEY, until)
    db.commit()
    return {"open_until": until}


def close_window(db: Session) -> dict:
    if not status.enabled():
        return {"open_until": None}
    begin_write(db)
    _set(db, WINDOW_KEY, "")
    db.commit()
    return {"open_until": None}


def _limit(db: Session) -> dict:
    try:
        stored = json.loads(_get(db, LIMIT_KEY) or "{}")
    except ValueError:
        return {}
    return stored if isinstance(stored, dict) else {}


def check_window(db: Session) -> None:
    blocked = _time(_limit(db).get("blocked_until"))
    if blocked is not None and blocked > utcnow():
        raise Refused(429, LIMITED, "limited")
    if _open_until(db) is None:
        raise Refused(409, CLOSED, "closed")


def record_failure(db: Session) -> None:
    begin_write(db)
    now, previous = utcnow(), _limit(db).get("failures", [])
    previous = previous[-5:] if isinstance(previous, list) else []
    times = [_time(item) for item in previous]
    recent = [item.isoformat() for item in times if item is not None and now - WINDOW < item <= now]
    recent.append(now.isoformat())
    blocked = (now + WINDOW).isoformat() if len(recent) >= 5 else None
    _set(db, LIMIT_KEY, json.dumps({"failures": recent, "blocked_until": blocked}))
    db.commit()


def consume_window(db: Session) -> None:
    """The key is handed off once: close and stamp in the same transaction."""
    begin_write(db)
    check_window(db)
    _set(db, WINDOW_KEY, "")
    _set(db, PAIRED_KEY, utcnow().isoformat())
    _set(db, LIMIT_KEY, "")
    db.commit()


def require_missing_key() -> None:
    if os.path.lexists(status.key_path()):
        raise Refused(409, EXISTS)


def _headers(db: Session) -> dict:
    revision, mine = status.schema_revision(db), status.machine_id(db)
    db.commit()
    return {"X-Maestro-Sync": f"{status.SYNC_PROTOCOL}:{revision}:{mine}"}


def _received_key(response: httpx.Response) -> str:
    if response.status_code != 200:
        raise _remote_refusal(response)
    try:
        body = response.json() if len(response.content) <= 8192 else None
        key = body.get("key") if isinstance(body, dict) else None
    except ValueError:
        key = None
    if not _valid_key(key):
        raise Refused(409, ANSWER)
    return key


def _valid_key(key: object) -> bool:
    return (isinstance(key, str) and 0 < len(key) <= 4096 and key.isascii()
            and key.isprintable() and not any(char.isspace() for char in key))


def _remote_reason(response: httpx.Response) -> str | None:
    try:
        body = response.json() if len(response.content) <= 8192 else {}
        reason = body.get("reason") if isinstance(body, dict) else None
    except ValueError:
        reason = None
    return reason if isinstance(reason, str) else None


def _remote_refusal(response: httpx.Response) -> Refused:
    code, reason = response.status_code, _remote_reason(response)
    conflicts = {"closed": CLOSED, "version": VERSION,
                 "busy": "A sync is already running on your laptop."}
    if code == 409 and reason in conflicts:
        return Refused(409, conflicts[reason], reason)
    if code == 429:
        return Refused(429, LIMITED, "limited")
    if code == 404:
        return Refused(409, "Sync isn't set up on your laptop.")
    return Refused(503 if code >= 500 else 409, "Your laptop couldn't finish that sync request.")


def enroll_here(db: Session) -> dict:
    if not status.remote_is_own_tunnel():
        raise Refused(409, TUNNEL)
    require_missing_key()
    try:
        with http_client.new_client(base_url=settings.sync_remote_url, headers=_headers(db),
                                    timeout=httpx.Timeout(30, connect=10), trust_env=False,
                                    follow_redirects=False) as http:
            key = _received_key(http.post("/api/sync/enroll"))
    except (httpx.TransportError, httpx.InvalidURL):
        raise Refused(503, "Laptop unreachable.") from None
    try:
        status.save_key(key)
    except FileExistsError:
        raise Refused(409, EXISTS) from None
    except OSError:
        raise Refused(500, DISK) from None
    return {"ok": True}

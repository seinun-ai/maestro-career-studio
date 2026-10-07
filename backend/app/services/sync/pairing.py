"""One-time pairing. The code is shown once; only its digest is stored."""

import hashlib
import json
import os
import secrets
import threading
import time
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import begin_write
from app.models.setting import Setting
from app.models.types import utcnow
from app.services import http_client
from app.services.sync import seal, status

LOCK = threading.Lock()
WINDOW_KEY = "sync.pairing_until"
PAIRED_KEY = "sync.last_paired_at"
DIGEST_KEY = "sync.pairing_digest"
_ATTEMPTS_KEY = "sync.pairing_attempts"
WINDOW = timedelta(minutes=10)
CLOSED = "Pairing didn't work. Show a pairing code on your laptop and try again."
EXISTS = "This copy already has a sync key. Use the pair option to finish setup."
HOME_ONLY = "Show a pairing code on your laptop, not on the always-on copy."
UNREADABLE_KEY = "The sync key file can't be read. Check it before pairing."
DISK = "Maestro couldn't save the sync key."
ANSWER = "Your laptop's answer wasn't what Maestro expected."
UNVERIFIED = "The laptop's answer couldn't be verified."
TUNNEL = "The laptop's address must be this machine's own tunnel or an https:// address."
INVALID_CODE = "That pairing code isn't valid."
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_CONFUSABLES = {"O": "0", "I": "1", "L": "1"}
_STAND_IN = secrets.token_hex(32)
_REPLAY = seal.ReplayCache()


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


def _ensure_key() -> None:
    if status.read_key() is not None:
        return
    try:
        status.create_key()
    except FileExistsError:
        raise Refused(409, UNREADABLE_KEY) from None
    except OSError:
        raise Refused(500, DISK) from None


def _new_code() -> str:
    bits = int.from_bytes(secrets.token_bytes(10), "big")
    chars = [_ALPHABET[(bits >> shift) & 31] for shift in range(75, -1, -5)]
    raw = "".join(chars)
    return "-".join(raw[index:index + 4] for index in range(0, 16, 4))


def normalize_code(raw: object) -> str | None:
    """Uppercase, drop spaces and dashes, map O/I/L, and keep 16 Crockford characters."""
    if not isinstance(raw, str) or len(raw) > 64:
        return None
    chars = _crockford(raw)
    if chars is None or len(chars) != 16:
        return None
    return "".join(chars)


def _crockford(raw: str) -> list[str] | None:
    chars = []
    for char in raw.upper():
        if char in " -":
            continue
        mapped = _CONFUSABLES.get(char, char)
        if mapped not in _ALPHABET:
            return None
        chars.append(mapped)
    return chars


def _code_secret(code: str) -> str | None:
    normalized = normalize_code(code)
    if normalized is None:
        return None
    return hashlib.sha256(normalized.encode()).hexdigest()


def open_window(db: Session) -> dict:
    _ensure_key()
    code = _new_code()
    secret = _code_secret(code)
    if secret is None:
        raise Refused(500, DISK)
    begin_write(db)
    until = (utcnow() + WINDOW).isoformat()
    _set(db, WINDOW_KEY, until)
    _set(db, DIGEST_KEY, secret)
    _drop_attempts(db)
    db.commit()
    return {"code": code, "open_until": until}


def _drop_attempts(db: Session) -> None:
    row = db.get(Setting, _ATTEMPTS_KEY)
    if row is not None:
        db.delete(row)


def _clear_code(db: Session) -> None:
    _set(db, WINDOW_KEY, "")
    _set(db, DIGEST_KEY, "")
    _drop_attempts(db)


def close_window(db: Session) -> dict:
    if not status.enabled():
        return {"open_until": None}
    begin_write(db)
    _clear_code(db)
    db.commit()
    return {"open_until": None}


def _hex64(value: object) -> str | None:
    if not isinstance(value, str) or len(value) != 64:
        return None
    if any(char not in "0123456789abcdef" for char in value):
        return None
    return value


def live_digest(db: Session) -> str | None:
    if _open_until(db) is None:
        return None
    return _hex64(_get(db, DIGEST_KEY))


def _stamp(header: str) -> int:
    try:
        return int(header.split(".")[1])
    except (IndexError, ValueError):
        return int(time.time())


def seen_enroll(rid: str, header: str) -> bool:
    """True when this rid was already accepted. Call only after the mac verifies."""
    expiry = _stamp(header) + seal.SKEW_SECONDS + seal.REPLAY_SECONDS
    return _REPLAY.seen(rid, time.time(), until=expiry)


def _stored(db: Session, name: str) -> str | None:
    value = db.execute(text("SELECT value FROM settings WHERE key = :name"), {"name": name}).scalar()
    return value if isinstance(value, str) else None


def _window_live(raw: str | None) -> bool:
    until = _time(raw)
    return until is not None and until > utcnow()


def _claim_digest(db: Session, digest: str) -> bool:
    """One row changes. A second caller in the same window updates nothing."""
    result = db.execute(
        text("UPDATE settings SET value = '' WHERE key = :name AND value = :digest"),
        {"name": DIGEST_KEY, "digest": digest})
    return result.rowcount == 1


def _stamp_paired(db: Session) -> None:
    db.expire_all()
    _set(db, WINDOW_KEY, "")
    _set(db, PAIRED_KEY, utcnow().isoformat())
    _drop_attempts(db)


def complete_pairing(db: Session, digest: str) -> bool:
    db.rollback()
    begin_write(db)
    if not _window_live(_stored(db, WINDOW_KEY)) or not _claim_digest(db, digest):
        db.rollback()
        return False
    _stamp_paired(db)
    db.commit()
    return True


def require_missing_key() -> None:
    if os.path.lexists(status.key_path()):
        raise Refused(409, EXISTS)


def prepare_enroll() -> str:
    route = status.remote_route()
    if route is None:
        raise Refused(409, TUNNEL)
    require_missing_key()
    return route


def _headers(db: Session) -> dict:
    revision, mine = status.schema_revision(db), status.machine_id(db)
    db.commit()
    return {"X-Maestro-Sync": f"{status.SYNC_PROTOCOL}:{revision}:{mine}"}


def _valid_key(key: object) -> bool:
    return (isinstance(key, str) and 0 < len(key) <= 4096 and key.isascii()
            and key.isprintable() and not any(char.isspace() for char in key))


def _enroll_client(route: str) -> httpx.Client:
    try:
        return http_client.new_client(
            base_url=settings.sync_remote_url, timeout=httpx.Timeout(30, connect=10),
            trust_env=route == "https", verify=True, follow_redirects=False)
    except OSError:
        raise Refused(409, "The certificate bundle in SSL_CERT_FILE can't be read.") from None
    except (ImportError, ValueError, httpx.InvalidURL):
        raise Refused(409, "The proxy settings in this machine's environment can't be used.") from None


def _query_text(query: object) -> str:
    if isinstance(query, bytes):
        return query.decode()
    return query if isinstance(query, str) else ""


def _post_enroll(http: httpx.Client, secret: str, peer: str):
    preview = http.build_request("POST", "/api/sync/enroll")
    header, wire, rid = seal.seal_request(
        secret, preview.method, preview.url.path, _query_text(preview.url.query), b"", peer,
        label=seal.ENROLL_TO_HOME)
    request = http.build_request(
        "POST", "/api/sync/enroll", content=wire,
        headers={seal.HEADER: header, "X-Maestro-Sync": peer})
    return http.send(request), rid


def _parsed_key(plain: bytes) -> str:
    try:
        body = json.loads(plain) if len(plain) <= 8192 else None
    except ValueError:
        body = None
    key = body.get("key") if isinstance(body, dict) else None
    if not _valid_key(key):
        raise Refused(409, ANSWER)
    return key


def _key_from(response: httpx.Response, secret: str, rid: str) -> str:
    if response.status_code == 404 and seal.HEADER not in response.headers:
        raise Refused(409, CLOSED, "closed")
    if response.status_code >= 500:
        raise Refused(503, "Laptop unreachable.")
    try:
        plain = seal.open_response(
            secret, rid, response.status_code, response.headers.get(seal.HEADER, ""),
            response.content, label=seal.ENROLL_TO_REMOTE)
    except seal.Broken:
        raise Refused(409, UNVERIFIED) from None
    return _parsed_key(plain)


def _fetch_key(route: str, secret: str, peer: str) -> str:
    try:
        with _enroll_client(route) as http:
            response, rid = _post_enroll(http, secret, peer)
    except (httpx.TransportError, httpx.InvalidURL):
        raise Refused(503, "Laptop unreachable.") from None
    return _key_from(response, secret, rid)


def _install_key(key: str) -> None:
    try:
        status.save_key(key)
    except FileExistsError:
        raise Refused(409, EXISTS) from None
    except OSError:
        raise Refused(500, DISK) from None


def enroll_here(db: Session, code: str) -> dict:
    route = prepare_enroll()
    secret = _code_secret(code)
    if secret is None:
        raise Refused(409, INVALID_CODE)
    _install_key(_fetch_key(route, secret, _headers(db)["X-Maestro-Sync"]))
    return {"ok": True}

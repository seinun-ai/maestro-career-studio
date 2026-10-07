"""Is sync set up, and which side is this? (split-ownership design, Part B)."""

import json
import logging
import os
import secrets
import stat
import threading
import uuid
from pathlib import Path

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models.setting import Setting

MACHINE_ID_KEY = "sync.machine_id"
STATE_KEY = "sync.state"
SYNC_PROTOCOL = 2
# The always-on copy's round state (local setting, never synced). ``since_home`` is home's opaque
# jobs cursor; ``acked_own`` is the highest local job revision the push has gone past; ``retry_own``
# maps a job home refused to the rounds it was refused, ``stuck_own`` one refused too often to the
# (fixed) reason home gave; ``last_outcome`` keeps a failure's classification during backoff;
# ``attempted_at`` is when the last round that reached home ended; times are ISO.
STATE_DEFAULTS: dict = {
    "paired": False, "last_ok": None, "last_error": None, "last_outcome": None,
    "failures": 0, "next_attempt_at": None,
    "since_home": "0", "acked_own": 0, "profile_rev": None, "runs_at": None,
    "retry_own": {}, "stuck_own": {}, "attempted_at": None,
}
_logger = logging.getLogger(__name__)
_KEY_READ_WARNING_LOGGED = False
_KEY_READ_WARNING_LOCK = threading.Lock()


def key_path() -> Path:
    return settings.sync_key_file or settings.settings_dir / "secrets" / "sync-key"


def read_key() -> str | None:
    """The shared key, or None when sync isn't set up. Never logged."""
    path = key_path()
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            fd = None
            key = handle.read().strip()
        return key or None
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError):
        _warn_unreadable_key()
        return None
    finally:
        if fd is not None:
            os.close(fd)


def enabled() -> bool:
    return read_key() is not None


def is_remote() -> bool:
    return enabled() and bool(settings.sync_remote_url)


LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")


def remote_route() -> str | None:
    """``tunnel`` for loopback http(s), ``https`` for any other https host, else None.

    A path past ``/``, a query, a fragment or userinfo is None: the seal binds the path that
    was sent, and a published mount only puts its own prefix back.
    """
    if not settings.sync_remote_url:
        return None
    try:
        url = httpx.URL(settings.sync_remote_url)
    except httpx.InvalidURL:
        return None
    return _route_of(url)


def _bare_address(url: httpx.URL) -> bool:
    if url.path not in ("", "/") or not url.host:
        return False
    if url.query or url.fragment or url.userinfo:
        return False
    return True


def _route_of(url: httpx.URL) -> str | None:
    if not _bare_address(url):
        return None
    if url.scheme in ("http", "https") and url.host in LOOPBACK_HOSTS:
        return "tunnel"
    if url.scheme == "https":
        return "https"
    return None


def mode() -> str:
    """"off", "home" or "remote" from one read of the key file (a list of rows reads it once)."""
    if read_key() is None:
        return "off"
    return "remote" if settings.sync_remote_url else "home"


def machine_id(db: Session) -> str:
    """This install's id, created on first use; local, never synced."""
    connection = db.connection()
    query = select(Setting.value).where(Setting.key == MACHINE_ID_KEY)
    # Read first: an INSERT, even one that does nothing, takes SQLite's write lock.
    existing = connection.execute(query).scalar_one_or_none()
    if existing is not None:
        return existing
    connection.execute(
        text(
            "INSERT INTO settings (key, value) VALUES (:key, :value) "
            "ON CONFLICT(key) DO NOTHING"
        ),
        {"key": MACHINE_ID_KEY, "value": uuid.uuid4().hex},
    )
    return connection.execute(query).scalar_one()


def schema_revision(db: Session) -> str:
    """The alembic revision this database is at; both copies must match before they sync."""
    return db.execute(text("SELECT version_num FROM alembic_version")).scalar() or "unknown"


def ensure_machine_id() -> str | None:
    """Persist this install's id at startup when sync is configured."""
    if not enabled():
        return None
    from app.db import SessionLocal

    with SessionLocal() as db:
        value = machine_id(db)
        db.commit()
        return value


def _warn_unreadable_key() -> None:
    global _KEY_READ_WARNING_LOGGED
    with _KEY_READ_WARNING_LOCK:
        if _KEY_READ_WARNING_LOGGED:
            return
        _KEY_READ_WARNING_LOGGED = True
        _logger.warning("The sync key file can't be read; sync is off.")


def create_key() -> Path:
    """Write a fresh key, 0600 in a 0700 directory, refusing to overwrite (the CLI's job)."""
    return save_key(secrets.token_urlsafe(32))


def save_key(key: str) -> Path:
    """Install a received key privately, never overwriting even an empty file or a symlink."""
    path = key_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(key + "\n")
    return path


def _tracked_fits(name: str, value: object) -> bool:
    """A dict of job id to attempts (``retry_own``) or to a reason (``stuck_own``)."""
    kind = int if name == "retry_own" else str
    return isinstance(value, dict) and all(
        isinstance(key, str) and isinstance(item, kind) and not isinstance(item, bool)
        for key, item in value.items())


def _state_value_fits(name: str, value: object) -> bool:
    default = STATE_DEFAULTS[name]
    if isinstance(default, dict):
        return _tracked_fits(name, value)
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, int):
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "profile_rev":
        return value is None or (isinstance(value, int) and not isinstance(value, bool))
    return value is None or isinstance(value, str)


def read_state(db: Session) -> dict:
    """The round state with defaults filled in; a damaged or unknown value reads as its default."""
    raw = db.scalar(select(Setting.value).where(Setting.key == STATE_KEY))
    try:
        stored = json.loads(raw) if raw else {}
    except ValueError:
        stored = {}
    stored = stored if isinstance(stored, dict) else {}
    return {name: stored[name] if name in stored and _state_value_fits(name, stored[name])
            else default for name, default in STATE_DEFAULTS.items()}


def update_state(db: Session, **changes) -> dict:
    """Merge ``changes`` into the round state and commit; returns the new state."""
    unknown = set(changes) - set(STATE_DEFAULTS)
    if unknown:
        raise ValueError(f"unknown sync state field: {sorted(unknown)[0]}")
    state = {**read_state(db), **changes}
    row = db.get(Setting, STATE_KEY)
    if row is None:
        db.add(Setting(key=STATE_KEY, value=json.dumps(state)))
    else:
        row.value = json.dumps(state)
    db.commit()
    return state

"""Is sync set up, and which side is this? (split-ownership design, Part B)."""

import logging
import os
import secrets
import stat
import threading
import uuid
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models.setting import Setting

MACHINE_ID_KEY = "sync.machine_id"
SYNC_PROTOCOL = 1
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
    path = key_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(secrets.token_urlsafe(32) + "\n")
    return path

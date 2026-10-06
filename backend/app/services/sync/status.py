"""Is sync set up, and which side is this? (split-ownership design, Part B)."""

import os
import secrets
import uuid
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.setting import Setting

MACHINE_ID_KEY = "sync.machine_id"
SYNC_PROTOCOL = 1


def key_path() -> Path:
    return settings.sync_key_file or settings.settings_dir / "secrets" / "sync-key"


def read_key() -> str | None:
    """The shared key, or None when sync isn't set up. Never logged."""
    path = key_path()
    if not path.is_file() or path.is_symlink():
        return None
    key = path.read_text(encoding="utf-8").strip()
    return key or None


def enabled() -> bool:
    return read_key() is not None


def is_remote() -> bool:
    return enabled() and bool(settings.sync_remote_url)


def machine_id(db: Session) -> str:
    """This install's id, created on first use; local, never synced."""
    row = db.get(Setting, MACHINE_ID_KEY)
    if row is None:
        row = Setting(key=MACHINE_ID_KEY, value=uuid.uuid4().hex)
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            row = db.get(Setting, MACHINE_ID_KEY)
            if row is None:
                raise
    return row.value


def create_key() -> Path:
    """Write a fresh key, 0600 in a 0700 directory, refusing to overwrite (the CLI's job)."""
    path = key_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(secrets.token_urlsafe(32) + "\n")
    return path

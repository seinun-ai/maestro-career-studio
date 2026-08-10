"""File-mirrored durable text settings (memory, persona).

Each setting is one row in the `settings` table plus a markdown mirror under
`settings_dir` so the text survives a wiped DB and stays hand-editable. The DB
row is the source of truth once it exists; the file lazily seeds it and is
rewritten on every set. Mirror I/O failures (e.g. running host-side while
`settings_dir` is a container path) degrade to DB-only with a warning.
"""

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.setting import Setting

logger = logging.getLogger(__name__)


def _file_path(filename: str) -> Path:
    return Path(settings.settings_dir) / filename


def _get_setting(session: Session, key: str) -> Setting | None:
    return session.scalar(select(Setting).where(Setting.key == key))


def get_text(key: str, filename: str, session: Session | None = None) -> str:
    owns_session = session is None
    session = session or SessionLocal()
    try:
        existing = _get_setting(session, key)
        if existing is not None:
            return existing.value or ""

        path = _file_path(filename)
        content = ""
        try:
            content = path.read_text(encoding="utf-8") if path.exists() else ""
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
        except OSError as exc:
            logger.warning("Text-setting mirror unavailable at %s: %s", path, exc)

        session.add(Setting(key=key, value=content))
        session.commit()
        return content
    finally:
        if owns_session:
            session.close()


def peek_text(key: str, filename: str, session: Session | None = None) -> str:
    """Read a setting without lazily seeding its DB row or file mirror."""
    owns_session = session is None
    session = session or SessionLocal()
    try:
        existing = _get_setting(session, key)
        if existing is not None:
            return existing.value or ""

        path = _file_path(filename)
        try:
            return path.read_text(encoding="utf-8") if path.exists() else ""
        except OSError as exc:
            logger.warning("Text-setting mirror unavailable at %s: %s", path, exc)
            return ""
    finally:
        if owns_session:
            session.close()


def set_text(key: str, filename: str, text: str, session: Session | None = None) -> str:
    owns_session = session is None
    session = session or SessionLocal()
    try:
        existing = _get_setting(session, key)
        if existing is None:
            session.add(Setting(key=key, value=text))
        else:
            existing.value = text
        session.commit()

        path = _file_path(filename)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except OSError as exc:
            logger.warning("Text-setting mirror not written at %s: %s", path, exc)
        return text
    finally:
        if owns_session:
            session.close()


def ensure_text(session: Session, key: str, filename: str) -> str:
    """Startup seeding: reconcile the DB row and its file mirror."""
    existing = _get_setting(session, key)
    path = _file_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)

    if existing is not None:
        if not path.exists():
            path.write_text(existing.value or "", encoding="utf-8")
        return existing.value or ""

    content = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(content, encoding="utf-8")
    session.add(Setting(key=key, value=content))
    session.commit()
    return content

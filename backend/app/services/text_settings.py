"""File-mirrored durable text settings (memory, persona).

Each setting is one row in the `settings` table plus a markdown mirror under
`settings_dir` so the text survives a wiped DB and stays hand-editable. The DB
row is the source of truth once it exists; the file lazily seeds it and is
rewritten on every set. Mirror I/O failures (e.g. running host-side while
`settings_dir` is a container path) degrade to DB-only with a warning.

`one_commit` holds several reads and writes to one transaction under SQLite's
write lock: an agent's merge (`PATCH /api/settings/*`) reads, merges and writes
with no other writer able to land in between.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, begin_write
from app.models.setting import Setting
from app.services.sync import hooks

logger = logging.getLogger(__name__)

# `session.info` key: the mirrors a `one_commit` block writes once it has committed.
_PENDING_MIRRORS = "text_settings_pending_mirrors"


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

        row = Setting(key=key, value=content)
        hooks.seed_setting(session, row)
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


def _write_mirror(filename: str, text: str) -> None:
    path = _file_path(filename)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        logger.warning("Text-setting mirror not written at %s: %s", path, exc)


def set_text(key: str, filename: str, text: str, session: Session | None = None) -> str:
    owns_session = session is None
    session = session or SessionLocal()
    try:
        existing = _get_setting(session, key)
        if existing is None:
            session.add(Setting(key=key, value=text))
        else:
            existing.value = text
        pending = session.info.get(_PENDING_MIRRORS)
        if pending is not None:
            # Inside `one_commit`: flushed so a later read in the block sees it, committed with the rest.
            session.flush()
            pending.append((filename, text))
            return text
        session.commit()
        _write_mirror(filename, text)
        return text
    finally:
        if owns_session:
            session.close()


@contextmanager
def one_commit(session: Session) -> Iterator[None]:
    """Run the block as ONE transaction under SQLite's write lock (`begin_write`): no other writer
    lands between its reads and its writes, every `set_text` in it flushes instead of committing,
    the block commits once at the end, and a failure anywhere rolls every write in it back. The
    file mirrors are written only after the commit. Reads inside use the `peek_*` readers: a first
    read that seeds a row (`get_text`) commits, which would end the transaction early, and a block
    in which anything committed is refused (RuntimeError, no mirrors written) rather than passed
    off as one transaction."""
    if _PENDING_MIRRORS in session.info:
        raise RuntimeError("one_commit blocks do not nest")
    begin_write(session)
    session.expire_all()
    transaction = session.get_transaction()
    mirrors: list[tuple[str, str]] = []
    session.info[_PENDING_MIRRORS] = mirrors
    try:
        yield
        if session.get_transaction() is not transaction:
            raise RuntimeError(
                "Something committed inside a one_commit block, releasing the write lock early; "
                "read with the peek_* readers and leave the commit to the block."
            )
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.info.pop(_PENDING_MIRRORS, None)
    for filename, text in mirrors:
        _write_mirror(filename, text)


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

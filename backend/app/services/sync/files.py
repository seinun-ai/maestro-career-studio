"""Portable paths and verified file transfer for sync bundles.

A bundle never carries a machine path. A file is named ``<root>:<relative path>`` and each side
joins it onto its own root. Every path is validated lexically (no ``..``, no absolute or drive
parts, no backslash or NUL), refused if any part of it below the root is a symlink, and checked to
resolve inside its root. Nothing here logs file names beyond error text or any file contents.
"""

import base64
import binascii
import hashlib
import os
import re
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path

from app.config import settings

ROOTS: dict[str, Callable[[], Path]] = {
    "applications": lambda: settings.applications_dir,
    "base_resumes": lambda: settings.base_resumes_dir,
    "kb_documents": lambda: settings.kb_documents_dir,
}

EVIDENCE_MAX_BYTES = 5 * 1024 * 1024
_PREVIEW_PNG = re.compile(r"page-\d+\.png")
_DRIVE = re.compile(r"[A-Za-z]:")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_FILE_MODE = 0o644


def _root(name: str) -> Path:
    """The named root as an absolute path, refused when the root itself is a symlink."""
    if name not in ROOTS:
        raise ValueError(f"unknown sync root: {name!r}")
    root = Path(os.path.abspath(ROOTS[name]()))
    if root.is_symlink():
        raise ValueError(f"sync root {name!r} is a symlink")
    return root


def _split(rel: str, *, allow_empty: bool) -> list[str]:
    """Validate a root-relative path and return its parts."""
    if rel == "":
        if allow_empty:
            return []
        raise ValueError("empty relative path")
    if "\\" in rel or "\x00" in rel or _DRIVE.match(rel):
        raise ValueError("unsafe relative path")
    parts = rel.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("unsafe relative path")
    return parts


def _checked(name: str, rel: str, *, allow_empty: bool) -> Path:
    """Absolute path for ``rel`` under the named root: no symlinks, resolves inside the root."""
    root = _root(name)
    current = root
    for part in _split(rel, allow_empty=allow_empty):
        current = current / part
        if current.is_symlink():
            raise ValueError("symlinks are not synced")
    resolved = current.resolve()
    if resolved != root.resolve() and not resolved.is_relative_to(root.resolve()):
        raise ValueError("path escapes its root")
    return current


def to_portable(path: str | os.PathLike | None) -> str | None:
    """'/app/applications/X/y.pdf' -> 'applications:X/y.pdf'.

    None for None and for a path under no root (dropped, never sent: it would leak a machine path
    and point nowhere on the other side). A symlink at or below the root raises ValueError.
    """
    if path is None:
        return None
    absolute = os.path.abspath(os.fspath(path))
    for name, getter in ROOTS.items():
        root = os.path.abspath(getter())
        if absolute.startswith(root.rstrip(os.sep) + os.sep):
            rel = absolute[len(root.rstrip(os.sep)) + 1 :]
            _checked(name, rel, allow_empty=False)
            return f"{name}:{rel}"
    return None


def from_portable(value: str | None) -> str | None:
    """Inverse of to_portable, joined onto THIS machine's root. Refuses '..', absolute parts,
    symlinks and an unknown root."""
    if value is None:
        return None
    name, sep, rel = value.partition(":")
    if not sep:
        raise ValueError("portable path has no root")
    return str(_checked(name, rel, allow_empty=False))


def _is_preview_png(directory: Path, filename: str) -> bool:
    return directory.name.endswith(".pages") and bool(_PREVIEW_PNG.fullmatch(filename))


def _is_evidence(rel: str) -> bool:
    return "evidence" in rel.split("/")[:-1]


def _read_regular(path: Path, *, limit: int) -> bytes | None:
    """The file's bytes, or None when it is not a regular file. Never blocks on a FIFO, never
    follows a symlink, and refuses a file that grows past ``limit`` while it is read."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise ValueError("file cannot be opened for sync") from exc
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            return None
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("files exceed the size limit")
    return data


def _walk(directory: Path) -> list[Path]:
    """Sorted entries under ``directory`` (files only); a symlink anywhere raises."""
    found = []
    for entry in sorted(os.scandir(directory), key=lambda e: e.name):
        if entry.is_symlink():
            raise ValueError("symlinks are not synced")
        if entry.is_dir(follow_symlinks=False):
            found.extend(_walk(Path(entry.path)))
        elif entry.is_file(follow_symlinks=False):
            found.append(Path(entry.path))
    return found


def _entry(name: str, root: Path, path: Path, remaining: int) -> tuple[dict, int] | None:
    """One packed file and the bytes it used, or None for a skipped file."""
    if _is_preview_png(path.parent, path.name):
        return None
    rel = path.relative_to(root).as_posix()
    _split(rel, allow_empty=False)
    limit = min(remaining, EVIDENCE_MAX_BYTES) if _is_evidence(rel) else remaining
    data = _read_regular(path, limit=limit)
    if data is None:
        return None
    packed = {
        "path": f"{name}:{rel}",
        "sha256": hashlib.sha256(data).hexdigest(),
        "b64": base64.b64encode(data).decode("ascii"),
    }
    return packed, len(data)


def pack_dir(root_name: str, rel_dir: str, *, max_bytes: int) -> list[dict]:
    """[{path, sha256, b64}] for every regular file under ``rel_dir`` of the named root.

    Symlinks raise; non-regular files and regenerated page-preview PNGs are skipped. The total
    must stay within ``max_bytes`` and one evidence file within 5 MiB, or ValueError.
    """
    if max_bytes < 0:
        raise ValueError("max_bytes must not be negative")
    directory = _checked(root_name, rel_dir, allow_empty=True)
    if not directory.is_dir():
        return []
    root = _root(root_name)
    packed: list[dict] = []
    remaining = max_bytes
    for path in _walk(directory):
        result = _entry(root_name, root, path, remaining)
        if result is not None:
            packed.append(result[0])
            remaining -= result[1]
    return packed


def _target(value: object) -> tuple[str, str]:
    if not isinstance(value, str):
        raise ValueError("portable path must be a string")
    name, sep, rel = value.partition(":")
    if not sep:
        raise ValueError("portable path has no root")
    return name, rel


def _decode(entry: dict, rel: str) -> bytes:
    """Decode and verify one incoming file's bytes (base64, evidence size, sha256)."""
    sha256, b64 = entry.get("sha256"), entry.get("b64")
    if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
        raise ValueError("malformed sha256")
    if not isinstance(b64, str) or not b64.isascii():
        raise ValueError("malformed base64")
    evidence = _is_evidence(rel)
    if evidence and len(b64) > (EVIDENCE_MAX_BYTES // 3 + 1) * 4:
        raise ValueError("evidence file exceeds the size limit")
    try:
        data = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("malformed base64") from exc
    if evidence and len(data) > EVIDENCE_MAX_BYTES:
        raise ValueError("evidence file exceeds the size limit")
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError("sha256 mismatch")
    return data


def _write_atomic(target: Path, data: bytes) -> None:
    """Temp file beside the target, fsync, then replace; the temp is removed on any failure."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix=".sync-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fchmod(handle.fileno(), _FILE_MODE)
            os.fsync(handle.fileno())
        os.replace(temp, target)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def unpack(files: list[dict]) -> None:
    """Write each file atomically under its root. Every entry is fully verified (path, base64,
    sha256, evidence size) before the first byte is written."""
    verified = []
    for entry in files:
        name, rel = _target(entry.get("path"))
        _checked(name, rel, allow_empty=False)
        verified.append((name, rel, _decode(entry, rel)))
    for name, rel, data in verified:
        # Re-check just before writing: the tree may have changed since validation.
        _write_atomic(_checked(name, rel, allow_empty=False), data)

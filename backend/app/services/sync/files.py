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
import unicodedata
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
_TEMP_FILE = re.compile(r"\.sync-.*\.tmp")
_MAX_COMPONENT_BYTES = 255
_MAX_REL_BYTES = 1024


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
    try:
        sizes = [len(part.encode("utf-8")) for part in parts]
    except UnicodeEncodeError:
        raise ValueError("unsafe relative path") from None
    if max(sizes) > _MAX_COMPONENT_BYTES or sum(sizes) + len(parts) - 1 > _MAX_REL_BYTES:
        raise ValueError("relative path is too long")
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
        # A stored path may use the resolved form of the root (``Path.resolve()``), so a root
        # reached through a symlinked parent matches both spellings. Only the ROOT is resolved.
        for root in dict.fromkeys((os.path.abspath(getter()), os.path.realpath(getter()))):
            prefix = root.rstrip(os.sep) + os.sep
            if absolute.startswith(prefix):
                rel = absolute[len(prefix) :]
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
    """The file's bytes, or None when it is not a regular file or cannot be read. Never blocks on
    a FIFO, never follows a symlink, and refuses a file that grows past ``limit`` while it is read."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                return None
            data = handle.read(limit + 1)
    except OSError:
        return None
    if len(data) > limit:
        raise ValueError("files exceed the size limit")
    return data


def _walk(directory: Path) -> tuple[list[Path], int]:
    """Sorted files under ``directory`` and the count of other non-directory entries (FIFOs,
    sockets); a symlink anywhere raises."""
    found: list[Path] = []
    others = 0
    for entry in sorted(os.scandir(directory), key=lambda e: e.name):
        if entry.is_symlink():
            raise ValueError("symlinks are not synced")
        if entry.is_dir(follow_symlinks=False):
            nested, nested_others = _walk(Path(entry.path))
            found.extend(nested)
            others += nested_others
        elif entry.is_file(follow_symlinks=False):
            found.append(Path(entry.path))
        else:
            others += 1
    return found, others


def _regenerated(path: Path) -> bool:
    """Files that are never sent and never counted as skipped: page previews and our own temps."""
    return _is_preview_png(path.parent, path.name) or bool(_TEMP_FILE.fullmatch(path.name))


def _entry(name: str, root: Path, path: Path, remaining: int) -> tuple[dict, int] | None:
    """One packed file and the bytes it used, or None for a file that cannot be sent."""
    rel = path.relative_to(root).as_posix()
    try:
        _split(rel, allow_empty=False)
    except ValueError:
        return None
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


def pack_dir_with_skips(root_name: str, rel_dir: str, *, max_bytes: int) -> tuple[list[dict], int]:
    """([{path, sha256, b64}], skipped) for every regular file under ``rel_dir`` of the named root.

    Symlinks raise. Files that cannot be sent are skipped and counted: a backslash or an over-long
    name, a non-regular file, an unreadable file. Regenerated page-preview PNGs and leftover
    ``.sync-*.tmp`` files are skipped silently. The total must stay within ``max_bytes`` and one
    evidence file within 5 MiB, or ValueError.
    """
    if max_bytes < 0:
        raise ValueError("max_bytes must not be negative")
    directory = _checked(root_name, rel_dir, allow_empty=True)
    if not directory.is_dir():
        return [], 0
    root = _root(root_name)
    paths, skipped = _walk(directory)
    packed: list[dict] = []
    remaining = max_bytes
    for path in paths:
        if _regenerated(path):
            continue
        result = _entry(root_name, root, path, remaining)
        if result is None:
            skipped += 1
            continue
        packed.append(result[0])
        remaining -= result[1]
    return packed, skipped


def pack_dir(root_name: str, rel_dir: str, *, max_bytes: int) -> list[dict]:
    """The files of ``pack_dir_with_skips`` without the skipped count."""
    return pack_dir_with_skips(root_name, rel_dir, max_bytes=max_bytes)[0]


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


class _Claims:
    """Paths a bundle will write, compared case-folded and NFC-normalised so that two entries that
    could land on one file (or a file and its own parent directory) are refused up front."""

    def __init__(self) -> None:
        self._files: set[tuple[str, ...]] = set()
        self._dirs: set[tuple[str, ...]] = set()

    @staticmethod
    def _fold(part: str) -> str:
        return unicodedata.normalize("NFC", unicodedata.normalize("NFC", part).casefold())

    def add(self, name: str, rel: str) -> None:
        key = tuple(self._fold(part) for part in (name, *rel.split("/")))
        parents = [key[:i] for i in range(1, len(key))]
        if key in self._files:
            raise ValueError("duplicate file entry")
        if key in self._dirs or any(parent in self._files for parent in parents):
            raise ValueError("file entries overlap")
        self._files.add(key)
        self._dirs.update(parents)


def _check_target(root: Path, path: Path) -> None:
    """Every existing parent below the root is a directory and the target is not one."""
    current = root
    for part in (None, *path.relative_to(root).parts[:-1]):
        current = current if part is None else current / part
        if os.path.lexists(current) and not current.is_dir():
            raise ValueError("a parent of the file is not a directory")
    if path.is_dir():
        raise ValueError("the file's name is already a directory")


def _verify_entry(entry: object, claims: _Claims) -> tuple[str, str, bytes]:
    """Fully check one incoming file; ValueError (naming no path) for anything unwritable."""
    if not isinstance(entry, dict):
        raise ValueError("file entry must be an object")
    name, rel = _target(entry.get("path"))
    try:
        path = _checked(name, rel, allow_empty=False)
        claims.add(name, rel)
        _check_target(_root(name), path)
    except OSError:
        raise ValueError("file path cannot be checked") from None
    return name, rel, _decode(entry, rel)


def _verify_all(files: list[dict], max_bytes: int | None) -> list[tuple[str, str, bytes]]:
    claims = _Claims()
    verified = []
    total = 0
    for entry in files:
        item = _verify_entry(entry, claims)
        total += len(item[2])
        if max_bytes is not None and total > max_bytes:
            raise ValueError("files exceed the size limit")
        verified.append(item)
    return verified


def unpack(files: list[dict], *, max_bytes: int | None = None) -> None:
    """Write each file atomically under its root. Every entry is fully verified (shape, path,
    duplicates and overlaps, existing parents, base64, sha256, evidence size, optional total
    ``max_bytes`` of decoded data) before the first byte is written."""
    for name, rel, data in _verify_all(files, max_bytes):
        # Re-check just before writing: the tree may have changed since validation.
        _write_atomic(_checked(name, rel, allow_empty=False), data)

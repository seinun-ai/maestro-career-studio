"""Compare artifact folders the way a disk does, not the way a string does.

APFS and NTFS ignore case and Unicode form, and ``os.path.realpath`` keeps whatever spelling it
was given, so ``Acme_x`` and ``acme_x`` are two strings and one folder. Folders are compared by
their case-folded, NFC-normalised real path and, when both exist, by inode, so a bundle cannot
write into (or have a later tombstone remove) a folder that belongs to another job.
"""

import os
import unicodedata


def _key(path: str) -> str:
    real = unicodedata.normalize("NFC", os.path.realpath(path))
    return unicodedata.normalize("NFC", real.casefold())


def same_file(first: str, second: str) -> bool:
    """True when both exist and are the same directory entry on disk (device and inode)."""
    try:
        return os.path.samestat(os.stat(first), os.stat(second))
    except OSError:
        return False


def _within(child: str, parent: str) -> bool:
    return child == parent or child.startswith(parent.rstrip(os.sep) + os.sep)


def overlaps(first: str, second: str) -> bool:
    """The folders are one, or one sits inside the other."""
    one, other = _key(first), _key(second)
    return _within(one, other) or _within(other, one) or same_file(first, second)


def lies_below(path: str, folder: str) -> bool:
    """``path`` is strictly under ``folder``, spelled exactly (the case a bundle names is the case
    it is written in)."""
    prefix = os.path.abspath(folder).rstrip(os.sep) + os.sep
    return os.path.abspath(path).startswith(prefix)

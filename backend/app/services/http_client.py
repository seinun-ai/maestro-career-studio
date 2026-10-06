"""Build httpx clients that survive a malformed proxy environment.

httpx reads NO_PROXY / HTTP(S)_PROXY when a Client is built, and a NO_PROXY entry
it cannot parse raises `httpx.InvalidURL`. The usual culprit is a bracketed IPv6
literal (`[fd8b:1234::1]`), which some VM images set. Raised at import it kept
the whole backend from starting, so every long-lived client Maestro builds comes
from `new_client` instead of `httpx.Client`.

Clients built by libraries (the OpenAI SDK, the embedding model's first download)
never pass through `new_client`, so the backend and the MCP server also call
`repair_proxy_env` once at startup; the processes they start inherit the fix.
"""

import logging
import os
import re
import threading
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_NO_PROXY_VARS = ("NO_PROXY", "no_proxy")
_BRACKETED = re.compile(r"^\[([^\[\]]*)\]$")
# The repair swaps os.environ for the length of one build; the lock keeps two
# builds from restoring each other's half-swapped values.
_ENV_LOCK = threading.Lock()
_warned: set[str] = set()


def _clean_entry(entry: str) -> str | None:
    """`[::1]` -> `::1` (httpx re-brackets an IPv6 literal itself); None when the
    entry is still malformed. Hostnames, IPv4 and `::1` pass through unchanged."""
    entry = entry.strip()
    bracketed = _BRACKETED.match(entry)
    if bracketed:
        return bracketed.group(1)
    return None if ("[" in entry or "]" in entry) else entry


def _clean_no_proxy(value: str) -> str:
    kept = (_clean_entry(entry) for entry in value.split(","))
    return ",".join(entry for entry in kept if entry is not None)


def _repaired_env() -> dict[str, str]:
    """The NO_PROXY variables that the cleaning changes, with their new values."""
    changed = {}
    for name in _NO_PROXY_VARS:
        value = os.environ.get(name)
        if value is not None and _clean_no_proxy(value) != value:
            changed[name] = _clean_no_proxy(value)
    return changed


def _warn_once(names: list[str]) -> None:
    fresh = [name for name in names if name not in _warned]
    if not fresh:
        return
    _warned.update(fresh)
    logger.warning(
        "Ignored malformed entries in %s: httpx could not parse them (a bracketed IPv6 "
        "literal like [::1] is the usual cause). Write them without brackets.",
        " and ".join(fresh))


def _build_repaired(kwargs: dict[str, Any], original: httpx.InvalidURL) -> httpx.Client:
    with _ENV_LOCK:
        repaired = _repaired_env()
        if not repaired:
            raise original  # not a NO_PROXY problem, so nothing here can fix it
        saved = {name: os.environ[name] for name in repaired}
        os.environ.update(repaired)
        try:
            client = httpx.Client(**kwargs)
        finally:
            os.environ.update(saved)
    _warn_once(sorted(repaired))
    return client


def new_client(**kwargs: Any) -> httpx.Client:
    """`httpx.Client(**kwargs)`, retried once with unparseable NO_PROXY entries fixed."""
    try:
        return httpx.Client(**kwargs)
    except httpx.InvalidURL as exc:
        return _build_repaired(kwargs, exc)


def repair_proxy_env() -> None:
    """Rewrite unparseable NO_PROXY entries in this process's environment, once.

    Only this process and the ones it starts see the change, never the user's shell."""
    with _ENV_LOCK:
        repaired = _repaired_env()
        os.environ.update(repaired)
    if repaired:
        _warn_once(sorted(repaired))

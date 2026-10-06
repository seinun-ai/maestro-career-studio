"""Sealed sync messages: the key never travels (docs/plans/2026-10-06-sealed-sync-design.md)."""

import base64
import hashlib
import hmac
import os
import threading
import time
from dataclasses import dataclass
from typing import NoReturn
from urllib.parse import parse_qsl, urlencode

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

VERSION = "2"
SKEW_SECONDS = 300
REPLAY_SECONDS = 600
TO_HOME = b"maestro-sync v2 remote->home"
TO_REMOTE = b"maestro-sync v2 home->remote"
ENROLL_TO_HOME = b"maestro-sync v2 enroll remote->home"
ENROLL_TO_REMOTE = b"maestro-sync v2 enroll home->remote"
HEADER = "X-Maestro-Seal"
_SALT = b"maestro-sync"
_HEADER_INFO = b" header"
_DUMMY_AAD = b"maestro-sync reject"
_DUMMY_MAC = b"\x00" * 16
_RID_LEN = 16
_NONCE_LEN = 12
_MAC_LEN = 16
_TAG_LEN = 16
_REPLAY_CAP = 100_000
_KEY_CAP = 16
_TS_MAX = 12
_KEYS: dict[tuple[str, bytes], bytes] = {}
_KEYS_LOCK = threading.Lock()


class Broken(Exception):
    """Any seal failure. Carries no detail: callers answer a bare 404."""


@dataclass(frozen=True)
class HeaderOk:
    rid: str
    nonce: bytes
    aad: bytes
    header_box: bytes


@dataclass(frozen=True)
class _Parsed:
    ts: str
    rid: str
    nonce: bytes
    mac: bytes
    boxed: bytes


def derive(secret: str, label: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=_SALT, info=label).derive(
        secret.encode("utf-8"))


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, TypeError):
        raise Broken from None


def canonical_query(raw: str) -> str:
    return urlencode(sorted(parse_qsl(raw, keep_blank_values=True)))


def request_aad(method: str, path: str, query: str, ts: str, rid: str, peer: str) -> bytes:
    return "\n".join([method.upper(), path, canonical_query(query), ts, rid, peer]).encode()


def _key(secret: str, label: bytes) -> bytes:
    slot = (secret, label)
    with _KEYS_LOCK:
        found = _KEYS.get(slot)
        if found is not None:
            return found
        return _store_key(slot, secret, label)


def _store_key(slot: tuple[str, bytes], secret: str, label: bytes) -> bytes:
    found = derive(secret, label)
    _KEYS[slot] = found
    if len(_KEYS) > _KEY_CAP:
        del _KEYS[next(iter(_KEYS))]
    return found


def _mac(secret: str, label: bytes, aad: bytes) -> bytes:
    digest = hmac.new(_key(secret, label + _HEADER_INFO), aad, hashlib.sha256).digest()
    return digest[:_MAC_LEN]


def _encrypt(secret: str, label: bytes, nonce: bytes, body: bytes, aad: bytes) -> bytes:
    return AESGCM(_key(secret, label)).encrypt(nonce, body, aad)


def _decrypt(secret: str, label: bytes, nonce: bytes, data: bytes, aad: bytes) -> bytes:
    try:
        return AESGCM(_key(secret, label)).decrypt(nonce, data, aad)
    except (InvalidTag, ValueError):
        raise Broken from None


def _nonce() -> bytes:
    # A few dozen messages a round, about 10**5 a year under one key — far
    # below the 2**32 random-nonce guidance for AES-GCM.
    return os.urandom(_NONCE_LEN)


def _shape(parts: list[str]) -> bool:
    if len(parts) != 6 or parts[0] != VERSION:
        return False
    stamp = parts[1]
    return stamp.isascii() and stamp.isdigit() and len(stamp) <= _TS_MAX


def _decode_piece(text: str) -> bytes | None:
    try:
        return _unb64(text)
    except Broken:
        return None


def _decode_pieces(parts: list[str]) -> tuple[bytes, bytes, bytes, bytes] | None:
    rid = _decode_piece(parts[2])
    nonce = _decode_piece(parts[3])
    mac = _decode_piece(parts[4])
    boxed = _decode_piece(parts[5]) if parts[5] else b""
    if rid is None or nonce is None or mac is None or boxed is None:
        return None
    return rid, nonce, mac, boxed


def _lengths(pieces: tuple[bytes, bytes, bytes, bytes]) -> bool:
    rid, nonce, mac, boxed = pieces
    if len(rid) != _RID_LEN or len(nonce) != _NONCE_LEN or len(mac) != _MAC_LEN:
        return False
    return not boxed or len(boxed) >= _TAG_LEN


def _parsed_header(header: str) -> _Parsed | None:
    parts = header.split(".")
    if not _shape(parts):
        return None
    pieces = _decode_pieces(parts)
    if pieces is None or not _lengths(pieces):
        return None
    _rid, nonce, mac, boxed = pieces
    return _Parsed(parts[1], parts[2], nonce, mac, boxed)


def _reject_unverified(secret: str, label: bytes) -> NoReturn:
    hmac.compare_digest(_mac(secret, label, _DUMMY_AAD), _DUMMY_MAC)
    raise Broken


def _usable(secret: str, label: bytes, header: str, now: float) -> _Parsed:
    parsed = _parsed_header(header)
    if parsed is not None and abs(now - int(parsed.ts)) <= SKEW_SECONDS:
        return parsed
    _reject_unverified(secret, label)


class ReplayCache:
    """Request ids seen in the last ten minutes. Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._expiry: dict[str, float] = {}
        self._soonest = float("inf")

    def seen(self, rid: str, now: float, *, until: float | None = None) -> bool:
        with self._lock:
            self._prune(now)
            if rid in self._expiry:
                return True
            expiry = now + REPLAY_SECONDS if until is None else until
            self._remember(rid, expiry)
            return False

    def _remember(self, rid: str, expiry: float) -> None:
        self._expiry[rid] = expiry
        if expiry < self._soonest:
            self._soonest = expiry
        self._trim()

    def _prune(self, now: float) -> None:
        # Every stored expiry is still ahead of now, so nothing can be due.
        if not self._expiry or now < self._soonest:
            return
        self._drop_expired(now)

    def _drop_expired(self, now: float) -> None:
        expired = [rid for rid, expiry in self._expiry.items() if expiry <= now]
        for rid in expired:
            del self._expiry[rid]
        self._reset_soonest()

    def _trim(self) -> None:
        if len(self._expiry) <= _REPLAY_CAP:
            return
        del self._expiry[next(iter(self._expiry))]
        self._reset_soonest()

    def _reset_soonest(self) -> None:
        self._soonest = min(self._expiry.values(), default=float("inf"))


def _hold_until(ts: str) -> float:
    """Keep the rid through the stamp's far skew edge plus the replay window."""
    return int(ts) + SKEW_SECONDS + REPLAY_SECONDS


def _replayed(replay: ReplayCache | None, rid: str, now: float, ts: str) -> bool:
    if replay is None:
        return False
    return replay.seen(rid, now, until=_hold_until(ts))


def _as_broken(fn):
    try:
        return fn()
    except Broken:
        raise
    except Exception:
        pass
    # Outside the handler, so a parser error is not chained: its text can echo header bytes.
    raise Broken


def _place(body: bytes, ciphertext: bytes) -> tuple[str, bytes]:
    if body:
        return "", ciphertext
    return _b64(ciphertext), b""


def seal_request(
    secret: str, method: str, path: str, query: str, body: bytes, peer: str, *,
    label: bytes = TO_HOME, now: float | None = None,
) -> tuple[str, bytes, str]:
    moment = time.time() if now is None else now
    ts = str(int(moment))
    rid = _b64(os.urandom(_RID_LEN))
    nonce = _nonce()
    aad = request_aad(method, path, query, ts, rid, peer)
    ciphertext = _encrypt(secret, label, nonce, body, aad)
    boxed, wire = _place(body, ciphertext)
    header = f"{VERSION}.{ts}.{rid}.{_b64(nonce)}.{_b64(_mac(secret, label, aad))}.{boxed}"
    return header, wire, rid


def check_header(
    secret: str, method: str, path: str, query: str, header: str, peer: str, *,
    replay: ReplayCache | None, label: bytes = TO_HOME, now: float | None = None,
) -> HeaderOk:
    def verify() -> HeaderOk:
        moment = time.time() if now is None else now
        parsed = _usable(secret, label, header, moment)
        aad = request_aad(method, path, query, parsed.ts, parsed.rid, peer)
        if not hmac.compare_digest(_mac(secret, label, aad), parsed.mac):
            raise Broken
        if _replayed(replay, parsed.rid, moment, parsed.ts):
            raise Broken
        return HeaderOk(parsed.rid, parsed.nonce, aad, parsed.boxed)

    return _as_broken(verify)


def open_request(
    secret: str, ok: HeaderOk, wire_body: bytes, *, label: bytes = TO_HOME,
) -> bytes:
    def verify() -> bytes:
        if bool(ok.header_box) == bool(wire_body):
            raise Broken
        return _decrypt(secret, label, ok.nonce, ok.header_box or wire_body, ok.aad)

    return _as_broken(verify)


def _response_aad(rid: str, status: int) -> bytes:
    return f"{rid}\n{status}".encode()


def seal_response(
    secret: str, rid: str, status: int, body: bytes, *, label: bytes = TO_REMOTE,
) -> tuple[str, bytes]:
    nonce = _nonce()
    ciphertext = _encrypt(secret, label, nonce, body, _response_aad(rid, status))
    return f"{VERSION}.{_b64(nonce)}", ciphertext


def _response_nonce(header: str) -> bytes | None:
    parts = header.split(".")
    if len(parts) != 2 or parts[0] != VERSION or not parts[1]:
        return None
    try:
        nonce = _unb64(parts[1])
    except Broken:
        return None
    if len(nonce) != _NONCE_LEN:
        return None
    return nonce


def open_response(
    secret: str, rid: str, status: int, header: str, wire_body: bytes, *,
    label: bytes = TO_REMOTE,
) -> bytes:
    def verify() -> bytes:
        nonce = _response_nonce(header)
        if nonce is None:
            raise Broken
        return _decrypt(secret, label, nonce, wire_body, _response_aad(rid, status))

    return _as_broken(verify)

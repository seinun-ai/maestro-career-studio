# Sealed Sync Over HTTPS Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Sync works for an always-on copy whose only way out is HTTPS through a TLS-decrypting
proxy: every sync message is sealed with keys derived from the sync key, the laptop publishes only
`/api/sync` (Tailscale Funnel), and pairing uses a one-time code.

**Design:** `docs/plans/2026-10-06-sealed-sync-design.md` (approved 2026-10-06). Background: phase
4b (`docs/plans/2026-10-06-split-ownership-sync*.md`, Tasks 1-18; Task 18 = commit 16d794a2).

**Architecture:** A new `services/sync/seal.py` holds the crypto (HKDF-SHA256 key derivation,
AES-256-GCM, request/response envelopes, replay cache). Home's sync route class unseals each
request before any handler runs and seals each response; anything that fails is a bare 404. The
remote's client seals/opens around every call and picks its route by URL (loopback = tunnel,
direct; non-loopback HTTPS = through the environment proxy). Pairing replaces Task 18's tunnel-only
enroll with a code-derived seal.

**Tech Stack:** Python 3.12, FastAPI/Starlette, `cryptography` (already locked at 50.0.0 as a
transitive dependency; make it direct), httpx, SQLite; Next.js 16 for the card; bash for sync.sh.

**Ground rules (every task):**
- Read `SYSTEM.md`, the design, and the code you change first. TDD: failing test first.
- Never log, echo, store or return the sync key, a pairing code, a seal's plaintext, a bundle
  value or a local path. Errors after unsealing stay fixed sentences.
- With no key file, nothing changes: every `/api/sync/*` route is a 404.
- The repo is PUBLIC: no agent product names, no real hostnames (write `<mac>.<tailnet>.ts.net`).
- Python `/opt/anaconda3/bin/python3` from `backend/`; suite with `-n auto --dist loadfile`.
- Functions ≤ complexity 10, ≤ 50 lines, ≤ 5 params.

---

## Task 1: The seal

**Files:**
- Create: `backend/app/services/sync/seal.py`
- Modify: `backend/pyproject.toml` (add `cryptography` to the base dependencies at the locked
  version range; `requirements.lock` already pins 50.0.0 — regenerate it only if the check in the
  Dockerfile comment demands it, and say so)
- Test: `backend/tests/sync/test_seal.py`

**The format (fixed):**
- Keys: `derive(secret, label) = HKDF(SHA256, length=32, salt=b"maestro-sync", info=label)`.
  Labels: `b"maestro-sync v2 remote->home"`, `b"maestro-sync v2 home->remote"`,
  `b"maestro-sync v2 enroll remote->home"`, `b"maestro-sync v2 enroll home->remote"`.
- Request header `X-Maestro-Seal: 2.<ts>.<rid>.<nonce>[.<tag>]` (base64url, no padding):
  `ts` = Unix seconds; `rid` = 16 random bytes; `nonce` = 12 random bytes. When the plaintext body
  is empty the whole ciphertext (16-byte tag) rides in the header's 5th field and the request has
  no body (some proxies drop GET bodies); otherwise the body is the ciphertext.
- Request AAD: `"\n".join([METHOD, path, canonical_query, ts, rid, x_maestro_sync]).encode()`,
  where `canonical_query` is the query string with keys sorted (`urllib.parse.urlencode(sorted(
  parse_qsl(raw, keep_blank_values=True)))`) and `x_maestro_sync` is the `X-Maestro-Sync` header
  value (protocol:schema:machine id) — bound so it can't be swapped.
- Response header `X-Maestro-Seal: 2.<nonce>`; body = ciphertext of the JSON body; AAD =
  `f"{rid}\n{status_code}".encode()`, so a response can't be replayed onto another request or
  status.

```python
"""Sealed sync messages: the key never travels (docs/plans/2026-10-06-sealed-sync-design.md)."""

import base64
import os
import threading
import time
from dataclasses import dataclass, field
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


class Broken(Exception):
    """Any seal failure. Carries no detail: callers answer a bare 404."""


def derive(secret: str, label: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"maestro-sync", info=label).derive(
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
```

Then write (you choose the helper split; names below are FIXED):
- `seal_request(secret, method, path, query, body: bytes, peer: str, *, label=TO_HOME,
  now: float | None = None) -> tuple[str, bytes, str]` → `(header, wire_body, rid)`.
- `open_request(secret, method, path, query, header: str, wire_body: bytes, peer: str, *,
  label=TO_HOME, now=None, replay: "ReplayCache | None") -> tuple[bytes, str]` →
  `(plaintext, rid)`; raises `Broken` on: wrong version, malformed header, ts outside ±SKEW,
  a body present when the tag rode in the header (or vice versa), `InvalidTag`, or a rid already
  in `replay`. Register the rid only after the tag verifies.
- `seal_response(secret, rid, status, body: bytes, *, label=TO_REMOTE) -> tuple[str, bytes]`.
- `open_response(secret, rid, status, header, wire_body, *, label=TO_REMOTE) -> bytes`.
- `class ReplayCache`: thread-safe dict rid→expiry with `seen(rid, now) -> bool` (adds when new,
  prunes expired entries on each call, caps at 100 000 entries by dropping the oldest).

**Tests (fail first):** round trip for request (with and without body) and response; each
rejection raises `Broken` with an empty message: tampered body, tampered header field, tampered
AAD component (method, path, query order-independent but value-sensitive, ts, peer), wrong
secret, wrong direction label, stale ts (+/− 301 s), replayed rid, malformed base64, version 1;
a response opened with another rid or status fails; `derive` is deterministic and labels differ;
`repr`/`str` of `Broken` never contains a sentinel secret; the replay cache prunes and caps.

---

## Task 2: Home unseals and seals every sync route

**Files:**
- Modify: `backend/app/routers/sync.py` (the route class `_SyncRoute`, `_require_sync`,
  `_check_key`, `_read_body`, `_json_body`), `backend/app/services/sync/status.py`
  (`SYNC_PROTOCOL = 2`)
- Modify: `backend/tests/sync/conftest.py` (a `sealed` test helper — see below) and every test
  that calls home's sync routes with a bearer key (`tests/sync/test_home_endpoints.py`,
  `test_two_machines.py`, others found by `grep -rn "Bearer" backend/tests`)
- Test: `backend/tests/sync/test_sealed_home.py`

**Behavior:**
1. Order per request: 404 when sync is off (no key, or this copy is remote) → 403 for an `Origin`
   header (before the body is read) → read the body under the existing caps/timeout → **open the
   seal** (`open_request` with the shared module-level `ReplayCache`) → version check (the
   `X-Maestro-Sync` header, now authenticated by the AAD) → the lock → the handler.
2. **Any seal failure → a bare 404**: empty body, no headers beyond the minimum, the same status
   as "sync is off". Do the same amount of work for a missing header as for a bad tag (derive the
   key and attempt a decrypt of a fixed dummy) so timing doesn't tell "no seal" from "bad seal".
   Count failures in a module-level window: after 30 failures in 60 s, answer every sync request
   with the bare 404 for 60 s without trying to open it (log one fixed line once per window).
3. The bearer check is removed; an `Authorization` header is ignored (a request carrying only the
   old bearer key is a bare 404).
4. Handlers receive the plaintext body exactly as before (inject it so `_json_body` keeps working;
   e.g. store it on `request.state` and read it from there).
5. **Every response is sealed** (status, body), including 409/413/422/500 refusals and the
   sanitized 422, with `seal_response(secret, rid, status, body)`. Only the bare 404 and the
   Origin 403 go out unsealed.
6. `SYNC_PROTOCOL = 2`.

**Test helper (`tests/sync/conftest.py`):** `sealed(client, method, path, *, json=None,
params=None, key=…, peer=…)` that seals with `seal_request`, sends with the TestClient, and opens
the response with `open_response` (returns `(status, parsed_json)`); plus `raw(...)` for
unsealed calls. Rewrite existing tests to use it — keep every assertion's meaning.

**Tests:** every route in `router.routes` answers a bare 404 (empty body) when unsealed, when
sealed with a wrong key, when carrying only `Authorization: Bearer <key>`, and when replayed; the
Origin 403 still comes before the body is read; a sealed request works end to end and its response
opens; a refusal (e.g. version mismatch 409) comes back sealed and readable by the client only;
the failure limiter trips at 30 and resets; no log record (caplog DEBUG) contains a sentinel from
a bundle, the key or the seal header.

---

## Task 3: The remote's client seals, and picks its route by URL

**Files:**
- Modify: `backend/app/services/sync/round.py` (`_call`, `_headers`, client construction),
  `backend/app/services/sync/status.py` (replace `remote_is_own_tunnel()` with
  `remote_route() -> "tunnel" | "https" | None`)
- Test: `backend/tests/sync/test_round.py` (adapt the fake home to speak seals — it calls home's
  route functions; make it use the same `open_request`/`seal_response`), new
  `backend/tests/sync/test_remote_route.py`

**Behavior:**
- `remote_route()`: `"tunnel"` for `http://` or `https://` on 127.0.0.1/::1/localhost;
  `"https"` for `https://` on any other host; `None` otherwise (plain `http://` to a non-loopback
  host, or anything unparseable). A round with `None` is a `needs_person` skip with the fixed
  sentence "The laptop's address must be this machine's own tunnel or an https:// address."
- Client: `"tunnel"` → `trust_env=False` (as today); `"https"` → `trust_env=True` (the
  environment proxy is the only way out of a sandbox; the seal makes it harmless), `verify=True`.
- Every call: `seal_request` on the way out (path = the URL path as sent, query = the encoded
  params), `open_response` on the way back; a response that fails to open is a transient
  "The laptop's answer couldn't be verified." (never the body).
- Remove the `Authorization` header.

**Tests:** `remote_route` table (loopback http/https, ::1, localhost, ts.net https, plain http
non-loopback, ftp, garbage); a round over `"https"` builds its client with `trust_env=True` and a
round over `"tunnel"` with `trust_env=False`; a forged/altered response from the fake home is
refused and the round backs off with the fixed sentence; the whole existing round suite passes
on seals.

---

## Task 4: The public host, only on `/api/sync`

**Files:**
- Modify: `backend/app/config.py` (`sync_public_host: str = ""`), `backend/app/main.py`
  (host checking)
- Test: `backend/tests/sync/test_public_host.py`

**Behavior:** a request whose Host is `settings.sync_public_host` is accepted only when its path
starts with `/api/sync/` (and that host is not added to `allowed_hosts`); any other path with that
Host gets the same 400 TrustedHostMiddleware gives today. Implement as a small ASGI wrapper
around the existing TrustedHostMiddleware (or an allowlist callable), not by widening
`allowed_hosts`. Empty setting = today's behavior exactly.

**Tests:** with the setting: `/api/sync/hello` sealed via that Host works; `/api/jobs`,
`/api/settings/...`, `/health`, `/docs`, `/` with that Host are refused; without the setting the
Host is refused everywhere; localhost behavior unchanged.

---

## Task 5: Pairing with a one-time code

**Files:**
- Modify: `backend/app/services/sync/pairing.py` (Task 18), `backend/app/routers/sync.py`
  (`post_enroll`, `post_setup_enroll`), `backend/app/routers/settings.py` (`/api/settings/
  second-copy`), `backend/scripts/native/sync.sh`, the Second copy card under `frontend/`
  (`second-copy-section.tsx`)
- Test: `backend/tests/sync/test_pairing.py`, `test_pairing_process.py`,
  `backend/tests/test_native_pairing.py` (adapt Task 18's)

**Behavior:**
- `POST /api/settings/second-copy` (home): creates the key if missing; generates a code of 16
  characters from the Crockford base32 alphabet (80 bits via `secrets`), shows it as
  `XXXX-XXXX-XXXX-XXXX`; stores only `sha256(normalized code)` and the window end (10 min) in local
  `sync.` settings; returns `{code, open_until}` ONCE (a later GET returns `{enabled, open_until,
  last_paired_at}` without the code). `DELETE` retires it.
- Normalizing a typed code: uppercase, drop spaces and dashes, map `O→0`, `I/L→1`, reject other
  characters.
- `POST /api/sync/enroll` (home, reached through Funnel or a tunnel, no sync key on the caller):
  sealed with `ENROLL_TO_HOME` keys derived from the normalized code; the laptop tries the stored
  code hash (constant time) — if no window is open, the code is wrong, or 5 attempts were used,
  answer the bare 404 (count the attempt). On success: answer `{key}` sealed with
  `ENROLL_TO_REMOTE`, retire the code in the same commit, stamp `last_paired_at`, log one fixed
  line.
- `POST /api/sync-setup/enroll` (remote, own loopback): body `{code}`; refuses when a key exists
  or `remote_route()` is None; calls home's enroll over the chosen route; writes the key 0600
  (O_EXCL); returns `{ok}` or a fixed sentence with an outcome. The code is never logged.
- `sync.sh --pair --code <code>`: if no key file, calls `enroll-here` with the code first, then
  the pairing round. `--code` without `--pair` is a usage error. The code never appears in output.
- The card: **Show a pairing code** → the code large and copyable, a 10-minute countdown,
  **Stop**, then "Paired with your bot at <time>". Plain copy: "Paste this code to your bot. It
  works once, for 10 minutes." Follow docs/design-system.

**Tests:** code format and normalization; only the hash is stored; GET never returns the code;
enroll succeeds once and retires the code; wrong code, expired window, 6th attempt, replay → bare
404; the code and key never in logs (sentinel); enroll-here writes 0600 and refuses with a key
present or a bad route; sync.sh `--pair --code` (fake-uvicorn) and usage errors; a real
two-process test: open a window → enroll with the code → pair; the card's parity test.

---

## Task 6: Proof against an intercepting proxy

**Files:**
- Test: `backend/tests/sync/test_two_machines.py` (extend) and a small recording HTTP proxy
  fixture in `tests/sync/conftest.py`

**Behavior to prove (real processes):** the remote reaches the home backend through a local
recording forward proxy over plain HTTP (enable non-loopback-style routing for the test by
pointing `SYNC_REMOTE_URL` at the proxy-reachable address and forcing the `"https"` client path
with a test-only override of the route check — never in production code paths). Run pairing by
code, a full round with a profile sentinel, the AI key and a job-site login on home, a job push
with a file, and a request. Assert the proxy's recording contains none of: the sync key, the
pairing code, the sentinel, the AI key, the login password, a bundle's job title. Assert a
replay of a recorded request through the proxy gets the bare 404.

---

## Task 7: Docs and rules

**Files:** `docs/sync-setup.md` (two routes: "HTTPS through Funnel" with the exact Funnel
command, `SYNC_PUBLIC_HOST`, the policy line `"nodeAttrs": [{"target": ["autogroup:member"],
"attr": ["funnel"]}]`, MagicDNS + HTTPS certificates; and "SSH tunnel"; both paired with a code;
remove vault/key-copy steps; troubleshooting for "couldn't be verified", a bare 404 from a wrong
key or an expired code), `SECURITY.md`, `PRIVACY.md` (what's public, who sees what: the bot's
hosting platform holds the bot's replica; the internet and the relay see ciphertext only),
`SYSTEM.md` (rewrite `inv-sync-channel`: every sync message sealed; unsealed → bare 404; the key
never travels; only `/api/sync` may be published, through Funnel; pin to test_seal.py,
test_sealed_home.py, test_public_host.py, test_pairing.py in `.system_md_enforcement.json`; stay
≤1000 lines), `CHANGELOG.md`. No real hostnames.

---

## Task 8: Two-container rehearsal (reviewer)

Two `python:3.12-slim` containers plus: a TLS-intercepting proxy container (e.g. mitmproxy) that
is the bot container's ONLY egress (no direct route to the laptop container), and a TLS endpoint
(e.g. Caddy with an internal CA trusted by the proxy) in front of the laptop's `/api/sync` only.
Walk: Show a pairing code → `sync.sh --pair --code` → profile and job flows → offers → failure
modes; grep the proxy's decrypted flow dump for the key, code, AI key, login and a profile
sentinel (must be absent); confirm non-sync paths through the TLS endpoint are refused.

## Task 9: Final review

Opus whole-diff review with a security pass on seal.py, the route class, the client route choice,
the public-host wrapper and pairing; full suite, ruff, frontend tsc/lint/build, ratchets,
check_system_md, check_mcpb_bundle. Then the owner's real Funnel with the real bot.

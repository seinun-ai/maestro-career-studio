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
- Modify: `backend/pyproject.toml` (add `cryptography>=43` to the base dependencies — the local
  anaconda env has 43.0.3; `requirements.lock` already pins 50.0.0 via pdfminer-six/pyjwt and the
  Dockerfile installs the lock then `--no-deps -e .`, so no regeneration; update only the lock's
  `# via` comment if you touch it)
- Test: `backend/tests/sync/test_seal.py`

**The format (fixed):**
- Keys: `derive(secret, label) = HKDF(SHA256, length=32, salt=b"maestro-sync", info=label)`.
  Labels: `b"maestro-sync v2 remote->home"`, `b"maestro-sync v2 home->remote"`,
  `b"maestro-sync v2 enroll remote->home"`, `b"maestro-sync v2 enroll home->remote"`.
- Request header `X-Maestro-Seal: 2.<ts>.<rid>.<nonce>.<mac>.<tag-or-empty>` (base64url, no
  padding): `ts` = Unix seconds; `rid` = 16 random bytes; `nonce` = 12 random bytes;
  `mac` = `HMAC-SHA256(derive(secret, label + b" header"), request_aad)[:16]` — verified BEFORE any
  body is read, so garbage costs one HMAC and no body (Fable review). The 6th field holds the whole
  ciphertext (the 16-byte tag) when the plaintext body is empty, and the request then has no body
  (some proxies drop GET bodies); otherwise it is empty and the body is the ciphertext.
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
- `check_header(secret, method, path, query, header: str, peer: str, *, label=TO_HOME, now=None,
  replay: "ReplayCache | None") -> "HeaderOk"`: parses the header, checks version and ±SKEW, verifies
  `mac` with `hmac.compare_digest` (when the header is missing or malformed, still compute an HMAC
  over a fixed dummy and compare, so timing doesn't tell them apart), then registers the rid in
  `replay` (a seen rid is `Broken`). Returns what `open_request` needs.
- `open_request(secret, ok: "HeaderOk", wire_body: bytes, *, label=TO_HOME) -> bytes`: the
  plaintext; raises `Broken` on a body present when the tag rode in the header (or vice versa) or
  `InvalidTag`.
- `seal_response(secret, rid, status, body: bytes, *, label=TO_REMOTE) -> tuple[str, bytes]`.
- `open_response(secret, rid, status, header, wire_body, *, label=TO_REMOTE) -> bytes`.
- `class ReplayCache`: thread-safe dict rid→expiry with `seen(rid, now) -> bool` (adds when new,
  prunes expired entries on each call, caps at 100 000 entries by dropping the oldest).

Cache derived keys per (secret, label) (a small dict; secrets are few). Nonce volume: a few dozen
messages per round, ~10⁵ a year under one key — far below the 2³² random-nonce guidance; say so
in a comment.

**Tests (fail first):** a header with a bad/absent mac is `Broken` without touching a body; round trip for request (with and without body) and response; each
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

**Scope (Fable review, blocker):** unseal only on home's peer routes: paths under `/api/sync/`
EXCEPT `/api/sync/round` (the always-on copy's own unsealed loopback call used by `sync.sh` and
MCP `sync_now`; its FastAPI-read `_RoundBody` stays untouched) and `/api/sync/enroll` (Task 5
seals it with code-derived keys). `setup_router` (`/api/sync-setup/*`) shares `_SyncRoute` and
keeps today's behaviour. Tests cover every route in `router.routes` except those two.

**Tasks 2 and 3 land in ONE commit** (implement Task 2, then Task 3, run everything, then commit):
after Task 2 alone the real two-process tests are red until the client seals.

**Behavior:**
1. Order per request: 404 when sync is off (no key, or this copy is remote) → 403 for an `Origin`
   header → **`check_header`** (mac, ts, replay — no body read yet) → read the body under the
   existing caps/timeout → **`open_request`** → version check (the `X-Maestro-Sync` header, now
   authenticated by the AAD) → the lock → the handler. A 408/413 raised after the header verified
   is sealed normally (the rid is known).
2. **Any seal failure → a bare 404**: empty body, no headers beyond the minimum, the same status
   as "sync is off" — with the dummy-HMAC equalization from Task 1. No lockout (an attacker could
   lock out the real bot); instead throttle LOGGING of failures per `X-Forwarded-For` (one fixed
   line per source per minute, never a header value).
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

**Tests:** every peer route (all of `router.routes` except `/round` and `/enroll`) answers a bare
404 (empty body) when unsealed, when sealed with a wrong key, when carrying only `Authorization:
Bearer <key>`, and when replayed; a request with a bad header mac is refused without its body being
read (send a body that would stall, assert the 404 comes back promptly); the Origin 403 still comes
first; a sealed request works end to end and its response opens; a refusal (e.g. version mismatch
409) comes back sealed and readable by the client only; the log throttle; no log record (caplog
DEBUG) contains a sentinel from a bundle, the key or the seal header. **Update
`.system_md_enforcement.json` in the same commit**: pins that vanish
(`test_a_wrong_or_missing_key_is_a_401_that_echoes_nothing`, `test_the_key_is_checked_before_the_version`)
must be replaced by their sealed successors, or `check_system_md.py` fails.

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
- `SYNC_REMOTE_URL` must have no path (anything beyond `/`) → `remote_route()` is None; the AAD
  binds the path as sent, and Funnel strips and re-prepends only its own mount.
- Client: `"tunnel"` → `trust_env=False` (as today); `"https"` → `trust_env=True` (the
  environment proxy is the only way out of a sandbox; the seal makes it harmless), `verify=True`.
  With `trust_env=True` httpx loads `SSL_CERT_FILE`, else `SSL_CERT_DIR`, else certifi
  (`REQUESTS_CA_BUNDLE` is ignored) — a sandbox whose proxy decrypts TLS must set `SSL_CERT_FILE`
  to a bundle containing the proxy's CA (Task 7 docs). Building the client can raise `OSError` /
  `ssl.SSLError` on a bad bundle: today `http_client.new_client` catches only `InvalidURL` and the
  client is built outside `_attempt`'s try (round.py ~963) → move construction inside it and turn
  those into a `needs_person` skip "The certificate bundle in SSL_CERT_FILE can't be read."
- Every call: `request = ctx.http.build_request(method, path, params=..., content=...)`, seal with
  `request.url.path` and `request.url.query.decode()`, set the seal header on the request, then
  `ctx.http.send(request)`; `open_response` on the way back; a response that fails to open is a
  transient "The laptop's answer couldn't be verified." (never the body).
- Remove the `Authorization` header.

**Tests:** `remote_route` table (loopback http/https, ::1, localhost, ts.net https, a URL with a
path, plain http non-loopback, ftp, garbage); a bad `SSL_CERT_FILE` gives the needs_person skip,
not a 500; update the `.system_md_enforcement.json` pin
`test_a_remote_address_that_is_not_this_machines_own_tunnel_is_refused` in the same commit (its
`https://[2001:db8::1]` case becomes valid); a round over `"https"` builds its client with `trust_env=True` and a
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
around the existing TrustedHostMiddleware (Starlette's is a plain ASGI class), not by widening
`allowed_hosts`. The wrapper reads `settings.sync_public_host` at REQUEST time (main.py reads
`allowed_hosts` at import, and tests must be able to switch the setting on). Empty setting =
today's behavior exactly.

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
  `XXXX-XXXX-XXXX-XXXX`; stores the digest (see below); returns `{code, open_until}` ONCE (a later GET returns `{enabled, open_until,
  last_paired_at}` without the code). `DELETE` retires it.
- Normalizing a typed code: uppercase, drop spaces and dashes, map `O→0`, `I/L→1`, reject other
  characters.
- **Keys from the code (Fable review, blocker):** both sides compute `digest =
  sha256(normalized_code)` and derive the enroll keys with `derive(digest.hex(), ENROLL_*)`. Home
  stores `digest.hex()` and the window end (10 min) in local `sync.` settings — never the code.
- `POST /api/sync/enroll` (home, reached through Funnel or a tunnel, no sync key on the caller):
  sealed (header mac + GCM) with the `ENROLL_TO_HOME` keys; the only check is the seal itself. No
  window open, an expired window, or a failed open → the bare 404, and a failed open counts one of 5
  attempts; on the 5th the window retires. On success: answer `{key}` sealed with
  `ENROLL_TO_REMOTE`, retire the code in the same commit, stamp `last_paired_at`, log one fixed
  line.
- `POST /api/sync-setup/enroll` (remote, own loopback): body `{code}`; refuses when a key exists
  or `remote_route()` is None; calls home's enroll over the chosen route; writes the key 0600
  (O_EXCL); returns `{ok}` or a fixed sentence with an outcome. The code is never logged.
- `sync.sh --pair --code <code>`: if no key file, calls `enroll-here` with the code first, then
  the pairing round. `--code -` reads the code from stdin (preferred: argv shows in `ps`); `--code`
  without `--pair` is a usage error. The code never appears in output.
- Strays to update (Fable review): `pairing.CLOSED` ("Click Allow pairing…") and its tests
  (`test_pairing.py:26`, `test_native_pairing.py:72`), `pairing.TUNNEL`, `round.NOT_OWN_TUNNEL`, the
  card copy "through its tunnel" (`second-copy-section.tsx:90`, its `.test.mjs:43`),
  `maestro.env.example:14`, README.md:61, docs/native-install.md:172.
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
recording forward proxy. Override in the in-process remote only: `monkeypatch.setattr(status,
"remote_route", lambda: "https")` (the `machines` fixture already monkeypatches settings), set
`HTTP_PROXY=<recording proxy>` and clear `NO_PROXY`. With an `http://` target httpx uses the
absolute-URI forward form, so the proxy sees the HTTP request in cleartext — exactly the
decrypting-proxy view we must survive; say so in the test's docstring. Run pairing by
code, a full round with a profile sentinel, the AI key and a job-site login on home, a job push
with a file, and a request. Assert the proxy's recording contains none of: the sync key, the
pairing code, the sentinel, the AI key, the login password, a bundle's job title. Assert a
replay of a recorded request through the proxy gets the bare 404, and that a replay after a home
restart (in-memory cache emptied, inside the 5-minute window) changes nothing (handlers are
idempotent; `request_apply` dedupes by id) — state this residual in SECURITY.md.

---

## Task 7: Docs and rules

**Files:** `docs/sync-setup.md` (two routes: "HTTPS through Funnel" with the exact Funnel
command, `SYNC_PUBLIC_HOST`, the policy line `"nodeAttrs": [{"target": ["autogroup:member"],
"attr": ["funnel"]}]`, MagicDNS + HTTPS certificates; and "SSH tunnel"; both paired with a code;
remove vault/key-copy steps; troubleshooting for "couldn't be verified", a bare 404 from a wrong
key or an expired code), `SECURITY.md`, `PRIVACY.md` (what's public, who sees what: the bot's
hosting platform holds the bot's replica; the internet and the relay see ciphertext only; the
pasted code plus a recorded enrollment would let that platform recover the sync key — nothing
beyond the key file already in its sandbox, but it can outlive the sandbox in transcripts, so
re-key (delete both key files, pair again) if the platform is ever suspect; prefer `--code -`), the
sandbox's `SSL_CERT_FILE=<bundle with the proxy CA>`,
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

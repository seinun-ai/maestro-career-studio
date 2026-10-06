# Sealed sync over HTTPS: a route for always-on copies that can't use SSH

Approved by the owner on 2026-10-06. Builds on phase 4b
(`docs/plans/2026-10-06-split-ownership-sync-design.md` and its plan, Tasks 1-18).

## Why

Phase 4b reaches the laptop through an SSH tunnel. The first real always-on copy runs in an agent
sandbox whose only way out is HTTPS through a proxy that decrypts TLS with its own certificate
authority. Outbound SSH is switched off by the platform on purpose, and Tailscale can't join
through the proxy (its control protocol needs TLS extensions the proxy drops). Routing SSH around
the platform's block is not an option. WebSocket upgrades and ordinary HTTPS do pass.

So the sync channel must work as plain HTTPS from the always-on copy's side, while nothing in the
middle (the sandbox's decrypting proxy, a public relay, the internet) can read or forge it.

## Decisions and rejected options

- **Seal every sync message with keys derived from the sync key** (AES-256-GCM, one key per
  direction). Chosen. The key never travels; there is no bearer header.
- **One protocol for both routes:** the SSH tunnel route seals too. Simpler than two protocols.
- **Publish only `/api/sync` with Tailscale Funnel.** TLS ends on the laptop (Funnel's relays
  can't decrypt), and the laptop already runs Tailscale. The always-on copy needs no Tailscale.
- **Pair with a one-time code** shown on the laptop and pasted to the bot. It replaces Task 18's
  tunnel-only key fetch (its card and window are reused).
- Rejected: TLS client certificates (the sandbox proxy decrypts TLS, and Funnel ends TLS before
  Maestro sees it); signed requests with readable bodies (the proxy would read the profile, the AI
  key and the job-site password); wrapping SSH in a WebSocket (it would bypass a deliberate
  platform block); asking the user to paste the sync key itself (it would stay valid forever in a
  chat history, where a code dies on use).

## Part 1: Transport and sealing

- **Laptop:** `tailscale funnel --bg --set-path=/api/sync http://127.0.0.1:8001/api/sync`
  publishes only the sync paths at `https://<mac>.<tailnet>.ts.net`. Nothing else in the app is
  reachable from outside. `SYNC_PUBLIC_HOST=<mac>.<tailnet>.ts.net` lets Maestro accept that Host
  header on `/api/sync/*` only; every other path still refuses unknown hosts.
- **Always-on copy:** `SYNC_REMOTE_URL=https://<mac>.<tailnet>.ts.net`. A non-loopback HTTPS URL
  is reached through the environment's proxy (the sandbox's only way out). A loopback URL (an SSH
  tunnel) is reached directly with proxies ignored, as today. A non-loopback plain `http://` URL
  is refused.
- **Sealing:** each request body and each response body is encrypted and authenticated with
  AES-256-GCM. Keys come from the sync key through HKDF-SHA256 with distinct labels for
  remote→laptop and laptop→remote. The method, path, query, a timestamp and a random request id
  are bound in as associated data; the response binds the request id. The laptop rejects a seal
  that fails, a timestamp more than 5 minutes off, and a request id seen in the last 10 minutes.
- **Unsealed or failed requests get a bare 404** with no body, after the same work as a real
  check (constant-time), and repeated failures are rate-limited. A public address reveals nothing
  about Maestro. With no key file every `/api/sync/*` route stays a 404, as today.
- **Kept, after unsealing:** the protocol and schema-revision check, one round at a time, the
  body caps and the chunk timeout. Every response is sealed, errors included (except the bare
  404). The sync protocol number goes to 2; nobody has paired yet, so v1 needs no support.

## Part 2: Pairing with a one-time code

- The Second copy card (Settings) gets **Show a pairing code**: it creates the sync key if none
  exists and shows a 16-character code (80 bits, grouped `XXXX-XXXX-XXXX-XXXX`), valid for 10
  minutes and usable once, with a countdown and Stop.
- The user pastes the code to the bot, which runs `sync.sh --pair --code <code>`. The always-on
  copy sends an enroll request sealed with a key derived from the code; the laptop answers with
  the sync key sealed the same way and retires the code. Then the pairing round runs.
- At most 5 attempts per code; the code is never logged or stored in clear (a hash, compared in
  constant time). The card then shows "Paired with your bot at <time>".
- The same mechanism serves the SSH tunnel route. Task 18's no-code enroll is replaced.

## Part 3: Setup, rules, docs, testing

- **Laptop setup:** in the tailnet admin, MagicDNS and HTTPS certificates on, and a policy line
  allowing Funnel (`"nodeAttrs": [{"target": ["autogroup:member"], "attr": ["funnel"]}]`); the
  funnel command above; `SYNC_PUBLIC_HOST` in `.env` and a restart; then a pairing code.
- **Always-on copy setup:** `SYNC_REMOTE_URL`, the `sync.sh` cron line, `sync.sh --pair --code`.
  No SSH key, no Tailscale.
- **Rules:** SYSTEM.md's sync-channel invariant becomes: every sync message is sealed; unsealed
  requests get a bare 404; the key never travels; only `/api/sync` may be published, through
  Funnel. SECURITY.md and PRIVACY.md say what is public and who sees what (the bot's hosting
  platform already holds the bot's replica; the internet and the relay see only ciphertext).
- **Setup guide:** two routes, "HTTPS through Funnel" (for sandboxes like this one) and "SSH
  tunnel" (for machines that allow SSH), both paired with a code.
- **Testing:** seal round trips and every rejection (tamper, replay, stale, wrong key, wrong
  direction); every unsealed sync route a bare 404, including one carrying a bearer key; the rate
  limit; the pairing code's single use, expiry, attempt limit and absence from logs; real
  two-process tests through a recording proxy that must never see a profile sentinel, the AI key
  or the login; a two-container rehearsal where the bot's only egress is an intercepting proxy and
  the laptop sits behind its own TLS endpoint; then the owner's real Funnel with the real bot.

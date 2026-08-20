/**
 * Is this `Host` header one we serve on?
 *
 * The backend has always rejected a forged Host (`TrustedHostMiddleware`), and
 * SECURITY.md calls that the DNS-rebinding defence. It only ever defended the
 * backend's own port. The browser talks to Next on :3000, and this app's
 * catch-all `/api` route proxies straight through to the zero-auth backend —
 * rebuilding the outbound request, and with it a trusted Host — so a page that
 * rebinds a hostile domain to 127.0.0.1 was same-origin with the whole API and
 * the backend never saw the attacker's authority. This module is the missing
 * half of that control.
 *
 * Kept as its own module with no framework imports for two reasons: both
 * readers (`proxy.ts` and the `/api` route) must decide identically, and a
 * dependency-free ES module can be executed directly by Node, so the
 * comparison is pinned by a real behavioural test rather than a source-text
 * one (`backend/tests/test_frontend_host_guard.py`).
 *
 * Plain `.mjs` with JSDoc types rather than TypeScript on purpose: the test
 * harness runs it under whatever Node CI happens to be on, and `.ts` type
 * stripping would silently tie a security test to a Node version.
 */

/**
 * Hosts served by default. A bare hostname — never a scheme, never a port.
 * @type {string[]}
 */
export const DEFAULT_ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"];

/**
 * Read the allowlist from the environment, falling back to the defaults.
 *
 * `FRONTEND_ALLOWED_HOSTS` is the origin-side twin of the backend's
 * `ALLOWED_HOSTS`: front the app with a reverse proxy and you must name the
 * hostname in both, or one of the two layers refuses the traffic.
 *
 * @param {Record<string, string | undefined>} env
 * @returns {string[]}
 */
export function allowedHostsFromEnv(env) {
  const raw = env.FRONTEND_ALLOWED_HOSTS;
  if (raw === undefined) return DEFAULT_ALLOWED_HOSTS;
  const entries = raw
    .split(",")
    .map((entry) => entry.trim().toLowerCase())
    .filter((entry) => entry.length > 0);
  // An explicitly empty value means "no host is allowed", which would brick the
  // app silently. Treat it as unset — the same reading the backend's
  // scrub_empty_env applies, and for the same reason.
  return entries.length > 0 ? entries : DEFAULT_ALLOWED_HOSTS;
}

/**
 * Exact hostname match, port ignored.
 *
 * The port is dropped because the published port varies (3000 in dev, whatever
 * a proxy maps in front of it) while the hostname is the thing an attacker
 * has to lie about. IPv6 literals keep their brackets so `[::1]:3000` and
 * `[::1]` compare equal, and a bare `::1` is never mistaken for a host:port
 * split.
 *
 * @param {string | null | undefined} hostHeader
 * @param {string[]} allowed
 * @returns {boolean}
 */
export function isAllowedHost(hostHeader, allowed) {
  if (!hostHeader) return false;

  const host = hostHeader.trim().toLowerCase();
  if (host.length === 0) return false;

  let hostname;
  if (host.startsWith("[")) {
    // IPv6 literal: `[::1]` or `[::1]:3000`. The bracket is part of the name.
    const close = host.indexOf("]");
    if (close === -1) return false;
    hostname = host.slice(0, close + 1);
    const rest = host.slice(close + 1);
    if (rest.length > 0 && !/^:\d+$/.test(rest)) return false;
  } else {
    const colon = host.indexOf(":");
    if (colon === -1) {
      hostname = host;
    } else {
      // More than one colon and no brackets is a malformed authority, not an
      // IPv6 host — refuse rather than guess which colon splits the port.
      if (host.indexOf(":", colon + 1) !== -1) return false;
      hostname = host.slice(0, colon);
      if (!/^\d+$/.test(host.slice(colon + 1))) return false;
    }
  }

  if (hostname.length === 0) return false;
  // Membership, never `startsWith`/`includes`: `localhost.evil.example` and
  // `notlocalhost` both contain an allowed name and are both a different site.
  return allowed.includes(hostname);
}

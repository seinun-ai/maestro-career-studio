import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { allowedHostsFromEnv, isAllowedHost } from "@/lib/allowed-hosts.mjs";

/**
 * Reject any request whose `Host` is not one we serve on — the DNS-rebinding
 * defence for the surface users actually open.
 *
 * The backend has always had this check (`TrustedHostMiddleware`) and
 * SECURITY.md called it "the DNS-rebinding defence", but it only guarded the
 * backend's own port. The browser talks to Next on :3000, and `app/api/[...path]`
 * proxies through to a zero-auth API while rebuilding the outbound request —
 * so the backend saw a trusted Host no matter what authority the page used.
 * A hostile domain rebound to 127.0.0.1 was therefore same-origin with the
 * entire career record, and CORS is never consulted on a same-origin request.
 *
 * **This file must be named `proxy.ts`.** Next 16 renamed the `middleware`
 * file convention to `proxy`; a `middleware.ts` here would be silently ignored,
 * which for a security control is the worst failure mode there is — a defence
 * that looks present and never runs. Pinned by
 * `backend/tests/test_frontend_host_guard.py`.
 *
 * There is deliberately NO `matcher` export: proxy runs on every route by
 * default, and every route is what we want. In particular `/api/*` must be
 * covered, and the Next docs' example matcher excludes it.
 */
export function proxy(request: NextRequest) {
  const allowed = allowedHostsFromEnv(process.env);
  if (!isAllowedHost(request.headers.get("host"), allowed)) {
    // Mirrors the backend's 400 for a forged Host, and like it carries no CORS
    // headers — the page must not be able to read this either.
    return new NextResponse(
      JSON.stringify({
        detail:
          "Host not allowed. Reach this app on localhost or 127.0.0.1, or set " +
          "FRONTEND_ALLOWED_HOSTS if you serve it on another hostname.",
      }),
      { status: 400, headers: { "content-type": "application/json" } },
    );
  }

  return NextResponse.next();
}

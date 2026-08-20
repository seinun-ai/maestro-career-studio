import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { allowedHostsFromEnv, isAllowedHost } from "@/lib/allowed-hosts.mjs";

export const dynamic = "force-dynamic";

/**
 * Same-origin proxy to FastAPI. The browser only talks to Next (:3000); this handler
 * forwards to the backend server-side (no CORS / Private Network Access issues).
 */
const BACKEND = (
  process.env.API_PROXY_BACKEND ??
  process.env.BACKEND_URL ??
  "http://127.0.0.1:8001"
).replace(/\/$/, "");

async function proxy(req: NextRequest, pathSegments: string[]) {
  // The SECOND Host check, and the one that actually guards the data.
  // `proxy.ts` covers every route including this one, so in a correctly wired
  // build this branch is unreachable — which is exactly why it is here. This
  // handler rebuilds the outbound request and deletes the inbound Host below,
  // so if the file-convention check ever stops running (a Next rename, a
  // matcher someone adds, a refactor that moves this route), the failure is
  // silent and the whole zero-auth API is behind it. A defence against a
  // rebinding attack must not rest on one framework filename.
  const allowed = allowedHostsFromEnv(process.env);
  if (!isAllowedHost(req.headers.get("host"), allowed)) {
    return NextResponse.json({ detail: "Host not allowed." }, { status: 400 });
  }

  const suffix = pathSegments.join("/");
  const search = req.nextUrl.search;
  const url = `${BACKEND}/api/${suffix}${search}`;

  const headers = new Headers(req.headers);
  headers.delete("host");
  headers.delete("connection");

  const init: RequestInit = {
    method: req.method,
    headers,
    redirect: "manual",
  };

  if (!["GET", "HEAD"].includes(req.method)) {
    init.body = await req.arrayBuffer();
  }

  let upstream: Response;
  try {
    upstream = await fetch(url, init);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { detail: `Upstream fetch failed (${BACKEND}): ${msg}` },
      { status: 502 },
    );
  }

  const outHeaders = new Headers(upstream.headers);
  outHeaders.delete("transfer-encoding");

  return new NextResponse(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: outHeaders,
  });
}

type RouteCtx = { params: Promise<{ path?: string[] }> };

export async function GET(req: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxy(req, path ?? []);
}

export async function POST(req: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxy(req, path ?? []);
}

export async function PATCH(req: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxy(req, path ?? []);
}

export async function PUT(req: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxy(req, path ?? []);
}

export async function DELETE(req: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxy(req, path ?? []);
}

export async function OPTIONS(req: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxy(req, path ?? []);
}

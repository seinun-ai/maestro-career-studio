import type { NextConfig } from "next";

/**
 * Response headers applied to every route.
 *
 * This app is single-user and usually local, but it holds the user's resume,
 * contact details, EEO answers and provider API keys, and it renders
 * job-description text and evidence screenshots that came from arbitrary
 * websites. That is exactly the content you do not want MIME-sniffed, framed
 * by another origin, or leaked through a Referer header to a careers site.
 *
 * A Content-Security-Policy is deliberately NOT set here: Next's App Router
 * emits inline bootstrap scripts, so a useful policy needs per-request nonces
 * threaded through middleware. Worth doing, but it is its own change.
 */
const SECURITY_HEADERS = [
  // Stop the browser guessing a content type. Evidence screenshots and
  // rendered PDFs are proxied through /api, so a sniffed text/html would be a
  // stored-XSS primitive on our own origin.
  { key: "X-Content-Type-Options", value: "nosniff" },
  // No page here is meant to be embedded anywhere.
  { key: "X-Frame-Options", value: "DENY" },
  // Never send a path to a third party. Job source URLs and careers pages open
  // in new tabs; the default policy would hand them the referring URL, which
  // in this app contains internal record ids.
  { key: "Referrer-Policy", value: "no-referrer" },
  // Nothing in the UI uses these; deny them rather than leave them available
  // to any script that ends up running here.
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
];

const nextConfig: NextConfig = {
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;

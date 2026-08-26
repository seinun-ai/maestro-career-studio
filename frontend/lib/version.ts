export const FRONTEND_VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? "dev";

/**
 * True when the two images demonstrably disagree.
 *
 * A version starting with "dev" ("dev" for a local build, "dev-<sha>" for a
 * workflow_dispatch image) means "unknown, do not compare": those builds
 * float free of any release, so a mismatch is noise. This exists to catch
 * the failure SYSTEM.md §9 records — a frontend-only change shipped without
 * rebuilding the frontend image, which once made fixed UI look broken for a
 * whole review.
 */
export function imagesDisagree(frontend: string, backend: string | undefined): boolean {
  if (!backend) return false;
  if (frontend.startsWith("dev") || backend.startsWith("dev")) return false;
  return frontend !== backend;
}

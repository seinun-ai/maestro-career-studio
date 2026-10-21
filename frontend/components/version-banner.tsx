"use client";

import { TriangleAlert } from "lucide-react";

import { GuardedLink as Link } from "@/components/guarded-link";
import { useVersion } from "@/hooks/use-version";
import { anchorHref } from "@/lib/settings-tabs";
import { FRONTEND_VERSION, imagesDisagree, pageIsOlder } from "@/lib/version";

/**
 * Persistent warning when the two images demonstrably disagree.
 *
 * Not dismissible: it reports a broken install, not news. Renders nothing
 * while the query is loading or errored — a stopped backend already has its
 * own error surfaces.
 */
export function VersionBanner() {
  const { data, isError, isLoading } = useVersion();

  if (
    isLoading ||
    isError ||
    !data ||
    !imagesDisagree(FRONTEND_VERSION, data.version)
  ) {
    return null;
  }

  return (
    <div
      role="status"
      className="bg-warning-container text-on-warning-container border-b px-4 py-2.5 text-body-medium"
    >
      <p className="mx-auto flex max-w-6xl items-start gap-2">
        <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
        {/* A page older than the backend was loaded before an update: reloading
            fetches the new web app. Any other mismatch is a broken install, and
            Settings › Basics › About's How to update says what to do for each install. */}
        {pageIsOlder(FRONTEND_VERSION, data.version) ? (
          <span>
            Maestro CS was updated. Reload this page to use the new version.{" "}
            <button
              type="button"
              className="underline underline-offset-4"
              onClick={() => window.location.reload()}
            >
              Reload
            </button>
          </span>
        ) : (
          <span>
            Maestro CS didn&apos;t finish updating. See How to update in{" "}
            <Link className="underline underline-offset-4" href={anchorHref("/settings", "about")}>
              Settings › Basics › About
            </Link>
            .
          </span>
        )}
      </p>
    </div>
  );
}

"use client";

import { AlertTriangle } from "lucide-react";

import { useVersion } from "@/hooks/use-version";
import { FRONTEND_VERSION, imagesDisagree } from "@/lib/version";

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
      className="border-amber-500/30 bg-amber-500/10 text-amber-950 dark:text-amber-100 border-b px-4 py-2.5 text-sm"
    >
      <p className="mx-auto flex max-w-6xl items-start gap-2">
        <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span>
          Your frontend ({FRONTEND_VERSION}) and backend ({data.version}) are
          different versions. One image is stale — run{" "}
          <code className="font-mono text-[0.85em]">./scripts/update.sh</code>.
        </span>
      </p>
    </div>
  );
}

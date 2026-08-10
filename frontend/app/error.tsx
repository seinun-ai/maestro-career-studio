"use client";

import Link from "next/link";
import { useEffect } from "react";
import { TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * Route-level error boundary.
 *
 * Without this file a render-time throw anywhere under app/ unmounts the whole
 * tree and leaves the user on a blank page with no way back — every page here
 * handles *query* failures (`isError` branches) but nothing caught a component
 * that threw. Rendered inside the shell, so the sidebar stays usable.
 *
 * `digest` is the server-side hash Next attaches to production errors; the
 * message itself is only shown in development, so a stack or an internal path
 * never reaches the page.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Unhandled error in route:", error);
  }, [error]);

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
      <TriangleAlert className="text-muted-foreground/50 size-8" aria-hidden />
      <h1 className="text-lg font-medium">Something went wrong</h1>
      <p className="text-muted-foreground text-sm">
        This page failed to render. Your data is untouched, so retrying is safe.
      </p>
      {process.env.NODE_ENV === "development" && error.message && (
        <pre className="bg-muted/40 text-muted-foreground max-w-full overflow-x-auto rounded-md px-3 py-2 text-left text-xs">
          {error.message}
        </pre>
      )}
      {error.digest && (
        <p className="text-muted-foreground text-xs">
          Reference: <span className="font-mono">{error.digest}</span>
        </p>
      )}
      {/* Retry is the filled one. It was the other way round: the escape hatch
          carried the emphasis while the action this page exists for sat in an
          outline button — directly contradicting the copy above it, which
          says retrying is safe. */}
      <div className="flex gap-2">
        <Button onClick={reset}>Try again</Button>
        <Button
          variant="ghost"
          nativeButton={false}
          render={<Link href="/applications">Back to Applications</Link>}
        />
      </div>
    </main>
  );
}

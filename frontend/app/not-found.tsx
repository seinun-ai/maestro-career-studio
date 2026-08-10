import Link from "next/link";
import { FileQuestion } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * 404 for URLs that match no route and for any `notFound()` call.
 * Deliberately offers a way onward rather than a bare status code — the two
 * likeliest arrivals here are a stale bookmark and a deleted record.
 */
export default function NotFound() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
      <FileQuestion className="text-muted-foreground/50 size-8" aria-hidden />
      <h1 className="text-lg font-medium">Page not found</h1>
      <p className="text-muted-foreground text-sm">
        That URL doesn&apos;t exist here. It may have been renamed, or the
        record behind it was deleted.
      </p>
      <Button
        nativeButton={false}
        render={<Link href="/applications">Back to Applications</Link>}
      />
    </main>
  );
}

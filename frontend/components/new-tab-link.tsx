import type { ReactNode } from "react";
import { ExternalLink } from "lucide-react";

import { cn } from "@/lib/utils";

/** What a link that leaves the app adds after its words: an icon to see, and
 *  "(opens in a new tab)" to hear. Inside the <a>, so both are part of the link. */
export function NewTabCue() {
  return (
    <>
      <ExternalLink className="size-3.5 shrink-0" aria-hidden="true" />
      <span className="sr-only"> (opens in a new tab)</span>
    </>
  );
}

/** An inline text link to a page outside the app, in a new tab. */
export function NewTabLink({
  href,
  className,
  children,
}: {
  href: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={cn("inline-flex items-center gap-1 underline underline-offset-4 hover:no-underline", className)}
    >
      {children}
      <NewTabCue />
    </a>
  );
}

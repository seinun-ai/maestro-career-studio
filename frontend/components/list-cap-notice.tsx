import { Info } from "lucide-react";

import { listCapSentence, type ListCap } from "@/lib/list-cap";
import { cn } from "@/lib/utils";

/**
 * The last line of a list fetched with a row limit, when the limit was hit:
 * say that rows were left out instead of dropping them silently.
 *
 * Plain text, not a live region: it is there on arrival, not news, and a
 * status role would be announced on every load. Screen readers reach it in
 * reading order, after the list. Renders nothing when the list is whole.
 * The Agent inbox passes the server's `total`; the tracker has none.
 */
export function ListCapNotice({ className, ...cap }: ListCap & { className?: string }) {
  const sentence = listCapSentence(cap);
  if (!sentence) return null;
  return (
    <p
      data-slot="list-cap-notice"
      className={cn("text-muted-foreground flex items-start gap-2 text-sm", className)}
    >
      <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{sentence}</span>
    </p>
  );
}

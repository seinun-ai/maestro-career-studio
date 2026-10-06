import { X } from "lucide-react";

import { CONCEPT_ICONS } from "@/lib/concept-icons";

const DoneIcon = CONCEPT_ICONS.done;

/** How an Assistant suggestion card ended: done (its own word, "Applied" or "Added") or Discarded.
 *  One shape for every card, so the words and glyphs cannot drift apart. */
export function CardResolution({ done, doneWord }: { done: boolean; doneWord: string }) {
  return (
    <span className="text-muted-foreground flex items-center gap-1 text-body-small">
      {done ? (
        <>
          <DoneIcon className="size-3.5" aria-hidden="true" /> {doneWord}
        </>
      ) : (
        <>
          <X className="size-3.5" aria-hidden="true" /> Discarded
        </>
      )}
    </span>
  );
}

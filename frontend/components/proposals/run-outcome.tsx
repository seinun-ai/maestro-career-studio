import { CircleAlert, CircleCheck, CircleX } from "lucide-react";

import { outcomeWord, type RunOutcome as Outcome } from "@/lib/agent-runs";

const GLYPH = {
  ok: { Icon: CircleCheck, tone: "text-success" },
  partial: { Icon: CircleAlert, tone: "text-warning" },
  failed: { Icon: CircleX, tone: "text-destructive" },
} as const;

/** How an automation's run ended: the glyph and the word (Done, Partly done, Failed), on a surface chip. */
export function RunOutcome({ outcome }: { outcome: Outcome }) {
  const glyph = GLYPH[outcome];
  return (
    <span className="inline-flex h-5 shrink-0 items-center gap-1 rounded-full bg-surface-container px-2 text-label-medium text-foreground">
      {glyph ? <glyph.Icon className={`size-3 shrink-0 ${glyph.tone}`} aria-hidden="true" /> : null}
      {outcomeWord(outcome)}
    </span>
  );
}

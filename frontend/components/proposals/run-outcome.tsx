import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { outcomeWord, type RunOutcome as Outcome } from "@/lib/agent-runs";

const GLYPH = {
  ok: { Icon: CONCEPT_ICONS.done, tone: "text-success" },
  partial: { Icon: CONCEPT_ICONS.warning, tone: "text-warning" },
  failed: { Icon: CONCEPT_ICONS.fails, tone: "text-destructive" },
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

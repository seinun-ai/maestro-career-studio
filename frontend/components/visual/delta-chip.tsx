import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { formatDelta } from "@/lib/visual";
import { cn } from "@/lib/utils";

const ICON = { up: CONCEPT_ICONS.increase, down: CONCEPT_ICONS.decrease, flat: CONCEPT_ICONS.none } as const;
const TONE = { up: "text-success", down: "text-destructive", flat: "text-muted-foreground" } as const;

/** A signed change with its direction icon ("+6.2", "−1.4", "0.0"). The sign is in the text, so colour only repeats it. */
export function DeltaChip({ value, prefix, unit = "points", className }: {
  value: number; prefix?: string; unit?: string; className?: string;
}) {
  const { text, sign } = formatDelta(value);
  const Icon = ICON[sign];
  return (
    <span role="img" aria-label={`${prefix ? prefix + " " : ""}${text} ${unit}`}
      className={cn("inline-flex h-5 items-center gap-1 rounded-full bg-surface-container px-2 text-label-medium tabular-nums", className)}>
      <Icon aria-hidden="true" className={cn("size-3 shrink-0", TONE[sign])} />
      <span aria-hidden="true">{prefix ? `${prefix} ${text}` : text}</span>
    </span>
  );
}

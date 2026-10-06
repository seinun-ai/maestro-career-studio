import { meterLabel } from "@/lib/visual";
import { cn } from "@/lib/utils";

/** An ordinal step on a short scale (the health evidence ladder, inbox readiness). The word stays. `label` replaces the spoken name when the word already says the count. */
export function DotMeter({ name, filled, total, word, label, className }: {
  name: string; filled: number; total: number; word: string; label?: string; className?: string;
}) {
  return (
    <span role="img" aria-label={label ?? meterLabel(name, filled, total, word)}
      className={cn("inline-flex items-center gap-1.5 text-body-small", className)}>
      <span className="inline-flex items-center gap-0.5" aria-hidden="true">
        {Array.from({ length: total }, (_, i) => (
          <span key={i} className={cn("size-1.5 rounded-full", i < filled ? "bg-foreground" : "bg-surface-container-highest")} />
        ))}
      </span>
      <span aria-hidden="true">{word}</span>
    </span>
  );
}

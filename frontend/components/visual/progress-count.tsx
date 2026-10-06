import { clampPct } from "@/lib/visual";
import { cn } from "@/lib/utils";

/** "3 of 5 answered" with a bar. `showText={false}` keeps the bar alone; the sentence stays in its aria-label. */
export function ProgressCount({ done, total, noun, showText = true, className }: {
  done: number; total: number; noun: string; showText?: boolean; className?: string;
}) {
  const sentence = `${done} of ${total} ${noun}`;
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-2", className)}>
      {showText ? <span className="text-body-small tabular-nums" aria-hidden="true">{sentence}</span> : null}
      <span role="progressbar" aria-label={sentence} aria-valuemin={0} aria-valuemax={total} aria-valuenow={Math.min(total, Math.max(0, done))}
        className="h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-surface-container">
        <span className="block h-full rounded-full bg-primary transition-[width] duration-(--duration-medium2) ease-(--ease-standard)"
          style={{ width: `${clampPct(done, total)}%` }} />
      </span>
    </span>
  );
}

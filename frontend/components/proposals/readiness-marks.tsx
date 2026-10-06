import { readinessMarks, type Readiness } from "@/lib/inbox-readiness";
import { cn } from "@/lib/utils";

const TONE = {
  muted: "bg-surface-container-high text-muted-foreground dark:bg-surface-container-highest",
  warning: "bg-warning-container text-on-warning-container",
} as const;

/** A row's readiness: tailoring, a knock-out, answers to check. Nothing when unknown. */
export function ReadinessMarks({ readiness }: { readiness: Readiness | null | undefined }) {
  const marks = readinessMarks(readiness);
  if (marks.length === 0) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {marks.map((mark) => (
        <span key={mark.text} className={cn("rounded-full px-2 py-0.5 text-label-small", TONE[mark.tone])}>
          {mark.text}
        </span>
      ))}
    </span>
  );
}

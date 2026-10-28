import { type DiffSegment, lineDiff } from "@/lib/word-diff";
import { cn } from "@/lib/utils";

/**
 * One change's old and new text, read as a diff: the old line on a faint red wash and the new on a faint
 * green, the words that changed on the full container (struck through on the old line), the health
 * report's diff colours (docs/design-system/components/JudgedText). `<del>`/`<ins>` with "Before:" and
 * "Now:" say it without colour. The studio's review mode and the job page's step 3 both draw it.
 */

// Exported for the contrast pins (backend/tests/test_frontend_color_roles.py).
export const DIFF_LINE = {
  removed: "bg-error-container/40 text-muted-foreground",
  added: "bg-success-container/40 text-foreground",
} as const;
export const DIFF_WORD = {
  removed: "bg-error-container text-on-error-container line-through",
  added: "bg-success-container text-on-success-container",
} as const;

function DiffLine({
  kind,
  segments,
  className,
}: {
  kind: "removed" | "added";
  segments: DiffSegment[];
  className?: string;
}) {
  const Tag = kind === "removed" ? "del" : "ins";
  return (
    <p className={cn("rounded-corner-xs px-1.5 py-0.5", DIFF_LINE[kind], className)}>
      <Tag className="no-underline">
        <span className="sr-only">{kind === "removed" ? "Before: " : "Now: "}</span>
        {segments.map((segment, i) =>
          segment.changed ? (
            <span key={i} className={cn("rounded-corner-2xs", DIFF_WORD[kind])}>
              {segment.text}
            </span>
          ) : (
            segment.text
          ),
        )}
      </Tag>
    </p>
  );
}

export function HunkDiff({
  before,
  after,
  className,
}: {
  before: string;
  after: string;
  /** The text size, for both lines alike so their words compare. */
  className?: string;
}) {
  const { before: old, after: now } = lineDiff(before, after);
  return (
    <div className="space-y-1">
      {before && <DiffLine kind="removed" segments={old} className={className} />}
      {after && <DiffLine kind="added" segments={now} className={className} />}
    </div>
  );
}

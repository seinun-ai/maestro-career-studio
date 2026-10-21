import { cn } from "@/lib/utils";

/** The AI is working: three dots that rise in turn beside what it is doing ("Writing your cover
 * letter"). It replaces a spinner where the work is shown. A status, so the label is spoken when it
 * appears; the dots are decoration. With reduced motion the dots hold still (globals.css). */
export function WorkingDots({ label, className }: { label: string; className?: string }) {
  return (
    <span role="status" className={cn("inline-flex items-center gap-3 text-label-large", className)}>
      <span aria-hidden="true" className="inline-flex h-5 items-center gap-1">
        <span className="working-dot" />
        <span className="working-dot" />
        <span className="working-dot" />
      </span>
      {label}
    </span>
  );
}

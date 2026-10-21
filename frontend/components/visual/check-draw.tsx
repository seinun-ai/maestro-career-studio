import { cn } from "@/lib/utils";

/** Done, drawn once: the register's CircleCheck (`text-success`) whose tick draws itself when it
 * mounts (`animate-check-draw`, 300ms), for "Saved" before it settles. Mount it when the thing is
 * done; with reduced motion the tick is there at once. Decoration: the word beside it says it. */
export function CheckDraw({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={cn("size-4 shrink-0 text-success", className)}
    >
      <circle cx="12" cy="12" r="10" />
      <path d="m9 12 2 2 4-4" pathLength="24" className="animate-check-draw" />
    </svg>
  );
}

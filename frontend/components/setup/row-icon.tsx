import { CircleCheck, CircleX, Loader2 } from "lucide-react";

/** Per-row status glyph shared by the document-lane queue and resume import. */
export function RowIcon({ state }: { state: string }) {
  if (state === "done")
    return <CircleCheck aria-hidden className="text-primary size-4 shrink-0" />;
  if (state === "failed")
    return <CircleX aria-hidden className="text-destructive size-4 shrink-0" />;
  if (state === "uploading" || state === "parsing" || state === "running")
    return (
      <Loader2 aria-hidden className="text-muted-foreground size-4 shrink-0 animate-spin" />
    );
  return (
    <span
      aria-hidden
      className="border-muted-foreground/40 size-4 shrink-0 rounded-full border"
    />
  );
}

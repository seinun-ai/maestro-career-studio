import type { EditWords } from "@/lib/describe-edit";

/** A proposal's edits in plain words: what happens, then the new text quoted.
 *  Chat's suggestion card and the studio's Ask for changes sheet share it. */
export function EditWordsList({ edits }: { edits: EditWords[] }) {
  return (
    <ul className="mt-2 space-y-1.5 text-xs">
      {edits.map((edit, i) => (
        <li key={i} className="min-w-0">
          {edit.action}
          {edit.detail ? (
            <span className="text-muted-foreground block truncate">“{edit.detail}”</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

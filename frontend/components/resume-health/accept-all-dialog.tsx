"use client";

import { useId, useState } from "react";

import { DiffText } from "@/components/resume-health/judged-text";
import { rowText, type PassRow } from "@/components/resume-health/pass-rows";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/**
 * Accept all shown, first as a list: every row it will change, each with a checkbox (all checked
 * when it opens). Accept sends the checked rows on, as one write.
 */
export function AcceptAllDialog({
  open,
  onOpenChange,
  acceptable,
  onAccept,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  acceptable: PassRow[];
  onAccept: (rows: PassRow[]) => void;
}) {
  const [excluded, setExcluded] = useState<ReadonlySet<string>>(new Set());
  const [wasOpen, setWasOpen] = useState(open);
  if (wasOpen !== open) {
    setWasOpen(open);
    if (open) setExcluded(new Set());
  }
  const listId = useId();
  const chosen = acceptable.filter((row) => !excluded.has(row.key));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-[min(96vw,48rem)] max-w-[min(96vw,48rem)] flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle>Accept these new wordings?</DialogTitle>
          <DialogDescription>
            Each checked bullet changes, all in one new version of your resume. You can undo it.
          </DialogDescription>
        </DialogHeader>
        <ul className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
          {acceptable.map((row, i) => (
            <li key={row.key} className="flex items-start gap-3 border-b pb-3 last:border-b-0">
              <Checkbox
                checked={!excluded.has(row.key)}
                aria-labelledby={`${listId}-${i}`}
                onCheckedChange={() =>
                  setExcluded((current) => {
                    const next = new Set(current);
                    if (next.has(row.key)) next.delete(row.key);
                    else next.add(row.key);
                    return next;
                  })
                }
                className="mt-1"
              />
              <div className="min-w-0 flex-1 space-y-1">
                <p id={`${listId}-${i}`} className="text-muted-foreground text-xs">
                  {row.finding.label}
                </p>
                <DiffText oldText={row.original ?? ""} newText={rowText(row)} />
              </div>
            </li>
          ))}
        </ul>
        <DialogFooter>
          <Button size="sm" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            size="sm"
            variant="default"
            disabled={chosen.length === 0}
            onClick={() => {
              onOpenChange(false);
              onAccept(chosen);
            }}
          >
            Accept {chosen.length} new {chosen.length === 1 ? "wording" : "wordings"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

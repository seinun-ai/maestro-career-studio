"use client";

import { useEffect, useRef } from "react";
import { GuardedLink as Link } from "@/components/guarded-link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { RetryChip } from "@/components/retry-chip";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Popover,
  PopoverContent,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import { applyKbSync, getKbSyncStatus } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { formatTimeAgo } from "@/lib/format-date";
import { isLoadFailure } from "@/lib/query-state";
import type { SyncStatus } from "@/lib/types";

/** Every state renders at this height, so the toolbar row keeps its baseline
 *  and never reflows vertically when the query resolves or the count drops to
 *  zero. Width still varies with the label — a count pill and a "KB synced"
 *  chip are not the same words — so the min-width only keeps the pre-fetch placeholder
 *  from collapsing to a sliver. The `text-[0.8rem]` against HealthBadges'
 *  `text-sm` beside it is deliberate: the two chips match in height, and the
 *  smaller type keeps a secondary status from competing with the health grade. */
const CHIP =
  "inline-flex h-7 min-w-16 shrink-0 items-center gap-1.5 rounded-md border " +
  "border-transparent bg-muted/40 px-2 text-[0.8rem]";

function skillsNew(status: SyncStatus): number {
  return status.counts.skills_new;
}

/**
 * What the number on the pill means: information the Career KB does not have
 * yet. New points and new skills obviously qualify. So does `drift` — a bullet
 * whose wording has moved away from the KB's copy and which nothing has filed
 * yet — because pressing Sync is precisely what turns it into a filed note.
 * Leaving it out stranded it: the pill would say "up to date" while drift sat
 * there unrecorded forever, reachable from no other surface.
 *
 * `recorded_drift` is the one tier that must never be added in. It is drift the
 * KB already documents, so there is nothing left to do about it, and counting
 * it is what made the old bar nag at a resume that was finished.
 */
function actionableCount(status: SyncStatus): number {
  return status.counts.new + status.counts.drift + skillsNew(status);
}

/** Section → its noun, one and many. Bullet-bearing sections produce bullets;
 *  the rest produce whole items, which are the cheap ones to accept. */
const SECTION_NOUNS: [section: string, one: string, many: string][] = [
  ["experience", "new bullet", "new bullets"],
  ["projects", "new project bullet", "new project bullets"],
  ["education", "new education item", "new education items"],
  ["certifications", "new certification", "new certifications"],
  ["extra", "new item in other sections", "new items in other sections"],
];

function breakdownLines(status: SyncStatus): string[] {
  const counted = new Map<string, number>();
  for (const item of status.items) {
    if (item.tier !== "new") continue;
    counted.set(item.section, (counted.get(item.section) ?? 0) + 1);
  }
  const lines: string[] = [];
  for (const [section, one, many] of SECTION_NOUNS) {
    const n = counted.get(section) ?? 0;
    if (n > 0) lines.push(`${n} ${n === 1 ? one : many}`);
  }
  const skills = skillsNew(status);
  if (skills > 0) lines.push(`${skills} new skill${skills === 1 ? "" : "s"}`);
  // Says what adding will DO to it, because "drifted" alone reads like a
  // problem being reported rather than a note about to be filed.
  const drift = status.counts.drift;
  if (drift > 0) lines.push(`${drift} reworded (we'll note the change)`);
  // The tier vocabulary belongs to the backend; if it grows a shape this list
  // does not name, still say how much there is rather than nothing.
  if (lines.length === 0) lines.push(`${actionableCount(status)} to add`);
  return lines;
}

/**
 * The base studio's Career-KB sync control, in the toolbar's `status` slot.
 *
 * This was a full-width card above the editor, which is far too much furniture
 * for a count. It is a count-pill now, the same shape as "Review changes (N)":
 * the number is the whole message, and the breakdown and the action live behind
 * it. `status` cannot mutate from the bar (see StudioToolbar) — so the popover
 * holds the filled button, not the pill.
 */
export function KbSyncPill({ slug }: { slug: string }) {
  const queryClient = useQueryClient();
  // A successful sync can drop the count to zero, which unmounts the whole
  // Popover subtree — the trigger the user just activated included — and drops
  // keyboard focus to <body>. Chosen over keeping a dead trigger mounted: the
  // "Career history up to date" chip is the honest end state, and moving focus onto it also
  // announces the result, which a disabled leftover trigger would not.
  const restoreFocus = useRef(false);
  const chipRef = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!restoreFocus.current || !chipRef.current) return;
    restoreFocus.current = false;
    chipRef.current.focus();
  });

  const query = useQuery({
    queryKey: ["base-resumes", slug, "kb-sync-status"],
    queryFn: () => getKbSyncStatus(slug),
    retry: false,
    staleTime: 60_000,
  });
  const sync = useMutation({
    mutationFn: () => applyKbSync(slug),
    onSuccess: async (result) => {
      // `skills_added`, never `skills`: the latter is CATEGORY names, so two
      // new skills filed under one category summarised as "1 skills".
      const added = result.skills_added.length;
      const { created, drifted } = result;
      const also = [
        drifted > 0 ? `Noted ${drifted} wording ${drifted === 1 ? "change" : "changes"}.` : null,
        added > 0 ? `Added ${added} ${added === 1 ? "skill" : "skills"}.` : null,
      ].filter(Boolean);
      toast.success(
        <>
          Added {created} new {created === 1 ? "bullet" : "bullets"} to your career
          history.{also.length ? ` ${also.join(" ")}` : ""}{" "}
          <Link href="/career" className="underline">
            Review drafts
          </Link>
        </>,
      );
      restoreFocus.current = true;
      await queryClient.invalidateQueries({
        queryKey: ["base-resumes", slug, "kb-sync-status"],
      });
    },
    onError: (err: Error) => toast.error(couldnt("add to your career history", err)),
  });

  // The error branch comes FIRST: a failed status fetch must not be able to
  // render as the reassuring "up to date" chip. `isLoadFailure` keeps it
  // mounted through a retry; a status already loaded stays on a failed refresh.
  if (isLoadFailure(query)) {
    return (
      <RetryChip
        className={`${CHIP} text-muted-foreground hover:text-foreground hover:bg-muted/60 hover:border-border cursor-pointer transition-colors`}
        title="Couldn't check your career history. Try again."
        icon={<RefreshCw className="size-3.5" />}
        label="Career history unavailable"
        retrying={query.isFetching}
        onRetry={() => void query.refetch()}
      />
    );
  }

  if (!query.data) {
    // Same box, so the row is already at its final height before the fetch
    // lands and the toolbar does not grow a line when it does. `aria-busy` plus
    // the label give a screen reader something to say meanwhile — an empty box
    // announced nothing at all.
    return (
      <span
        className={CHIP}
        aria-busy="true"
        aria-label="Checking career history"
      >
        <Skeleton className="h-3 w-12" />
      </span>
    );
  }

  const status = query.data;
  const count = actionableCount(status);
  const recorded = status.counts.recorded_drift;

  if (count === 0) {
    const synced = status.last_kb_synced_at;
    return (
      <span
        ref={chipRef}
        // Focusable only programmatically: it is not a control, so it must not
        // join the tab order — but it has to be able to receive focus when the
        // trigger that was focused unmounts out from under the user.
        tabIndex={-1}
        className={`${CHIP} text-muted-foreground`}
        title={
          synced
            ? `Career history up to date, last updated ${formatTimeAgo(synced)}`
            : "Career history up to date"
        }
      >
        {/* Words, not a glyph: the abbreviation-plus-check was only legible to
            someone who already knew what the pill was. */}
        <Check className="size-3.5" />
        Career history up to date
      </span>
    );
  }

  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button variant="outline" size="sm">
            <RefreshCw />
            {/* "Add to career history", with the preposition: the label must
                say which way the data flows — nothing here touches the resume. */}
            Add to career history ({count})
          </Button>
        }
      />
      {/* A Popover, not a DropdownMenu: the contents are two lines of prose, a
          button and a link. `role="menu"` with no menuitem in it is an invalid
          tree and gives arrow keys nothing to move between. */}
      <PopoverContent align="end" className="w-72">
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-0.5">
            {/* Names the popup for screen readers via aria-labelledby. */}
            <PopoverTitle className="text-muted-foreground text-xs font-medium">
              Not yet in your career history
            </PopoverTitle>
            {breakdownLines(status).map((line) => (
              <p key={line} className="text-sm">
                {line}
              </p>
            ))}
          </div>
          {recorded > 0 && (
            // Outside the titled group on purpose: everything under "Not yet in
            // your career history" is work about to be done, and this is the
            // opposite — already filed, and never added to the count. Listing
            // it there said the title was wrong about its own contents.
            <p className="text-muted-foreground text-xs">
              {recorded} wording {recorded === 1 ? "change" : "changes"} already noted
            </p>
          )}
          <div className="flex items-center justify-between gap-2">
            <Button
              size="sm"
              onClick={() => sync.mutate()}
              disabled={sync.isPending}
            >
              {sync.isPending ? "Adding…" : "Add now"}
            </Button>
            <Link
              href="/career"
              className="text-muted-foreground hover:text-foreground text-xs"
            >
              Open career history
            </Link>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { LoadErrorState } from "@/components/load-error-state";
import { isLoadFailure } from "@/lib/query-state";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * The one shell every settings card renders through.
 *
 * Before this existed, each card hand-wrote `Card → header → isError ?
 * LoadErrorState : isLoading ? Skeleton : editor`, and the copies had drifted
 * into four different answers to "what happens when the fetch fails": five
 * cards showed the shared error state, Market showed a bare sentence with no
 * retry, and the three cards living inside `app/settings/page.tsx` showed
 * NOTHING — an empty card (Prompts, Models) or a skeleton that never resolved
 * (Auto-apply). A shell makes that a property of the shell, not of whoever
 * wrote the card last.
 *
 * Two details worth keeping:
 *
 * 1. **Readiness is `data !== undefined`, not `!isLoading`.** react-query
 *    leaves `data` undefined after an error while `isLoading` goes false, so
 *    an `isLoading` gate falls straight through to the success branch with no
 *    data — which is exactly how Prompts came to render "Advanced prompts (0)"
 *    on a failed fetch. `LoadErrorState`'s own docstring records the same trap.
 *
 * 2. **A failure only replaces the body when there is no body yet.** If a
 *    background refetch fails while the editor is on screen, the editor stays;
 *    swapping it for an error panel would discard whatever the user was
 *    typing. Errors win on first load, data wins afterwards.
 *
 * 3. **The header has one action slot, filled from the body.** See
 *    `SettingCardAction`. The title is a level-2 heading (`CardTitle` is a
 *    `div`), so each tab panel reads as a list of named cards.
 */
export type SettingQuery<T> = {
  data: T | undefined;
  isError: boolean;
  isFetching: boolean;
  fetchStatus: "fetching" | "paused" | "idle";
  /** How many times the query has failed; a refetch does not reset it. */
  errorUpdateCount: number;
  error: unknown;
  refetch: () => unknown;
};

function firstMessage(queries: SettingQuery<unknown>[]): string | undefined {
  for (const query of queries) {
    const message = (query.error as Error | null)?.message;
    if (message) return message;
  }
  return undefined;
}

/** The header's action node, filled once the card has committed. */
const HeaderSlot = createContext<HTMLElement | null>(null);

// Beside the title while the header has room; below the description when the
// header is narrower than 28rem (every card at 375, and a header crowded by two
// buttons at 768). The title and description sit in column 1 explicitly, so a
// narrow header never flows the description into the action's column. Stacked,
// a child that reserves width (the autosave status) starts at the left edge.
const ACTION =
  "flex flex-wrap items-center gap-2 empty:hidden @max-md/card-header:col-start-1 @max-md/card-header:row-span-1 @max-md/card-header:row-start-auto @max-md/card-header:justify-self-start @max-md/card-header:*:justify-start";

export function SettingCard<T>({
  id,
  title,
  description,
  errorTitle,
  skeleton = "h-40 w-full",
  query,
  also,
  children,
}: {
  /** Anchor for deep links (`/profile#autofill`). Every settings card has one. */
  id?: string;
  title: string;
  description?: ReactNode;
  errorTitle?: string;
  /** Tailwind sizing for the loading placeholder, so it matches the real body. */
  skeleton?: string;
  query: SettingQuery<T>;
  /** Extra queries the body also needs. They gate loading and error; only the
   *  primary query's data is handed to `children`. */
  also?: SettingQuery<unknown>[];
  children: (value: T) => ReactNode;
}) {
  const queries: SettingQuery<unknown>[] = [query, ...(also ?? [])];
  const ready = queries.every((q) => q.data !== undefined);
  const loadFailed = queries.some((q) => isLoadFailure(q));
  // A callback ref, not an effect: React sets it in the commit, and the body's
  // portal renders into it on the next render.
  const [slot, setSlot] = useState<HTMLElement | null>(null);

  return (
    <Card id={id}>
      <CardHeader>
        <CardTitle role="heading" aria-level={2} className="col-start-1">
          {title}
        </CardTitle>
        {description ? (
          <CardDescription className="col-start-1">{description}</CardDescription>
        ) : null}
        <CardAction ref={setSlot} className={ACTION} />
      </CardHeader>
      <CardContent className="@container/setting">
        <HeaderSlot value={slot}>
          {loadFailed && !ready ? (
            <LoadErrorState
              className="py-8"
              title={errorTitle}
              detail={firstMessage(queries)}
              retrying={queries.some((q) => q.isFetching)}
              onRetry={() => {
                for (const q of queries) void q.refetch();
              }}
            />
          ) : !ready ? (
            <Skeleton className={skeleton} />
          ) : (
            children(query.data as T)
          )}
        </HeaderSlot>
      </CardContent>
    </Card>
  );
}

/**
 * Renders its children into the card header, right of the title: the autosave
 * status, Persona's "Draft from my career", the model list's find buttons.
 *
 * A PORTAL, not a prop. Each of those is driven by state that belongs to the
 * editor inside the body (the autosave queue, the draft request, the sync
 * mutation); a header prop would mean lifting that state out through an effect
 * for a placement. The portal leaves the state where it is and puts the DOM in
 * the header, so a screen reader meets the status after the title and
 * description and before the fields it describes. (It replaces the old status
 * row at the top of the body, which left an empty row on a one-field card such
 * as Market.) Nothing renders on the card's first frame; the slot fills on the
 * next. One slot per card: a second `SettingCardAction` lands beside the first
 * with nothing between them.
 */
export function SettingCardAction({ children }: { children: ReactNode }) {
  const slot = useContext(HeaderSlot);
  return slot ? createPortal(children, slot) : null;
}

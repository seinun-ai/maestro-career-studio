"use client";

import type { ReactNode } from "react";

import { LoadErrorState } from "@/components/load-error-state";
import {
  Card,
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
 */
export type SettingQuery<T> = {
  data: T | undefined;
  isError: boolean;
  isFetching: boolean;
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
  const loadFailed = queries.some((q) => q.isError);

  return (
    <Card id={id}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent>
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
      </CardContent>
    </Card>
  );
}

/**
 * Where the autosave indicator goes: top of the card body, right-aligned.
 *
 * The header is title-and-description only, on purpose. Every control a
 * settings card owns — this indicator, Persona's "Draft from my career",
 * the catalog's Sync buttons — is driven by state belonging to the editor
 * inside the body, so a header slot would mean lifting that state up through
 * an effect for a purely cosmetic placement. Market used to put the indicator
 * in the header and Job preferences in the body; this is the one answer, and
 * `SettingCard` gives the header no slot so the question cannot be reopened.
 */
export function AutosaveRow({ children }: { children: ReactNode }) {
  return <div className="mb-4 flex justify-end">{children}</div>;
}

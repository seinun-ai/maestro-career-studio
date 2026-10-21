"use client";

import { createContext, useContext, useId, type ReactNode } from "react";

import { SettingCard, SettingCardAction, type SettingQuery } from "@/components/settings/setting-card";
import { Button } from "@/components/ui/button";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { PROFILE_TILES, cardId, type TileId } from "@/lib/profile-tiles";
import { cn } from "@/lib/utils";

/** What a tile says beside its title: Ready, Needs you, or a count in words ("3 countries"). */
export type TileState = { kind: "ready" } | { kind: "needs" } | { kind: "count"; text: string } | { kind: "none" };

/** One tile: its state, a short summary of what it holds (real values, never examples), a quiet note, and the
 *  editor its panel shows. */
export type TileView = {
  state: TileState;
  summary: ReactNode;
  note?: string;
  panel: ReactNode;
};

export function tileTitle(id: TileId): string {
  return PROFILE_TILES.find((tile) => tile.id === id)?.title ?? id;
}

export function TileStateMark({ id, state }: { id?: string; state: TileState }) {
  if (state.kind === "ready") {
    return (
      <span id={id} className="inline-flex shrink-0 items-center gap-1 text-label-medium text-success">
        <CONCEPT_ICONS.done aria-hidden="true" className="size-4" />
        Ready
      </span>
    );
  }
  if (state.kind === "needs") {
    // The Needs you chip's role pair (status-chip.tsx): round, because it is a state.
    return (
      <span
        id={id}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-attention-container px-2 py-0.5 text-label-small text-on-attention-container"
      >
        <span aria-hidden="true" className="size-1.5 rounded-full bg-attention" />
        Needs you
      </span>
    );
  }
  if (state.kind === "count") {
    return (
      <span id={id} className="shrink-0 text-label-medium text-muted-foreground tabular-nums">
        {state.text}
      </span>
    );
  }
  return null;
}

/** A tile in the grid: a button that opens its editor under the grid (`aria-expanded`), named by its title and
 *  state, described by its summary. */
export function TileButton({
  id,
  domId,
  view,
  open,
  regionId,
  onToggle,
}: {
  id: TileId;
  /** The button's own id, for Close to hand focus back to. */
  domId: string;
  view: TileView;
  open: boolean;
  regionId: string;
  onToggle: () => void;
}) {
  const titleId = useId();
  const stateId = useId();
  const summaryId = useId();
  return (
    <button
      id={domId}
      type="button"
      aria-expanded={open}
      aria-controls={regionId}
      aria-labelledby={view.state.kind === "none" ? titleId : `${titleId} ${stateId}`}
      aria-describedby={summaryId}
      onClick={onToggle}
      className={cn(
        "flex h-full w-full cursor-pointer flex-col gap-2.5 rounded-corner-md bg-card p-4.5 text-left outline-none transition-colors duration-(--duration-short3) ease-standard hover:bg-surface-container-low focus-visible:ring-3 focus-visible:ring-ring",
        open ? "ring-2 ring-primary" : view.state.kind === "needs" && "ring-1 ring-attention-container ring-inset",
      )}
    >
      <span className="flex items-center gap-2.5">
        <span id={titleId} className="min-w-0 flex-1 text-title-small">
          {tileTitle(id)}
        </span>
        <TileStateMark id={stateId} state={view.state} />
      </span>
      <span id={summaryId} className="flex min-w-0 flex-col gap-1.5 text-body-small text-muted-foreground">
        {view.summary}
      </span>
      {view.note ? <span className="text-label-small text-muted-foreground">{view.note}</span> : null}
    </button>
  );
}

const TileClose = createContext<(() => void) | null>(null);

/** The open tile's Close, for the card its panel shows. */
export function TileCloseProvider({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  return <TileClose value={onClose}>{children}</TileClose>;
}

/**
 * A tile's editor: a settings card (the one shell: header, loading, the failure with Try again) under the
 * tile's title, with the card id its deep links name (`autofill-personal`), and Close last in its header.
 */
export function TileCard<T>({
  tile,
  description,
  query,
  also,
  errorTitle,
  skeleton,
  children,
}: {
  tile: TileId;
  description?: ReactNode;
  query: SettingQuery<T>;
  also?: SettingQuery<unknown>[];
  errorTitle: string;
  skeleton?: string;
  children: (value: T) => ReactNode;
}) {
  const close = useContext(TileClose);
  const section = PROFILE_TILES.find((t) => t.id === tile);
  return (
    <SettingCard
      id={section ? cardId(section) : tile}
      title={tileTitle(tile)}
      description={description}
      errorTitle={errorTitle}
      skeleton={skeleton}
      query={query}
      also={also}
    >
      {(value) => (
        <>
          {children(value)}
          {close ? (
            <SettingCardAction>
              <Button type="button" variant="ghost" size="sm" onClick={close}>
                Close
              </Button>
            </SettingCardAction>
          ) : null}
        </>
      )}
    </SettingCard>
  );
}

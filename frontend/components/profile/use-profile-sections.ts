"use client";

import { useState, useSyncExternalStore } from "react";

import { sectionForAnchor, type FoldId, type TileId } from "@/lib/profile-tiles";

function subscribeToLocation(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  window.addEventListener("popstate", onChange);
  return () => {
    window.removeEventListener("hashchange", onChange);
    window.removeEventListener("popstate", onChange);
  };
}
const readAnchor = () => window.location.hash.slice(1);
// The server cannot see a hash: hydrate with none, then React re-renders with the real one.
const noAnchor = () => "";

/**
 * Which tile is open (one at a time) and which folds are, on Profile. A NEW hash opens the tile or fold that
 * holds it (`lib/profile-tiles.ts`): a deep link (`anchorHref("/profile", "autofill-work_auth")`, an old
 * `?tab=autofill#autofill-eeo` bookmark), and `useFocusSection`'s jump to a card that is not shown, which
 * announces its anchor with a `hashchange`. Closing a section the hash names drops the hash (no event), so a
 * later link to the same card opens it again.
 */
export function useProfileSections() {
  const anchor = useSyncExternalStore(subscribeToLocation, readAnchor, noAnchor);
  const [tile, setTile] = useState<TileId | null>(null);
  const [folds, setFolds] = useState<readonly FoldId[]>([]);
  const [seen, setSeen] = useState("");
  if (anchor !== seen) {
    setSeen(anchor);
    const at = sectionForAnchor(anchor);
    if (at?.kind === "tile") setTile(at.id);
    else if (at?.kind === "fold" && !folds.includes(at.id)) setFolds([...folds, at.id]);
  }

  const forget = (id: TileId | FoldId) => {
    if (sectionForAnchor(readAnchor())?.id !== id) return;
    const { pathname, search } = window.location;
    window.history.replaceState(null, "", `${pathname}${search}`);
  };

  return {
    tile,
    openTile: (id: TileId | null) => {
      if (tile !== null && tile !== id) forget(tile);
      setTile(id);
    },
    folds,
    setFold: (id: FoldId, open: boolean) => {
      if (!open) forget(id);
      setFolds((current) =>
        open ? (current.includes(id) ? current : [...current, id]) : current.filter((f) => f !== id),
      );
    },
  };
}

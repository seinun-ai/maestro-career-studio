/**
 * Which editors' edits are not on the server yet, where several editors change one value that saves whole
 * (Profile's answers: Next up, Contact, the folds and the rest, through one `useAutosave`). No imports:
 * `node --test` loads it as it is (save-surfaces.test.ts).
 *
 * Every edit gets the next number. A write that goes out carries every edit up to the newest (the whole
 * value), so when it lands those are on the server. An editor shows Saving while its own newest edit waits
 * for a write, Not saved when the last write carrying it failed, and nothing when it has no such edit: never
 * Saved before the write carrying its edit has landed, and never another editor's save.
 */
export type SurfaceSaves = {
  /** The newest edit's number. */
  readonly seq: number;
  /** Each editor's newest edit. */
  readonly edits: Readonly<Record<string, number>>;
  /** Every edit up to this number is on the server. */
  readonly saved: number;
};

export const NO_EDITS: SurfaceSaves = { seq: 0, edits: {}, saved: 0 };

/** One more edit, from `surface`. */
export function edited(state: SurfaceSaves, surface: string): SurfaceSaves {
  const seq = state.seq + 1;
  return { ...state, seq, edits: { ...state.edits, [surface]: seq } };
}

/** A write that carried every edit up to `through` landed. An older write answering late changes nothing. */
export function landed(state: SurfaceSaves, through: number): SurfaceSaves {
  return through > state.saved ? { ...state, saved: through } : state;
}

/** One editor's status, from the autosave's own `pending` (a write in flight or queued, which carries every
 *  edit not yet saved) and `failed` (the newest value is not on the server). */
export function surfaceStatus(
  state: SurfaceSaves,
  surface: string,
  save: { pending: boolean; failed: boolean },
): { pending: boolean; failed: boolean } {
  const waiting = (state.edits[surface] ?? 0) > state.saved;
  return { pending: save.pending && waiting, failed: save.failed && waiting };
}

/**
 * The Jobs list's three filters (Status, the stage chips, the source toggle): where each lives in the URL and
 * in session memory, and which of the two the page starts from. No imports: `node --test` loads this file as it is.
 */

export const STAGE_FILTERS = ["pdf_ready", "tailored", "gaps"] as const;
export type StageFilter = (typeof STAGE_FILTERS)[number];
export type TrackerSource = "all" | "user" | "agent";
export type TrackerFilters = { filter: string; stage: StageFilter | null; source: TrackerSource };
type Axis = keyof TrackerFilters;

// The names predate the page being called Jobs and stay, so bookmarks and the job page's prev/next keep working.
export const TRACKER_URL_KEYS: Record<Axis, string> = { filter: "status", stage: "stage", source: "source" };
export const TRACKER_STORE_KEYS: Record<Axis, string> = {
  filter: "cs-tracker-filter",
  stage: "cs-tracker-stage",
  source: "cs-tracker-source",
};

/**
 * The state the page opens with. A URL that carries any of the three keys is the whole state (a missing key
 * takes its default); session memory is read only when the URL carries none, so a link never mixes with it.
 * `filters` is every Status value, `"all"` included; an unknown value falls back to its default.
 */
export function resolveTrackerFilters(
  url: (key: string) => string | null,
  stored: (key: string) => string | null,
  filters: readonly string[],
): TrackerFilters {
  const axes: Axis[] = ["filter", "stage", "source"];
  const fromUrl = axes.some((a) => url(TRACKER_URL_KEYS[a]) !== null);
  const read = (a: Axis) => (fromUrl ? url(TRACKER_URL_KEYS[a]) : stored(TRACKER_STORE_KEYS[a]));
  const filter = read("filter");
  const stage = read("stage");
  const source = read("source");
  return {
    filter: filter && filters.includes(filter) ? filter : "all",
    stage: stage && (STAGE_FILTERS as readonly string[]).includes(stage) ? (stage as StageFilter) : null,
    source: source === "user" || source === "agent" ? source : "all",
  };
}

/** The page's URL for a state: defaults are left out, so the plain list is `/applications`. */
export function trackerHref(state: TrackerFilters): string {
  const params = new URLSearchParams();
  if (state.filter !== "all") params.set(TRACKER_URL_KEYS.filter, state.filter);
  if (state.stage) params.set(TRACKER_URL_KEYS.stage, state.stage);
  if (state.source !== "all") params.set(TRACKER_URL_KEYS.source, state.source);
  const qs = params.toString();
  return qs ? `/applications?${qs}` : "/applications";
}

/**
 * The Jobs list's three filters (Status, the stage chips, the source toggle): where each lives in the URL and
 * in session memory, and which of the two the page starts from. No imports: `node --test` loads this file as it is.
 */

export const STAGE_FILTERS = ["pdf_ready", "tailored", "gaps"] as const;
export type StageFilter = (typeof STAGE_FILTERS)[number];

/** The Status value the list opens with: every job still in play. Closed jobs are one chip away. */
export const DEFAULT_FILTER = "active";

/**
 * The chips over the list. Each is a preset of the Status filter and the stage chip, so the URL and session
 * memory keep the names they had (`?status=`, `?stage=`); Filters can set a state no chip names.
 */
export const TRACKER_VIEWS = ["active", "ready", "waiting", "interviews", "closed"] as const;
export type TrackerView = (typeof TRACKER_VIEWS)[number];
type ViewFilter = typeof DEFAULT_FILTER | "applied" | "interviews" | "closed";
export const VIEW_FILTERS: Readonly<Record<TrackerView, { filter: ViewFilter; stage: StageFilter | null }>> = {
  active: { filter: "active", stage: null },
  ready: { filter: "active", stage: "pdf_ready" },
  waiting: { filter: "applied", stage: null },
  interviews: { filter: "interviews", stage: null },
  closed: { filter: "closed", stage: null },
};

/** The chip a state is, or null when Filters set something no chip names. */
export function viewOf(state: { filter: string; stage: StageFilter | null }): TrackerView | null {
  return TRACKER_VIEWS.find((v) => VIEW_FILTERS[v].filter === state.filter && VIEW_FILTERS[v].stage === state.stage) ?? null;
}
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
 * `filters` is every Status value, `"all"` and `DEFAULT_FILTER` included; an unknown value falls back to its
 * default.
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
    filter: filter && filters.includes(filter) ? filter : DEFAULT_FILTER,
    stage: stage && (STAGE_FILTERS as readonly string[]).includes(stage) ? (stage as StageFilter) : null,
    source: source === "user" || source === "agent" ? source : "all",
  };
}

/** The page's URL for a state: defaults are left out, so the plain list is `/applications`. */
export function trackerHref(state: TrackerFilters): string {
  const params = new URLSearchParams();
  if (state.filter !== DEFAULT_FILTER) params.set(TRACKER_URL_KEYS.filter, state.filter);
  if (state.stage) params.set(TRACKER_URL_KEYS.stage, state.stage);
  if (state.source !== "all") params.set(TRACKER_URL_KEYS.source, state.source);
  const qs = params.toString();
  return qs ? `/applications?${qs}` : "/applications";
}

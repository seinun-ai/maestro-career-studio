"use client";

import { Suspense, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { GuardedLink as Link } from "@/components/guarded-link";
import { useRouter } from "next/navigation";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Check, FilePlus2, KeyRound, Inbox, SendHorizontal, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { JobOwnershipPopover } from "@/components/job-ownership";
import { isSyncQueued, jobOwnershipView, ownershipSays } from "@/lib/job-ownership";

import { CompanyMonogram } from "@/components/company-monogram";
import { JobMorph } from "@/components/job-morph";
import { EmptyState, TableFrame } from "@/components/empty-state";
import { filterChipClass } from "@/components/filter-chips";
import { FiltersButton } from "@/components/filters-button";
import { ListCapNotice } from "@/components/list-cap-notice";
import { ListSearch } from "@/components/list-search";
import { ListToolbar } from "@/components/list-toolbar";
import { LoadErrorState } from "@/components/load-error-state";
import { SelectToggle } from "@/components/selection-bar";
import { GettingStartedCard } from "@/components/setup/getting-started-card";
import { useSidebarHidden } from "@/components/sidebar-reveal-trigger";
import { SourceToggle } from "@/components/source-toggle";
import { LaneDot, SavedJobChip, StatusChip, StatusDot, statusLabel } from "@/components/status-chip";
import { NextStep, ScoreBar } from "@/components/visual";
import { useConfirm } from "@/components/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LINKED_APPLICATION_MARK, agentMarkLabel, queuedToast } from "@/lib/agent-name";
import { apiFetch, promoteJobToAgentQueue } from "@/lib/api";
import { couldnt, loadErrorDetail } from "@/lib/error-text";
import { focusIfDropped, focusReturnPoint, focusSuccessor } from "@/lib/focus";
import { formatShortDate } from "@/lib/format-date";
import { selectedAmong } from "@/lib/inbox-lanes";
import { jobMetaLine } from "@/lib/job-meta";
import { statusDate } from "@/lib/job-standing";
import { isListCapped } from "@/lib/list-cap";
import { nextStep, nextStepHref, type Rung } from "@/lib/next-step";
import { chipCount, matchesFilter } from "@/lib/tracker-counts";
import {
  DEFAULT_FILTER,
  STAGE_FILTERS,
  TRACKER_VIEWS,
  VIEW_FILTERS,
  type StageFilter,
  type TrackerView,
  viewOf,
} from "@/lib/tracker-filters";
import { isLoadFailure } from "@/lib/query-state";
import { anchorHref } from "@/lib/settings-tabs";
import { cn } from "@/lib/utils";
import {
  APPLICATION_STATUSES,
  type ApplicationStatus,
  type ApplicationSummary,
  type Job,
  type SetupStatus,
} from "@/lib/types";
import { PageHeader, PageShell } from "@/components/page-shell";
import { useBaseResumeLabel } from "@/hooks/use-base-resume-label";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { JobsBulkBar, bulkCan, useJobBulkActions, type JobBulkAction } from "./job-bulk";
import { storeValue, useTrackerFilters } from "./use-tracker-filters";
import { CONCEPT_ICONS } from "@/lib/concept-icons";

const MoreIcon = CONCEPT_ICONS.more;

// "saved" is the synthetic no-application state (a captured job you haven't
// started on) — one name everywhere, not aspiring/not-applied/jobs.
// Agent-lane filters cover proposal_status on saved jobs. Keys stay distinct
// from APPLICATION_STATUSES — proposal "accepted" (Queued) must not collide
// with application "accepted" (Offer), proposal "rejected" (you passed on the
// agent's proposal) must not read like application "rejected" (they passed on
// you), and the application's own "skipped" is your draft, hence
// "agent_skipped", worded Skipped like it. It absorbs expired proposals too:
// either way you are not pursuing that job. The row chip still says Expired.
const AGENT_LANE_FILTERS = [
  "proposed",
  "queued",
  "needs_you",
  "agent_skipped",
] as const;
// The three dropdown groups, in render order — FILTERS is derived from them so
// a new key can never type-check and filter rows yet never appear as an option.
// "active", "interviews" and "closed" are groups of the keys below (lib/tracker-counts.ts
// `matchesFilter`): the list's chips set them, and the Status filter names them too.
const TOP_FILTERS = ["all", DEFAULT_FILTER, "interviews", "closed", "saved"] as const;
const FILTERS = [
  ...TOP_FILTERS,
  ...APPLICATION_STATUSES,
  ...AGENT_LANE_FILTERS,
] as const;
type Filter = (typeof FILTERS)[number];
type AgentLaneFilter = (typeof AGENT_LANE_FILTERS)[number];

const AGENT_LANE_LABELS: Record<AgentLaneFilter, string> = {
  proposed: "To review",
  queued: "Queued",
  needs_you: "Needs you",
  agent_skipped: "Skipped",
};

// The list's chips, each a preset of the Status filter and the stage (lib/tracker-filters.ts `VIEW_FILTERS`).
const VIEW_LABELS: Record<TrackerView, string> = {
  active: "All active",
  ready: "Ready to apply",
  waiting: "Waiting to hear",
  interviews: "Interviews",
  closed: "Closed",
};

function filterLabel(value: Filter): string {
  if (value === "all") return "All";
  if (value === "saved") return "Saved";
  if (value === "active") return VIEW_LABELS.active;
  if (value === "interviews") return VIEW_LABELS.interviews;
  if (value === "closed") return VIEW_LABELS.closed;
  if ((AGENT_LANE_FILTERS as readonly string[]).includes(value)) {
    return AGENT_LANE_LABELS[value as AgentLaneFilter];
  }
  return statusLabel(value);
}

// Session-scoped memory: coming back via the sidebar link (no URL params)
// restores the last filter, stage chip and source instead of resetting to All
// (useTrackerFilters), and the job page's prev/next arrows walk the tracker's
// last visible row order.
const SEQUENCE_STORE_KEY = "cs-tracker-seq";

// The API's max page (routers/applications.py, routers/jobs.py: le=500).
// Older rows are not loaded; the list says so at its end (ListCapNotice).
const LIST_LIMIT = 500;

// Saved jobs without an application, from one source. One definition for the
// list's query and the Agents segment's prefetch, so the two share a cache entry.
function savedJobsQuery(savedSource: "user" | "agent") {
  return {
    queryKey: ["jobs", "without-application", savedSource],
    queryFn: () =>
      apiFetch<Job[]>(
        `/api/jobs?without_application=true&source=${savedSource}&limit=${LIST_LIMIT}`,
      ),
  };
}

/** A row's ⋯ trigger: where focus goes once the row's Queue in Agent inbox closes the menu. */
function moreActions(key: string): HTMLElement | null {
  return document.querySelector<HTMLElement>(`[data-row="${key}"] [aria-label="More actions"]`);
}

type SortKey = "created_at" | "role" | "status" | "applied_at" | "ats";

// The sort menu: the Added and Applied columns went, and their orders stay here. Values that describe
// themselves, as the Agent inbox's: the toolbar has no captions.
const SORTS = {
  added: { label: "Newest first", key: "created_at", dir: "desc" },
  oldest: { label: "Oldest first", key: "created_at", dir: "asc" },
  applied: { label: "Recently applied", key: "applied_at", dir: "desc" },
  match: { label: "Best match first", key: "ats", dir: "desc" },
  title: { label: "Job title A–Z", key: "role", dir: "asc" },
  status: { label: "By status", key: "status", dir: "asc" },
} as const satisfies Record<string, { label: string; key: SortKey; dir: "asc" | "desc" }>;
type SortName = keyof typeof SORTS;

type Row =
  | { kind: "application"; app: ApplicationSummary }
  | { kind: "saved"; job: Job };

/** Status-column key for a row — what the filter dropdown aggregates on. */
function rowFilterKey(r: Row): Exclude<Filter, "all"> {
  if (r.kind === "application") {
    return (r.app.status ?? "draft") as ApplicationStatus;
  }
  const ps = r.job.proposal_status;
  if (ps === "pending_review") return "proposed";
  if (ps === "accepted") return "queued";
  if (ps === "rejected" || ps === "expired") return "agent_skipped";
  if (ps === "needs_decision" || ps === "needs_human") return "needs_you";
  return "saved";
}

/** The score a row shows: an application's own, a saved job's best base score. Null = never scored. */
function rowScore(r: Row): number | null {
  return (r.kind === "saved" ? r.job.best_ats_score : r.app.ats_score) ?? null;
}

// The inbox lane each agent-lane filter stands for, so its dot is the lane chip's own (LaneDot).
const AGENT_LANE_DOT_STATUS: Record<AgentLaneFilter, string> = {
  proposed: "pending_review",
  queued: "accepted",
  needs_you: "needs_decision",
  agent_skipped: "rejected",
};

/** A filter's own dot: a status dot, a lane dot, or none for All and Saved. */
function FilterDot({ value }: { value: Filter }) {
  if ((APPLICATION_STATUSES as readonly string[]).includes(value)) {
    return <StatusDot status={value as ApplicationStatus} />;
  }
  if ((AGENT_LANE_FILTERS as readonly string[]).includes(value)) {
    return <LaneDot status={AGENT_LANE_DOT_STATUS[value as AgentLaneFilter]} />;
  }
  return null;
}

/** The row's rung from the server (services/stage.py); undefined from a backend that predates it. */
function rowStage(r: Row): Rung | undefined {
  return r.kind === "saved" ? r.job.stage : r.app.stage;
}

// The stage filter (under Filters): a filter of its own that ANDs with the Status filter. Ready to apply is
// also a chip, with the active jobs.
const STAGE_LABELS: Record<StageFilter, string> = {
  pdf_ready: "Ready to apply",
  tailored: "Tailored, review",
  gaps: "Gaps open",
};

function rowCompany(r: Row): string {
  return (r.kind === "saved" ? r.job.company : r.app.job_company) ?? "";
}

function rowTitle(r: Row): string {
  return (r.kind === "saved" ? r.job.title : r.app.job_title) ?? "";
}

/** A row's React key, and the `data-row` a status change finds its row by. */
function rowKey(r: Row): string {
  return r.kind === "saved" ? `job-${r.job.id}` : `app-${r.app.id}`;
}

/** What a picked row lets Select mode's bar do: the actions its own controls offer, under the same locks. */
function bulkActionsOf(r: Row): JobBulkAction[] {
  const ownership = jobOwnershipView(r.kind === "saved" ? r.job.ownership : r.app.ownership);
  const out: JobBulkAction[] = [];
  // The status chip: an application's, locked while its job moves between copies.
  if (r.kind === "application" && ownership.canRequest) out.push("status");
  // The row menu's Queue in Agent inbox: a saved job with no proposal yet.
  if (r.kind === "saved" && !r.job.proposal_status && ownership.canWrite) out.push("queue");
  if (ownership.canWrite) out.push(r.kind === "saved" ? "deleteJob" : "deleteApp");
  return out;
}

function ApplicationsContent() {
  const router = useRouter();
  const qc = useQueryClient();
  const confirm = useConfirm();
  const sidebarHidden = useSidebarHidden();
  const baseName = useBaseResumeLabel();
  const { filter, stage: stageFilter, source, update } = useTrackerFilters(FILTERS);
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortName>("added");
  const sortKey = SORTS[sort].key;
  const sortDir = SORTS[sort].dir;
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filtersId = useId();
  // Select mode, the Agent inbox's: a checkbox on every row, the bar at the bottom, a row's click picks it.
  const [selectMode, setSelectMode] = useState(false);
  // The row a key opened: it draws its monogram and title without their morph names (keyboard actions never animate).
  const [unmorphed, setUnmorphed] = useState<string | null>(null);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const selectButton = useRef<HTMLButtonElement>(null);
  // Set when the bar leaves (Done, or its action landed): focus goes back to Select in that commit.
  const barLeft = useRef(false);

  // Two queries: the summary list carries job fields server-side now, and
  // one unfiltered fetch gives the filter chips their counts for free.
  const apps = useQuery({
    queryKey: ["applications"],
    queryFn: () => apiFetch<ApplicationSummary[]>(`/api/applications?limit=${LIST_LIMIT}`),
  });
  // Saved jobs: agent captures show only under the Agents toggle (the inbox
  // owns that inventory otherwise), and they are fetched apart from the
  // user's own, so a busy hunt cannot push the user's saved jobs out of the
  // 500 (one mixed page did).
  const savedSource = source === "agent" ? "agent" : "user";
  // The other source's first fetch keeps the rows on screen: a skeleton in their place shortened
  // the page and dropped the reader at the top. Those rows are the LAST source's, so while they
  // show (`stale`) the list is marked busy and nothing is counted from them.
  const savedJobs = useQuery({ ...savedJobsQuery(savedSource), placeholderData: keepPreviousData });
  const stale = savedJobs.isPlaceholderData;
  // First run: with no API key, saving a job can't read it, so the empty state says the key comes first.
  // The same query as the Getting started card below (one request).
  const setup = useQuery({
    queryKey: ["setup-status"],
    queryFn: () => apiFetch<SetupStatus>("/api/setup/status"),
  });
  const needsKey = setup.data?.model_key.done === false;

  // A status outside the active filter takes its row, and the chip focus went
  // back to, out of the list once the refetch lands. Where focus goes then is
  // read when the status is picked, while the row is still there.
  const leaving = useRef<{ key: string; next: () => HTMLElement | null } | null>(null);
  // Queue in Agent inbox can take its row out of the list (a Saved filter), and the row's ⋯ with it: where
  // focus goes is read at the click, while the row is there.
  const queued = useRef<{ jobId: string; next: () => HTMLElement | null } | null>(null);

  const patchStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: ApplicationStatus }) =>
      apiFetch<unknown>(`/api/applications/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }),
    // The chip turns at once; a failed PATCH puts every cached list back.
    onMutate: async ({ id, status }) => {
      await qc.cancelQueries({ queryKey: ["applications"] });
      const previous = qc.getQueriesData<ApplicationSummary[]>({ queryKey: ["applications"] });
      qc.setQueriesData<ApplicationSummary[]>({ queryKey: ["applications"] }, (rows) =>
        rows?.map((row) => (row.id === id ? { ...row, status } : row)),
      );
      return { previous };
    },
    // A job on the other copy takes the change at the next sync (202): the refetch puts the chip back meanwhile.
    onSuccess: (data) => {
      if (isSyncQueued(data)) toast.success("Sent at the next sync");
      void qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (err: Error, _vars, context) => {
      context?.previous.forEach(([key, rows]) => qc.setQueryData(key, rows));
      leaving.current = null;
      toast.error(couldnt("change the status", err));
    },
    // Returned, so isPending lasts until the refetch lands and the chip never shows the old label.
    onSettled: (_data, _err, { id }) => {
      const jobId = apps.data?.find((a) => a.id === id)?.job_id;
      if (jobId) void qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
      return qc.invalidateQueries({ queryKey: ["applications"] });
    },
  });

  const deleteApp = useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/api/applications/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Application deleted");
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (err: Error) => toast.error(couldnt("delete the application", err)),
  });

  // Promote a scored-but-unproposed capture into the agent queue: file a
  // proposal from the job's stored base scores, then straight to accepted —
  // this click IS the user's triage decision. The escape hatch for good
  // captures that missed the hunt's per-run proposal cap.
  const promoteJob = useMutation({
    mutationFn: (jobId: string) => promoteJobToAgentQueue(jobId),
    onSuccess: (queue) => toast.success(queuedToast(queue)),
    // Whatever happened, a proposal may now exist (filed, then the accept failed): show it.
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["jobs", "without-application"] });
      qc.invalidateQueries({ queryKey: ["proposals"] });
    },
    onError: (err: Error) => {
      queued.current = null;
      toast.error(couldnt("queue the job", err));
    },
  });
  // A double click filed two accepted proposals for one job.
  const promoteJobOnce = useSingleFlight(promoteJob.mutate);

  const deleteJob = useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/api/jobs/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Job deleted");
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["applications"] });
    },
    onError: (err: Error) => toast.error(couldnt("delete the job", err)),
  });

  const allRows = useMemo<Row[]>(() => {
    const appRows: Row[] = (apps.data ?? []).map((app) => ({
      kind: "application",
      app,
    }));
    // Already the toggle's source (the query above filters server-side).
    const savedRows: Row[] = (savedJobs.data ?? []).map((job) => ({
      kind: "saved" as const,
      job,
    }));
    return [...savedRows, ...appRows];
  }, [apps.data, savedJobs.data]);

  // Source filter before counts so chip totals match what is visible.
  const sourceScopedRows = useMemo(() => {
    if (source === "all") return allRows;
    return allRows.filter(
      (r) => r.kind === "saved" || r.app.source === source,
    );
  }, [allRows, source]);

  // Every Status value's count, the groups included (a row counts under each value that shows it).
  const counts = useMemo(() => {
    const keys = sourceScopedRows.map(rowFilterKey);
    return new Map<Filter, number>(FILTERS.map((f) => [f, keys.filter((k) => matchesFilter(f, k)).length]));
  }, [sourceScopedRows]);

  // Empty buckets are noise — drop them, except "all" and whatever is active
  // (an option must never vanish out from under the user who picked it).
  const visibleFilters = (group: readonly Filter[]) =>
    group.filter((f) => (counts.get(f) ?? 0) > 0 || f === "all" || f === filter);
  const topOptions = visibleFilters(TOP_FILTERS);
  const appOptions = visibleFilters(APPLICATION_STATUSES);
  const laneOptions = visibleFilters(AGENT_LANE_FILTERS);
  // Counted from rows the other source has not replaced yet, a number would be wrong.
  const countOf = (f: Filter) => (stale ? "…" : String(counts.get(f) ?? 0));
  const filterOption = (f: Filter) => (
    <SelectItem key={f} value={f}>
      <FilterDot value={f} />
      {`${filterLabel(f)} · ${countOf(f)}`}
    </SelectItem>
  );

  const filtered = useMemo(() => {
    let list = sourceScopedRows;
    if (filter !== "all") {
      list = list.filter((r) => matchesFilter(filter, rowFilterKey(r)));
    }
    if (stageFilter) {
      list = list.filter((r) => rowStage(r) === stageFilter);
    }

    const needle = q.trim().toLowerCase();
    if (needle) {
      list = list.filter((r) =>
        `${rowCompany(r)} ${rowTitle(r)}`.toLowerCase().includes(needle),
      );
    }

    const dir = sortDir === "asc" ? 1 : -1;
    const pick = (r: Row): string | number => {
      switch (sortKey) {
        case "role":
          return rowTitle(r).toLowerCase();
        case "status":
          // In the Status filter's order: saved, then each application status, then the agent lanes.
          return FILTERS.indexOf(rowFilterKey(r));
        case "applied_at":
          return r.kind === "saved" ? "" : (r.app.applied_at ?? "");
        case "created_at":
        default:
          return r.kind === "saved" ? r.job.created_at : r.app.created_at;
      }
    };
    return [...list].sort((a, b) => {
      if (sortKey === "ats") {
        // Unscored rows sit last whichever way it sorts: no score is not a low score.
        const as = rowScore(a);
        const bs = rowScore(b);
        if (as === bs) return 0;
        if (as === null) return 1;
        if (bs === null) return -1;
        return (as - bs) * dir;
      }
      const av = pick(a);
      const bv = pick(b);
      if (av === bv) return 0;
      return av < bv ? -dir : dir;
    });
  }, [sourceScopedRows, filter, stageFilter, q, sortKey, sortDir]);

  // Each chip and stage option counts the rows pressing it shows (source-scoped, before the search; nothing
  // while the other source loads).
  const countRows = sourceScopedRows.map((r) => ({ filterKey: rowFilterKey(r), stage: rowStage(r) }));
  const axes = { filter, stage: stageFilter };
  const view = viewOf(axes);
  const chips = TRACKER_VIEWS.map((v) => ({
    v,
    on: view === v,
    count: stale ? "…" : chipCount(countRows, VIEW_FILTERS[v], {}),
  }));
  // A stage option shows while it has rows, or while it is on, so it can never vanish under the user.
  const stageOptions = STAGE_FILTERS.map((s) => ({ s, count: chipCount(countRows, axes, { stage: s }) })).filter(
    ({ s, count }) => count > 0 || s === stageFilter,
  );
  // What Filters holds that no chip says: a Status value or a stage no chip names, and the source. A link or
  // an earlier visit can set them, so the button counts them.
  const filtersOn = (view ? 0 : (filter !== "all" ? 1 : 0) + (stageFilter ? 1 : 0)) + (source !== "all" ? 1 : 0);

  // Select mode acts on the rows shown, never one a filter or the search hides (as the Agent inbox does).
  const rowsShown = useMemo(() => filtered.map((r) => ({ id: rowKey(r), r, actions: bulkActionsOf(r) })), [filtered]);
  const selectedShown = useMemo(() => selectedAmong(rowsShown, selected), [rowsShown, selected]);
  const picked = rowsShown.filter((row) => selected.has(row.id));
  const can = bulkCan(picked.map((row) => row.actions));
  const pickableIds = rowsShown.filter((row) => row.actions.length > 0).map((row) => row.id);
  const allPicked = pickableIds.length > 0 && pickableIds.every((id) => selected.has(id));
  const toggleSelected = (id: string, on: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  const endSelect = () => {
    barLeft.current = true;
    setSelectMode(false);
    setSelected(new Set());
  };
  const bulk = useJobBulkActions({ onDone: endSelect, returnFocus: () => selectButton.current });

  const loading = apps.isLoading || savedJobs.isLoading || (stale && filtered.length === 0);
  // Checked BEFORE the empty state, which is the whole bug: with `data`
  // undefined after a failure, `filtered.length === 0` is true and the branch
  // below hands a user with a full pipeline the brand-new-user onboarding card.
  const loadFailed = isLoadFailure(apps) || isLoadFailure(savedJobs);
  // What was LOADED hit the cap, whatever the filter or search shows: the
  // notice is about the fetch, so it stays true under all of them.
  const caps = [
    { loaded: apps.data?.length ?? 0, limit: LIST_LIMIT, noun: "applications" },
    {
      loaded: savedJobs.data?.length ?? 0,
      limit: LIST_LIMIT,
      noun: savedSource === "agent" ? "jobs from connected agents" : "saved jobs",
    },
  ].filter(isListCapped);

  // Record the visible row order (job ids) so the job page's prev/next arrows
  // can walk exactly what the user was looking at, filters and sort included.
  useEffect(() => {
    if (loading || stale) return;
    storeValue(
      SEQUENCE_STORE_KEY,
      JSON.stringify(
        filtered.map((r) => (r.kind === "saved" ? r.job.id : r.app.job_id)),
      ),
    );
  }, [filtered, loading, stale]);

  // In the commit that drops the row, before paint (a passive effect left
  // focus on <body> for a frame): the next row's status chip, else the
  // previous row's, else the main area (the table goes with its last row).
  useLayoutEffect(() => {
    const l = leaving.current;
    if (!l || filtered.some((r) => rowKey(r) === l.key)) return;
    leaving.current = null;
    focusIfDropped(l.next());
  }, [filtered]);

  // The same commit for Queue in Agent inbox: once the queued job's row stops offering it.
  useLayoutEffect(() => {
    const q = queued.current;
    if (!q) return;
    if (filtered.some((r) => r.kind === "saved" && r.job.id === q.jobId && !r.job.proposal_status))
      return;
    queued.current = null;
    focusIfDropped(q.next());
  }, [filtered]);

  // The bar's commit: its action or Done took it away, so focus goes back to Select.
  useLayoutEffect(() => {
    if (selectMode || !barLeft.current) return;
    barLeft.current = false;
    focusIfDropped(selectButton.current);
  }, [selectMode]);

  // A column the sort menu orders by says so to a screen reader.
  const sortedAs = (key: SortKey) =>
    sortKey === key ? (sortDir === "asc" ? "ascending" : "descending") : undefined;

  return (
    <PageShell>
      <PageHeader
        title="Jobs"
        // How many jobs the source toggle holds, every status included; the chips split them.
        meta={
          loading || loadFailed ? null : (
            <span className="text-muted-foreground text-body-large tabular-nums">
              {countOf("all")}
              <span className="sr-only"> jobs</span>
            </span>
          )
        }
        actions={
          <>
            <ListSearch label="Search jobs" value={q} onChange={setQ} />
            {/* The sidebar's FAB is THE Add job while it is showing (M3:
                a FAB's action is not repeated on its screen). The sidebar slides
                off-canvas when collapsed and below 768px; then this is the only
                way to start one, so it renders exactly when the FAB cannot be seen. */}
            {sidebarHidden ? (
              <Button
                nativeButton={false}
                render={
                  <Link href="/new">
                    <FilePlus2 className="size-4" />
                    Add job
                  </Link>
                }
              />
            ) : null}
          </>
        }
      />

      <ListToolbar>
        <div className="flex flex-wrap items-center gap-2">
          {/* One chip on at a time: each is a preset of the Status filter and the stage. Pressing the one
              that is on shows everything. */}
          <div role="group" aria-label="Show" className="flex flex-wrap items-center gap-2">
            {chips.map(({ v, on, count }) => (
              <button
                key={v}
                type="button"
                aria-pressed={on}
                aria-label={`${VIEW_LABELS[v]} ${count}`}
                className={filterChipClass(on)}
                onClick={() => update(on ? { filter: "all", stage: null } : VIEW_FILTERS[v])}
              >
                {on ? <Check className="size-3" aria-hidden="true" /> : null}
                {VIEW_LABELS[v]}
                <span className="tabular-nums">{count}</span>
              </button>
            ))}
          </div>
          <div className="ml-auto flex items-center gap-1">
            <Select value={sort} onValueChange={(v) => setSort((v as SortName) ?? "added")}>
              <SelectTrigger className="h-8 min-w-[10rem]" aria-label="Sort">
                <SelectValue>{SORTS[sort].label}</SelectValue>
              </SelectTrigger>
              <SelectContent align="end" alignItemWithTrigger={false} className="w-auto min-w-[12rem]">
                {(Object.keys(SORTS) as SortName[]).map((name) => (
                  <SelectItem key={name} value={name}>
                    {SORTS[name].label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FiltersButton
              open={filtersOpen}
              onToggle={() => setFiltersOpen((o) => !o)}
              controls={filtersId}
              active={filtersOn}
            />
            {filtered.length > 0 || selectMode ? (
              <SelectToggle
                ref={selectButton}
                selecting={selectMode}
                onClick={() => (selectMode ? endSelect() : setSelectMode(true))}
              />
            ) : null}
          </div>
        </div>
        {/* Every filter the list had keeps its home here: the Status filter (each application status and
            Agent inbox lane), the stage and the source. */}
        <div id={filtersId} hidden={!filtersOpen} className="flex flex-wrap items-center gap-1.5">
          <Select
            value={filter}
            onValueChange={(v) => {
              if (v && (FILTERS as readonly string[]).includes(v)) {
                update({ filter: v as Filter });
              }
            }}
          >
            <SelectTrigger
              className="h-8 min-w-[11rem]"
              aria-label="Filter by status"
            >
              {/* "Status:" on screen: the toolbar has no captions, and "All · 21" alone named nothing. */}
              <SelectValue>
                <FilterDot value={filter} />
                {`Status: ${filterLabel(filter)} · ${countOf(filter)}`}
              </SelectValue>
            </SelectTrigger>
            <SelectContent
              align="start"
              alignItemWithTrigger={false}
              className="w-auto min-w-[14rem]"
            >
              <SelectGroup aria-label="Overview">
                {topOptions.map(filterOption)}
              </SelectGroup>
              {appOptions.length > 0 ? (
                <SelectGroup>
                  <SelectLabel>Your applications</SelectLabel>
                  {appOptions.map(filterOption)}
                </SelectGroup>
              ) : null}
              {laneOptions.length > 0 ? (
                <SelectGroup>
                  <SelectLabel>Agent inbox</SelectLabel>
                  {laneOptions.map(filterOption)}
                </SelectGroup>
              ) : null}
            </SelectContent>
          </Select>
          <Select
            value={stageFilter ?? "any"}
            onValueChange={(v) => update({ stage: v && v !== "any" ? (v as StageFilter) : null })}
          >
            <SelectTrigger className="h-8 min-w-[10rem]" aria-label="Filter by stage">
              <SelectValue>{stageFilter ? STAGE_LABELS[stageFilter] : "Any stage"}</SelectValue>
            </SelectTrigger>
            <SelectContent align="start" alignItemWithTrigger={false} className="w-auto min-w-[12rem]">
              <SelectItem value="any">Any stage</SelectItem>
              {stageOptions.map(({ s, count }) => (
                <SelectItem key={s} value={s}>
                  {`${STAGE_LABELS[s]} · ${stale ? "…" : count}`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <SourceToggle
            className="ml-auto"
            // Your saved jobs and every application, agent ones included:
            // not "All", since agent finds nobody proposed or applied to are
            // only under Agents.
            allLabel="Tracked"
            label="Filter jobs by source"
            value={source}
            onChange={(next) => update({ source: next })}
            // Hover or focus on Agents starts its fetch, so the first switch
            // shows rows instead of a skeleton. A fresh cache entry is kept.
            onPreview={(next) => {
              if (next === "agent") void qc.prefetchQuery(savedJobsQuery("agent"));
            }}
          />
        </div>
      </ListToolbar>

      {loadFailed ? (
        <LoadErrorState
          title="Couldn't load your jobs."
          detail={loadErrorDetail(apps.error ?? savedJobs.error)}
          retrying={apps.isFetching || savedJobs.isFetching}
          onRetry={() => {
            void apps.refetch();
            void savedJobs.refetch();
          }}
        />
      ) : loading ? (
        <div className="space-y-2">
          <Skeleton className="animate-shimmer h-12 w-full" />
          <Skeleton className="animate-shimmer h-12 w-full" />
          <Skeleton className="animate-shimmer h-12 w-full" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="space-y-5">
          {/* The task leads and the setup checklist supports it: a new user
              reads what this page is for before a list of setup homework. */}
          <EmptyState
            icon={Inbox}
            title={
              allRows.length === 0
                ? "No jobs yet"
                : "Nothing matches this filter"
            }
            description={
              allRows.length === 0
                ? needsKey
                  ? "Add an API key first, then add a job."
                  : "Add a job to get started."
                : "Try another chip or filter, or clear the search."
            }
            action={
              allRows.length === 0 ? (
                // Lowest emphasis (M3 text button): the FAB or the header
                // button is the primary create action, but an empty state
                // still offers its pathway as a control, not just a sentence.
                // With no key, that pathway starts at the key.
                <Button
                  variant="ghost"
                  nativeButton={false}
                  render={
                    needsKey ? (
                      <Link href={anchorHref("/settings", "api-keys")}>
                        <KeyRound className="size-4" />
                        Add API key
                      </Link>
                    ) : (
                      <Link href="/new">
                        <FilePlus2 className="size-4" />
                        Add job
                      </Link>
                    )
                  }
                />
              ) : null
            }
          />
          {allRows.length === 0 ? <GettingStartedCard /> : null}
        </div>
      ) : (
        <TableFrame className={cn(selectMode && "mb-16")}>
          {/* minWidth engages Table's own overflow-x-auto container. Without
              it the table shrinks to whatever width is left (462px at 768px,
              where the sidebar has not yet collapsed), and because the layout
              is fixed the status chip cannot widen its column, so it paints
              over its date instead. It is also the width the header
              sticks from: a table wider than its frame scrolls sideways, and
              then its header cannot stick to the window. */}
          <Table minWidth="57rem" stickyHeader className="table-fixed" aria-busy={stale || undefined}>
            <TableHeader>
              <TableRow className="hover:bg-transparent dark:hover:bg-transparent">
                {selectMode ? (
                  <TableHead className="w-10 pr-0">
                    <Checkbox
                      aria-label="Select all shown"
                      checked={allPicked}
                      disabled={pickableIds.length === 0}
                      onCheckedChange={(on) =>
                        setSelected((prev) => {
                          const next = new Set(prev);
                          for (const id of pickableIds) {
                            if (on) next.add(id);
                            else next.delete(id);
                          }
                          return next;
                        })
                      }
                    />
                  </TableHead>
                ) : null}
                <TableHead className="w-full" aria-sort={sortedAs("role")}>Role</TableHead>
                <TableHead className="w-[6.75rem] px-3" aria-sort={sortedAs("ats")}>Match</TableHead>
                <TableHead className="w-[12.5rem] px-3" aria-sort={sortedAs("status")}>Status</TableHead>
                <TableHead className="w-[12rem] px-3">Next step</TableHead>
                <TableHead className="w-10 px-1" />
              </TableRow>
            </TableHeader>
            <TableBody className={cn("transition-opacity", stale && "opacity-60")}>
              {filtered.map((r) => {
                const key = rowKey(r);
                const jobId = r.kind === "saved" ? r.job.id : r.app.job_id;
                const owner = r.kind === "saved" ? r.job.ownership : r.app.ownership;
                const ownership = jobOwnershipView(owner);
                const href =
                  r.kind === "saved"
                    ? `/jobs/${r.job.id}`
                    : `/jobs/${r.app.job_id}`;
                const company = rowCompany(r) || "—";
                const title = rowTitle(r) || "Untitled role";
                const place = jobMetaLine([rowCompany(r), r.kind === "saved" ? r.job.location : r.app.job_location]);
                const resumeName = r.kind === "application" ? r.app.base_resume_name || baseName(r.app.base_resume) : "";
                const stage = rowStage(r);
                const step = nextStep(stage, r.kind === "saved" ? r.job : r.app);
                // Applied and closed rows have no next step: only a plain applied one says it is waiting.
                const waiting = stage === "applied" && r.kind === "application" && r.app.status === "applied";
                // A saved job an agent captured names its filer; an application is "agent" only
                // because a proposal was linked to it, whoever made it.
                const mark =
                  r.kind === "saved"
                    ? agentMarkLabel(r.job.proposal_proposed_by)
                    : LINKED_APPLICATION_MARK;
                const pickable = bulkActionsOf(r).length > 0;
                const isPicked = selected.has(key);
                // Beside the chip: when the status began (the status log), or when you applied.
                const dated = r.kind === "application" ? statusDate(r.app) : null;

                return (
                  <TableRow
                    key={key}
                    data-row={key}
                    className="group/row cursor-pointer"
                    aria-selected={selectMode ? isPicked : undefined}
                    // The row was click-only: no tabIndex, no key handler, no
                    // role. A keyboard user could reach the status chip and the
                    // overflow menu inside the row but had no way to open the
                    // job it points at. Proposals solves the identical case
                    // with a real <Link>; a table row cannot contain one
                    // without breaking the row semantics, so it takes the
                    // link role and the two keys that role implies. In Select
                    // mode a click picks the row instead, and keyboards use its
                    // checkbox, as in the Agent inbox.
                    role={selectMode ? undefined : "link"}
                    tabIndex={selectMode ? undefined : 0}
                    onClick={() => {
                      if (!selectMode) router.push(href);
                      else if (pickable) toggleSelected(key, !isPicked);
                    }}
                    onKeyDown={(e) => {
                      if (selectMode || e.target !== e.currentTarget) return;
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        // Keyboard actions never animate: the row drops its names before it opens the job.
                        flushSync(() => setUnmorphed(jobId));
                        router.push(href);
                      }
                    }}
                  >
                    {selectMode ? (
                      <TableCell className="w-10 pr-0" onClick={(e) => e.stopPropagation()}>
                        <Checkbox
                          disabled={!pickable}
                          checked={isPicked}
                          onCheckedChange={(on) => toggleSelected(key, on)}
                          aria-label={`Select ${title}${rowCompany(r) ? ` at ${rowCompany(r)}` : ""}`}
                        />
                      </TableCell>
                    ) : null}
                    <TableCell className="max-w-0 whitespace-normal py-2.5">
                      <div className="flex min-w-0 items-center gap-3">
                        {/* The monogram and title morph into the job page's (components/job-morph.tsx). */}
                        <JobMorph jobId={jobId} part="monogram" off={unmorphed === jobId}>
                          <CompanyMonogram name={company} className="shrink-0" />
                        </JobMorph>
                        <div className="min-w-0 flex-1 overflow-hidden">
                          <p className="flex min-w-0 items-center gap-1.5 text-title-small">
                            <JobMorph jobId={jobId} part="title" off={unmorphed === jobId}>
                              <span className="truncate">{title}</span>
                            </JobMorph>
                            {(r.kind === "saved" ? r.job.source : r.app.source) ===
                            "agent" ? (
                              // An SVG with only aria-label is announced
                              // unevenly; the sr-only words join the row
                              // link's name everywhere.
                              <span className="inline-flex shrink-0" title={mark}>
                                <Bot className="text-muted-foreground size-3.5" aria-hidden="true" />
                                <span className="sr-only">{mark}</span>
                              </span>
                            ) : null}
                          </p>
                          <p className="text-muted-foreground truncate text-body-small">
                            {place || company}
                          </p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="px-3">
                      {(() => {
                        const score = rowScore(r);
                        return score === null ? (
                          <span className="text-muted-foreground text-body-small">
                            <span aria-hidden="true">—</span>
                            <span className="sr-only">No score yet</span>
                          </span>
                        ) : (
                          // The meter's name and the hover name the resume behind the score; a saved job's best
                          // base is not named by the API.
                          <span className="inline-flex" title={resumeName || undefined}>
                            <ScoreBar
                              value={score}
                              label={
                                r.kind === "saved"
                                  ? "Best match score"
                                  : resumeName
                                    ? `Match score, ${resumeName}`
                                    : "Match score"
                              }
                              valueText={score.toFixed(1)}
                              width="w-10"
                            />
                          </span>
                        );
                      })()}
                    </TableCell>
                    <TableCell className="px-3">
                      <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                        {r.kind === "saved" ? (
                          <SavedJobChip proposalStatus={r.job.proposal_status} />
                        ) : (
                          <StatusChip
                            status={r.app.status}
                            lockedReason={ownership.canRequest ? undefined : (ownership.reason ?? undefined)}
                            pending={
                              patchStatus.isPending &&
                              patchStatus.variables?.id === r.app.id
                            }
                            onSelect={(status) => {
                              if (filter !== "all" && !matchesFilter(filter, status))
                                leaving.current = {
                                  key,
                                  next: focusSuccessor(
                                    document.querySelector(`[data-row="${key}"]`),
                                    "[data-status-chip]",
                                  ),
                                };
                              patchStatus.mutate({ id: r.app.id, status });
                            }}
                          />
                        )}
                        {dated ? (
                          <span className="text-muted-foreground text-body-small tabular-nums" title={`${dated.word} ${formatShortDate(dated.at)}`}>
                            <span className="sr-only">{dated.word} </span>
                            {formatShortDate(dated.at)}
                          </span>
                        ) : null}
                      </span>
                    </TableCell>
                    <TableCell className="px-3">
                      {step ? (
                        // It only navigates, so it is never disabled: the page it opens says whose the job is.
                        // Its click stays its own; the rest of the cell opens the job like the row.
                        // A link opened from the keyboard (a click with no pointer) drops the row's names first too.
                        <span
                          className="inline-flex"
                          onClick={(e) => e.stopPropagation()}
                          onClickCapture={(e) => {
                            if (e.detail === 0) flushSync(() => setUnmorphed(jobId));
                          }}
                        >
                          <NextStep label={step.label} href={nextStepHref(jobId, step)} />
                        </span>
                      ) : waiting ? (
                        <NextStep waiting="Waiting to hear back" />
                      ) : null}
                    </TableCell>
                    {/* Where the job is, only when it is not on this copy or a request waits; else the row's ⋯,
                        whose actions a job on the other copy could not take anyway. */}
                    <TableCell className="px-1" onClick={(e) => e.stopPropagation()}>
                      {ownershipSays(owner) ? (
                        <JobOwnershipPopover jobId={jobId} ownership={owner} />
                      ) : selectMode ? null : (
                        <DropdownMenu>
                          <DropdownMenuTrigger
                            render={
                              <Button
                                variant="ghost"
                                size="icon-sm"
                                aria-label="More actions"
                                className="opacity-0 transition-opacity duration-150 group-hover/row:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-100 aria-expanded:opacity-100"
                              >
                                <MoreIcon className="size-4" />
                              </Button>
                            }
                          />
                          <DropdownMenuContent align="end" className="w-max">
                            {r.kind === "saved" && !r.job.proposal_status ? (
                              <DropdownMenuItem
                                disabled={promoteJob.isPending || !ownership.canWrite}
                                onClick={() => {
                                  queued.current = { jobId: r.job.id, next: focusReturnPoint(moreActions(key)) };
                                  promoteJobOnce(r.job.id);
                                }}
                              >
                                <SendHorizontal className="size-4" />
                                Queue in Agent inbox
                              </DropdownMenuItem>
                            ) : null}
                            {r.kind === "saved" ? (
                              <DropdownMenuItem
                                variant="destructive"
                                disabled={!ownership.canWrite}
                                onClick={async () => {
                                  const ok = await confirm({
                                    title: "Delete this job?",
                                    description: `${company} · ${title}. This deletes the job and everything saved with it.`,
                                    confirmLabel: "Delete",
                                    destructive: true,
                                  });
                                  if (ok) deleteJob.mutate(r.job.id);
                                }}
                              >
                                <Trash2 className="size-4" />
                                Delete job
                              </DropdownMenuItem>
                            ) : (
                              <DropdownMenuItem
                                variant="destructive"
                                disabled={!ownership.canWrite}
                                onClick={async () => {
                                  const ok = await confirm({
                                    title: "Delete this application?",
                                    description: `${company} · ${title}. This deletes its tailored resume, answers and PDF. The job stays saved.`,
                                    confirmLabel: "Delete",
                                    destructive: true,
                                  });
                                  if (ok) deleteApp.mutate(r.app.id);
                                }}
                              >
                                <Trash2 className="size-4" />
                                Delete application
                              </DropdownMenuItem>
                            )}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableFrame>
      )}

      {!loading && !loadFailed && !stale && caps.length > 0 ? (
        <div className="flex flex-col gap-1">
          {caps.map((cap) => (
            <ListCapNotice key={cap.noun} {...cap} />
          ))}
        </div>
      ) : null}

      {selectMode ? (
        <JobsBulkBar
          selectedCount={selectedShown.length}
          can={can}
          running={bulk.running}
          onStatus={(status) =>
            bulk.setStatus({ ids: picked.flatMap(({ r }) => (r.kind === "application" ? [r.app.id] : [])), status })
          }
          onQueue={() => bulk.queue(picked.map(({ r }) => (r.kind === "saved" ? r.job.id : r.app.job_id)))}
          onDelete={() =>
            bulk.remove({
              ids: picked.map(({ r }) => (r.kind === "saved" ? r.job.id : r.app.id)),
              kind: can.delete === "deleteJob" ? "saved" : "application",
            })
          }
          onDone={endSelect}
        />
      ) : null}
    </PageShell>
  );
}

// useSearchParams() requires a Suspense boundary for the static prerender in
// `next build` (Next.js 16 CSR bailout).
export default function ApplicationsPage() {
  return (
    <Suspense fallback={null}>
      <ApplicationsContent />
    </Suspense>
  );
}

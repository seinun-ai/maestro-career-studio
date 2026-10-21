"use client";

import { createContext, useContext, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { useQuery } from "@tanstack/react-query";
import { GuardedLink as Link } from "@/components/guarded-link";
import {
  TriangleAlert,
  BookOpen,
  Bot,
  ChevronDown,
  Loader2,
  Settings as SettingsIcon,
  Trash2,
  X,
} from "lucide-react";

import { CompanyMonogram } from "@/components/company-monogram";
import { JobOwnershipPopover } from "@/components/job-ownership";
import { jobOwnershipView, ownershipControlProps } from "@/lib/job-ownership";
import { EmptyState } from "@/components/empty-state";
import { ListCapNotice } from "@/components/list-cap-notice";
import { ListSearch } from "@/components/list-search";
import { FilterChips } from "@/components/filter-chips";
import { FiltersButton } from "@/components/filters-button";
import { ListToolbar } from "@/components/list-toolbar";
import { SelectToggle } from "@/components/selection-bar";
import { useRoleLabel } from "@/components/role-category-picker";
import {
  BulkBar,
  type BulkActions,
  DeclineDialog,
  useProposalActions,
} from "@/components/proposals/triage-actions";
import { ROW_EXIT_MS } from "@/lib/motion";
import { ReadinessMarks } from "@/components/proposals/readiness-marks";
import { IconButton } from "@/components/icon-button";
import { humanizeEnum } from "@/components/job-extracted-fields";
import { PROPOSAL_STATUS_CHIP } from "@/components/status-chip";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Fold } from "@/components/ui/fold";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LoadErrorState } from "@/components/load-error-state";
import { useBaseResumeColor, useBaseResumeName } from "@/hooks/use-base-resume-label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AGENT_APPLICATIONS_URL,
  CONNECTED_AGENTS_SETTINGS,
  JOB_HUNT_SKILL_URL,
} from "@/lib/agent-links";
import { ActorChip, ResumeTag, ScoreBar } from "@/components/visual";
import { agentDisplayName, proposalByLine } from "@/lib/agent-name";
import { apiFetch } from "@/lib/api";
import { loadErrorDetail } from "@/lib/error-text";
import { formatTimeAgo } from "@/lib/format-date";
import {
  SCORE_FLOORS,
  type ScoreFloor,
  boardHost,
  chosenScore,
  filterProposals,
  filtersShown,
} from "@/lib/inbox-filter";
import { finalFocusOn, focusIfDropped, focusSuccessor } from "@/lib/focus";
import {
  INBOX_LANES,
  type InboxLane,
  STATUS_ORDER,
  inLane,
  laneOf,
  needsYouHelp,
  needsYouLine,
  selectedAmong,
} from "@/lib/inbox-lanes";
import { historyLabel, historyStatusOf, isNew, readyFirst } from "@/lib/inbox-readiness";
import { jobMetaLine } from "@/lib/job-meta";
import { isLoadFailure } from "@/lib/query-state";
import { cn } from "@/lib/utils";
import {
  type Proposal,
  type ProposalListResponse,
  type ProposalStatus,
} from "@/lib/types";
import { CONCEPT_ICONS } from "@/lib/concept-icons";

const QueueIcon = CONCEPT_ICONS.queue;
const ApproveIcon = CONCEPT_ICONS.approve;

const PROPOSALS_KEY = ["proposals"] as const;
// The dashboard can open History before a tile scrolls; standalone inboxes keep local state.
export const InboxHistoryContext = createContext<readonly [boolean, Dispatch<SetStateAction<boolean>>] | null>(null);
// The API's max page (routers/proposals.py: le=500); `total` counts them all.
const PROPOSALS_LIMIT = 500;
const SEQUENCE_STORE_KEY = "cs-proposals-seq";

function storeProposalSequence(jobIds: string[]) {
  try {
    sessionStorage.setItem(SEQUENCE_STORE_KEY, JSON.stringify(jobIds));
  } catch {
    // Session memory is a convenience — never let storage failures break the page.
  }
}

// Both derived from the ONE vocabulary in status-chip.tsx. They stay exported
// under these names because they are the established import surface (the job
// page uses them), but they are no longer a second source of truth.
export const STATUS_LABELS = Object.fromEntries(
  STATUS_ORDER.map((k) => [k, PROPOSAL_STATUS_CHIP[k].label]),
) as Record<ProposalStatus, string>;

export const STATUS_BADGE_CLASS = Object.fromEntries(
  STATUS_ORDER.map((k) => [k, PROPOSAL_STATUS_CHIP[k].className]),
) as Record<ProposalStatus, string>;

/** A row's actions: the same one on the next row takes focus when a row leaves its lane. */
type RowAction = "queue" | "keep" | "skip" | "delete";

type LaneKind = "needs_you" | "triage" | "queued" | "in_flight" | "history";

// Delete is on Needs you (bogus or dead postings parked there never earn a skip record; the backend
// refuses deletes only for submitted and uncertain) and on a History row that was skipped or expired.
function canDeleteIn(proposal: Proposal, lane: LaneKind): boolean {
  return lane === "needs_you" ||
    (lane === "history" && (proposal.status === "rejected" || proposal.status === "expired"));
}

/** What a picked row lets the bulk bar do: the actions its own buttons offer, under the same locks. */
function bulkActionsOf(proposal: Proposal, lane: LaneKind): (keyof BulkActions)[] {
  const view = jobOwnershipView(proposal.job.ownership);
  const out: (keyof BulkActions)[] = [];
  if (lane === "triage" && view.canRequest) out.push("queue");
  if ((lane === "triage" || lane === "queued" || lane === "needs_you") && view.canRequest) out.push("skip");
  if (canDeleteIn(proposal, lane) && view.canWrite) out.push("delete");
  return out;
}

const selectableIds = (rows: Proposal[], lane: LaneKind) =>
  rows.filter((p) => bulkActionsOf(p, lane).length > 0).map((p) => p.id);

/**
 * Where focus goes when the control holding it leaves: one row leaving its lane, or the bulk bar leaving.
 * Read at the click, while the row is there (lib/focus.ts `focusSuccessor`).
 */
type Leaving =
  | { kind: "row"; id: string; lane: InboxLane | null; next: () => HTMLElement | null }
  | { kind: "bar"; next: () => HTMLElement | null };

type SortKey = "score" | "newest" | "title" | "company";

// Values that describe themselves: the toolbar has no captions. "Job title",
// not "Role": the Role filter is the role category, this is the posting's title.
const SORT_LABELS: Record<SortKey, string> = {
  score: "Best score first",
  newest: "Newest first",
  title: "Job title A–Z",
  company: "Company A–Z",
};

const scoreLabel = (floor: ScoreFloor | null) =>
  floor == null ? "Any score" : `Score ${floor}+`;

function normalizeTitle(title: string): string {
  return title.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function duplicateKey(p: Proposal): string {
  return `${(p.job.company ?? "").toLowerCase()}|${normalizeTitle(p.job.title ?? "")}`;
}

function chosenBase(p: Proposal): string | null {
  const fit = (p.fit_json ?? {}) as Record<string, unknown>;
  return typeof fit.chosen_base === "string" ? fit.chosen_base : null;
}

function formatDayLabel(isoDay: string): string {
  const d = new Date(`${isoDay}T00:00:00Z`);
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

function sortProposals(items: Proposal[], sort: SortKey): Proposal[] {
  const list = [...items];
  list.sort((a, b) => {
    switch (sort) {
      case "newest":
        return b.created_at.localeCompare(a.created_at);
      case "title":
        return (a.job.title ?? "").localeCompare(b.job.title ?? "");
      case "company":
        return (a.job.company ?? "").localeCompare(b.job.company ?? "");
      case "score":
      default: {
        const as = chosenScore(a);
        const bs = chosenScore(b);
        if (as == null && bs == null) return b.created_at.localeCompare(a.created_at);
        if (as == null) return 1;
        if (bs == null) return -1;
        return bs - as;
      }
    }
  });
  return list;
}

export function ProposalsSection({ since = null }: { since?: string | null } = {}) {
  const { data, isLoading, isError, error, isFetching, fetchStatus, refetch, errorUpdateCount } = useQuery({
    queryKey: PROPOSALS_KEY,
    queryFn: () =>
      apiFetch<ProposalListResponse>(`/api/proposals?limit=${PROPOSALS_LIMIT}`),
  });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  // Select mode (Photos' Select): checkboxes on the rows, the bulk bar at the bottom, a row's click picks it.
  const [selecting, setSelecting] = useState(false);
  const selectButton = useRef<HTMLButtonElement>(null);
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortKey>("score");
  const [role, setRole] = useState("all");
  const [board, setBoard] = useState("all");
  const [minScore, setMinScore] = useState<ScoreFloor | null>(null);
  // Role, Job board and Minimum score sit behind Filters; the sort stays in view.
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filtersId = useId();
  const roleLabel = useRoleLabel();
  const localHistory = useState(false);
  const [historyOpen, setHistoryOpen] = useContext(InboxHistoryContext) ?? localHistory;
  // The History statuses that are on; none on shows them all (FilterChips has no "All").
  const [historyStatus, setHistoryStatus] = useState<ReadonlySet<ProposalStatus>>(new Set());
  const [expandedDays, setExpandedDays] = useState<Set<string> | null>(null);
  const [declineTarget, setDeclineTarget] = useState<
    { mode: "single"; id: string } | { mode: "bulk" } | null
  >(null);

  // Focus never falls to <body> when a Queue, Skip, Delete or Clear takes its control away.
  const leaving = useRef<Leaving | null>(null);
  // Set when a Skip from the dialog succeeds: the dialog's close hands focus on (its opener goes).
  const skipReturn = useRef<(() => HTMLElement | null) | null>(null);
  const toReview = useRef<HTMLElement>(null);
  // Rows that were queued or skipped and are collapsing out, with the status they leave: the refetch
  // moves a queued row to another lane (a new row there, not leaving), so an id only leaves as that status.
  const [leavingIds, setLeavingIds] = useState<ReadonlyMap<string, ProposalStatus>>(new Map());
  const actions = useProposalActions({
    settleMs: ROW_EXIT_MS,
    onQueued: () => setDeclineTarget(null),
    onDone: (ids, became) => {
      if (became === "accepted" || became === "rejected") {
        const before = new Map((data?.items ?? []).map((p) => [p.id, p.status] as const));
        setLeavingIds((prev) => {
          const next = new Map(prev);
          for (const id of ids) {
            const status = before.get(id);
            if (status) next.set(id, status);
          }
          return next;
        });
      }
      // A row queued, skipped or deleted on its own leaves the selection; so do the bar's rows.
      setSelected((prev) => {
        const copy = new Set(prev);
        for (const id of ids) copy.delete(id);
        return copy;
      });
      // The bar's action is done: select mode ends with it, as Photos' does after a delete.
      if (leaving.current?.kind === "bar") setSelecting(false);
      if (declineTarget) skipReturn.current = leaving.current?.next ?? null;
      setDeclineTarget(null);
    },
    onUndone: () => {
      leaving.current = null;
    },
  });

  const items = useMemo(() => data?.items ?? [], [data]);

  // Clear an id once the refetched list no longer holds it as it was: gone, or in another status. A stale
  // entry would hide a row that comes back in that status (Queue, then Keep it returns it to To review).
  // Adjusted while rendering, keyed on the list itself (React: "adjusting state when a prop changes").
  const [prunedFor, setPrunedFor] = useState(items);
  if (prunedFor !== items) {
    setPrunedFor(items);
    if (leavingIds.size > 0) {
      const now = new Map(items.map((p) => [p.id, p.status] as const));
      const rest = [...leavingIds].filter(([id, status]) => now.get(id) === status);
      if (rest.length !== leavingIds.size) setLeavingIds(new Map(rest));
    }
  }

  const roles = useMemo(() => {
    const set = new Set<string>();
    for (const p of items) {
      if (p.job.role_category) set.add(p.job.role_category);
    }
    return [...set].sort((a, b) => roleLabel(a).localeCompare(roleLabel(b)));
  }, [items, roleLabel]);

  const boards = useMemo(() => {
    const set = new Set<string>();
    for (const p of items) {
      const host = boardHost(p.job.source_url);
      if (host) set.add(host);
    }
    return [...set].sort();
  }, [items]);

  const filtered = useMemo(
    () => filterProposals(items, { q, role, board, minScore }),
    [items, q, role, board, minScore],
  );
  // Read only after the no-proposals return below: filters hid everything.
  const nothingMatches = filtered.length === 0;

  const duplicateKeys = useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of filtered) {
      const key = duplicateKey(p);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return new Set(
      [...counts.entries()].filter(([, n]) => n > 1).map(([k]) => k),
    );
  }, [filtered]);

  const needsYou = useMemo(
    () => sortProposals(inLane(filtered, "needs_you"), sort),
    [filtered, sort],
  );
  const triage = useMemo(
    () => sortProposals(inLane(filtered, "triage"), sort),
    [filtered, sort],
  );
  const queued = useMemo(
    () => readyFirst(sortProposals(inLane(filtered, "queued"), sort)),
    [filtered, sort],
  );
  const inFlight = useMemo(
    () => sortProposals(inLane(filtered, "in_flight"), sort),
    [filtered, sort],
  );
  const historyAll = useMemo(() => inLane(filtered, "history"), [filtered]);
  const history = useMemo(() => {
    const scoped =
      historyStatus.size === 0
        ? historyAll
        : historyAll.filter((p) => historyStatus.has(historyStatusOf(p.status, p.reason)));
    return sortProposals(scoped, sort);
  }, [historyAll, historyStatus, sort]);

  // The rows a selection can hold, with their lane: Applying rows have no action to share.
  const pickable = useMemo(() => [
    ...needsYou.map((p) => ({ p, lane: "needs_you" as const })),
    ...triage.map((p) => ({ p, lane: "triage" as const })),
    ...queued.map((p) => ({ p, lane: "queued" as const })),
    ...(historyOpen ? history : []).map((p) => ({ p, lane: "history" as const })),
  ], [needsYou, triage, queued, history, historyOpen]);
  // Bulk actions and the bar's count see only the rows shown: never a row a filter or the search hides.
  const selectedShown = useMemo(() => selectedAmong(pickable.map((r) => r.p), selected), [pickable, selected]);
  // An action is offered when every picked row allows it (a locked job's row allows none of its writes).
  const bulkCan = useMemo<BulkActions>(() => {
    const picked = pickable.filter((r) => selected.has(r.p.id)).map((r) => bulkActionsOf(r.p, r.lane));
    const all = (action: keyof BulkActions) => picked.length > 0 && picked.every((a) => a.includes(action));
    return { queue: all("queue"), skip: all("skip"), delete: all("delete") };
  }, [pickable, selected]);
  const barShown = selecting;

  // In the commit that takes the row out of its lane, or the bar away, before paint. A dialog still
  // closing keeps focus until its own finalFocus runs; focusIfDropped leaves that alone.
  useLayoutEffect(() => {
    const l = leaving.current;
    if (!l) return;
    if (l.kind === "bar" ? barShown : items.some((p) => p.id === l.id && laneOf(p.status) === l.lane)) return;
    leaving.current = null;
    focusIfDropped(l.next());
  }, [items, barShown]);

  const dayBatches = useMemo(() => {
    const map = new Map<string, Proposal[]>();
    for (const p of triage) {
      const day = p.created_at.slice(0, 10);
      const bucket = map.get(day) ?? [];
      bucket.push(p);
      map.set(day, bucket);
    }
    return [...map.entries()]
      .sort(([a], [b]) => b.localeCompare(a))
      .map(([day, dayItems]) => ({ day, items: dayItems }));
  }, [triage]);

  const newestDay = dayBatches[0]?.day ?? null;
  const effectiveExpandedDays = useMemo(
    () => expandedDays ?? (newestDay ? new Set([newestDay]) : new Set<string>()),
    [expandedDays, newestDay],
  );

  // On-screen order for job-page prev/next (same pattern as the Jobs page's
  // cs-tracker-seq). History only when that lane is expanded.
  useEffect(() => {
    const visible: Proposal[] = [
      ...needsYou,
      ...dayBatches.flatMap(({ day, items: dayItems }) =>
        effectiveExpandedDays.has(day) ? dayItems : [],
      ),
      ...queued,
      ...inFlight,
      ...(historyOpen ? history : []),
    ];
    // Dedupe job ids while preserving first-seen order (a job should only
    // appear once even if filters somehow double-list).
    const ids: string[] = [];
    const seen = new Set<string>();
    for (const p of visible) {
      if (seen.has(p.job_id)) continue;
      seen.add(p.job_id);
      ids.push(p.job_id);
    }
    storeProposalSequence(ids);
  }, [
    needsYou,
    dayBatches,
    effectiveExpandedDays,
    queued,
    inFlight,
    historyOpen,
    history,
  ]);

  const toggleSelected = (id: string, next: boolean) => {
    setSelected((prev) => {
      const copy = new Set(prev);
      if (next) copy.add(id);
      else copy.delete(id);
      return copy;
    });
  };

  const exitSelect = () => {
    setSelecting(false);
    setSelected(new Set());
  };

  const selectAllShown = (ids: string[], on: boolean) => {
    setSelected((prev) => {
      const copy = new Set(prev);
      for (const id of ids) {
        if (on) copy.add(id);
        else copy.delete(id);
      }
      return copy;
    });
  };

  if (isLoadFailure({ data, isError, fetchStatus, errorUpdateCount })) {
    return (
      <LoadErrorState
        title="Couldn't load your Agent inbox."
        detail={loadErrorDetail(error)}
        retrying={isFetching}
        onRetry={() => void refetch()}
      />
    );
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <EmptyState
        icon={Bot}
        title="No proposals yet"
        // The page header carries the consent line (no submit without your yes); once is enough.
        description="Proposals come from an AI agent you connect, such as Claude, Codex or the ChatGPT desktop app. It connects through MCP (the standard way AI apps connect to tools). The app never proposes jobs itself."
        action={
          <div className="flex max-w-full flex-col items-center gap-2 px-4">
            {/* Links styled as buttons, not Buttons rendered as links: Base UI's Button
                gives its element role="button", so these were announced as buttons.
                The first label is long; it wraps at 375 instead of overflowing. */}
            <a href={JOB_HUNT_SKILL_URL} target="_blank" rel="noopener noreferrer" className={cn(buttonVariants(), "h-auto min-h-8 max-w-full py-1.5 whitespace-normal")}>
              <BookOpen className="size-4" aria-hidden="true" />
              Start a hunt: install the job-hunt skill, ready-made instructions for your agent
            </a>
            <div className="flex flex-wrap justify-center gap-2">
              <a href={AGENT_APPLICATIONS_URL} target="_blank" rel="noopener noreferrer" className={buttonVariants({ variant: "ghost" })}>
                How agent applications work
              </a>
              <Link href={CONNECTED_AGENTS_SETTINGS} className={buttonVariants({ variant: "ghost" })}>
                <SettingsIcon className="size-4" aria-hidden="true" />
                Connect an agent
              </Link>
            </div>
          </div>
        }
      />
    );
  }

  const rowProps = {
    since,
    duplicateKeys,
    pending: actions.pending,
    actingIds: actions.actingIds,
    leavingIds,
    onAct: (p: Proposal, action: RowAction, from: HTMLElement) => {
      const l: Leaving = {
        kind: "row",
        id: p.id,
        lane: laneOf(p.status),
        // The next row's same control, else the previous row's, else the lane.
        next: focusSuccessor(from.closest(".collapse-exit"), `[data-row-action="${action}"]`),
      };
      leaving.current = l;
      if (action === "queue") actions.transition({ id: p.id, status: "accepted" });
      // Keep it: the agent's question answered yes, back to To review (the server links the application).
      else if (action === "keep") actions.transition({ id: p.id, status: "pending_review" });
      else if (action === "skip") setDeclineTarget({ mode: "single", id: p.id });
      else actions.remove({ id: p.id, next: l.next });
    },
    selected,
    selecting,
    onToggleSelected: toggleSelected,
  };
  // The bar leaves when select mode ends (Done, or its action landed): focus goes back to Select, or,
  // when the inbox emptied and Select is not drawn, to the To review lane or the page's content.
  const leaveBar = () => {
    leaving.current = { kind: "bar", next: () => selectButton.current ?? toReview.current ?? document.getElementById("main-content") };
  };
  const laneSelect = (ids: string[]) =>
    selecting && ids.length > 0
      ? { checked: ids.every((id) => selected.has(id)), onChange: (on: boolean) => selectAllShown(ids, on) }
      : undefined;
  const selectToggle = nothingMatches ? null : (
    <SelectToggle ref={selectButton} selecting={selecting} onClick={() => (selecting ? exitSelect() : setSelecting(true))} />
  );

  return (
    <div className="flex flex-col gap-6 pb-20">
      {/* The lanes stay later siblings of the toolbar: globals.css clears a
          focused row from under the stuck toolbar (and the bulk bar) only for
          `[data-slot="list-toolbar"] ~ :focus-within`. */}
      {/* Search and filters are for a long inbox, or while one is in use (so it can always be cleared). */}
      {filtersShown(items.length, { q, role, board, minScore, sort }) ? (
        <ListToolbar>
          {/* The search and one sort select in view; Role, Job board and Minimum score under Filters. On a
              phone the controls wrap whole instead of clipping a value. */}
          <div className="flex flex-wrap items-center gap-2">
            <ListSearch label="Search the Agent inbox" value={q} onChange={setQ} />
            <Select
              value={sort}
              onValueChange={(v) => setSort((v as SortKey) ?? "score")}
            >
              <SelectTrigger className="h-8 shrink-0 grow sm:grow-0 sm:min-w-[10rem]" aria-label="Sort">
                <SelectValue>{SORT_LABELS[sort]}</SelectValue>
              </SelectTrigger>
              <SelectContent align="start" alignItemWithTrigger={false} className="w-auto min-w-[12rem]">
                {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
                  <SelectItem key={key} value={key}>
                    {SORT_LABELS[key]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="ml-auto flex items-center gap-1">
              <FiltersButton
                open={filtersOpen}
                onToggle={() => setFiltersOpen((o) => !o)}
                controls={filtersId}
                active={(role === "all" ? 0 : 1) + (board === "all" ? 0 : 1) + (minScore == null ? 0 : 1)}
              />
              {selectToggle}
            </div>
          </div>
          <div id={filtersId} hidden={!filtersOpen} className="flex flex-wrap items-center gap-1.5">
            <Select value={role} onValueChange={(v) => setRole(v ?? "all")}>
              <SelectTrigger className="h-8 shrink-0 grow sm:grow-0 sm:min-w-[10rem]" aria-label="Role">
                <SelectValue>{role === "all" ? "All roles" : roleLabel(role)}</SelectValue>
              </SelectTrigger>
              <SelectContent align="start" alignItemWithTrigger={false} className="w-auto min-w-[12rem]">
                <SelectItem value="all">All roles</SelectItem>
                {roles.map((r) => (
                  <SelectItem key={r} value={r}>
                    {roleLabel(r)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={board} onValueChange={(v) => setBoard(v ?? "all")}>
              <SelectTrigger className="h-8 shrink-0 grow sm:grow-0 sm:min-w-[10rem]" aria-label="Job board">
                <SelectValue>{board === "all" ? "All boards" : board}</SelectValue>
              </SelectTrigger>
              <SelectContent align="start" alignItemWithTrigger={false} className="w-auto min-w-[12rem]">
                <SelectItem value="all">All boards</SelectItem>
                {boards.map((b) => (
                  <SelectItem key={b} value={b}>
                    {b}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={minScore == null ? "any" : String(minScore)}
              onValueChange={(v) =>
                setMinScore(v && v !== "any" ? (Number(v) as ScoreFloor) : null)
              }
            >
              <SelectTrigger className="h-8 shrink-0 grow sm:grow-0 sm:min-w-[8rem]" aria-label="Minimum score">
                <SelectValue>{scoreLabel(minScore)}</SelectValue>
              </SelectTrigger>
              <SelectContent align="start" alignItemWithTrigger={false} className="w-auto min-w-[10rem]">
                <SelectItem value="any">{scoreLabel(null)}</SelectItem>
                {SCORE_FLOORS.map((floor) => (
                  <SelectItem key={floor} value={String(floor)}>
                    {scoreLabel(floor)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </ListToolbar>
      ) : selectToggle ? (
        <div className="-mb-4 flex justify-end">{selectToggle}</div>
      ) : null}

      {nothingMatches ? (
        <EmptyState
          title="Nothing matches these filters"
          description="Try another role, board or score, or clear the search."
        />
      ) : (
        <>
          {needsYou.length > 0 ? (
            <Lane
              title={`Needs you · ${needsYou.length}`}
              help={needsYouHelp(needsYou.map((p) => p.status))}
              select={laneSelect(selectableIds(needsYou, "needs_you"))}
              anchor="inbox-needs-you"
            >
              {needsYou.map((p) => (
                <ProposalRow
                  key={p.id}
                  proposal={p}
                  lane="needs_you"
                  {...rowProps}
                />
              ))}
            </Lane>
          ) : null}

          {triage.length > 0 ? (
            <Lane ref={toReview} title={`To review · ${triage.length}`} anchor="inbox-to-review">
              {dayBatches.map(({ day, items: dayItems }) => {
                const open = effectiveExpandedDays.has(day);
                const ids = selectableIds(dayItems, "triage");
                const allSelected = ids.every((id) => selected.has(id));
                return (
                  // One group per day inside the lane's card: its header row, then its rows.
                  <div key={day}>
                    <div className="flex min-h-10 flex-wrap items-center gap-2 px-5">
                      <button
                        type="button"
                        className="text-muted-foreground inline-flex items-center gap-1 text-label-medium"
                        onClick={() => {
                          setExpandedDays((prev) => {
                            const base =
                              prev ?? (newestDay ? new Set([newestDay]) : new Set());
                            const next = new Set(base);
                            if (next.has(day)) next.delete(day);
                            else next.add(day);
                            return next;
                          });
                        }}
                      >
                        <ChevronDown
                          className={cn(
                            "size-3.5 transition-transform",
                            !open && "-rotate-90",
                          )}
                          aria-hidden="true"
                        />
                        {formatDayLabel(day)} · {dayItems.length}{" "}
                        {dayItems.length === 1 ? "proposal" : "proposals"}
                      </button>
                      {open && selecting && ids.length > 0 ? (
                        <label className="text-muted-foreground ml-auto inline-flex items-center gap-1.5 text-body-small">
                          <Checkbox checked={allSelected && ids.length > 0} onCheckedChange={(next) =>
                              selectAllShown(ids, next)} />
                          Select all shown
                        </label>
                      ) : null}
                    </div>
                    {open ? (
                      // Rows only, so a row's neighbours are rows (focusSuccessor).
                      <div className="divide-y border-t">
                        {dayItems.map((p) => (
                          <ProposalRow
                            key={p.id}
                            proposal={p}
                            lane="triage"
                            {...rowProps}
                          />
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </Lane>
          ) : null}

          {queued.length > 0 ? (
            <Lane title={`Queued · ${queued.length}`} select={laneSelect(selectableIds(queued, "queued"))} anchor="inbox-queued">
              {queued.map((p) => (
                <ProposalRow key={p.id} proposal={p} lane="queued" {...rowProps} />
              ))}
            </Lane>
          ) : null}

          {inFlight.length > 0 ? (
            <Lane title={`Applying · ${inFlight.length}`}>
              {inFlight.map((p) => (
                <ProposalRow
                  key={p.id}
                  proposal={p}
                  lane="in_flight"
                  {...rowProps}
                />
              ))}
            </Lane>
          ) : null}

          {/* A lane with nothing in it is not drawn; History is a fold, closed until you open it. */}
          {historyAll.length > 0 ? (
            <section tabIndex={-1} aria-label="History" id="inbox-history" className="outline-none tall:scroll-mt-28">
              <Fold title="History" summary={historyAll.length} open={historyOpen} onOpenChange={setHistoryOpen}>
                {historyOpen ? (
                  <div className="flex flex-col gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <FilterChips
                        label="History status"
                        value={historyStatus}
                        onChange={setHistoryStatus}
                        options={INBOX_LANES.history.map((status) => ({
                          value: status,
                          label: STATUS_LABELS[status],
                          count: historyAll.filter((p) => historyStatusOf(p.status, p.reason) === status).length,
                        }))}
                      />
                      {(() => {
                        const select = laneSelect(selectableIds(history, "history"));
                        return select ? <SelectAll {...select} className="ml-auto" /> : null;
                      })()}
                    </div>
                    {history.length === 0 ? (
                      <p className="text-muted-foreground text-body-medium">
                        No history with these statuses.
                      </p>
                    ) : (
                      // The fold is the card: its rows reach its edges, as a lane's do.
                      <div className="-mx-5 -mb-5 divide-y overflow-clip rounded-b-corner-md border-t">
                        {history.map((p) => (
                          <ProposalRow
                            key={p.id}
                            proposal={p}
                            lane="history"
                            {...rowProps}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                ) : null}
              </Fold>
            </section>
          ) : null}
        </>
      )}

      <ListCapNotice loaded={items.length} limit={PROPOSALS_LIMIT} total={data?.total} noun="proposals" />

      {selecting ? (
        <BulkBar
          selectedCount={selectedShown.length}
          can={bulkCan}
          pending={actions.pending}
          queuePending={actions.queuePending}
          onQueue={() => {
            leaveBar();
            actions.bulk({ ids: selectedShown, status: "accepted" });
          }}
          onDecline={() => {
            leaveBar();
            setDeclineTarget({ mode: "bulk" });
          }}
          onDelete={() => {
            leaveBar();
            const next = leaving.current?.next;
            actions.removeMany({ ids: selectedShown, next });
          }}
          onDone={() => {
            leaveBar();
            exitSelect();
          }}
        />
      ) : null}

      <DeclineDialog
        open={declineTarget != null}
        onOpenChange={(open) => {
          if (open) return;
          // Cancelled: nothing leaves, and Base UI returns focus to the Skip that opened it.
          leaving.current = null;
          setDeclineTarget(null);
        }}
        pending={actions.pending}
        blocked={declineTarget?.mode === "bulk" && !bulkCan.skip}
        finalFocus={() => {
          const next = skipReturn.current;
          skipReturn.current = null;
          return next ? finalFocusOn(next()) : true;
        }}
        onConfirm={(reason) => {
          if (!declineTarget) return;
          if (declineTarget.mode === "single") {
            actions.transition({ id: declineTarget.id, status: "rejected", reason });
            return;
          }
          actions.bulk({ ids: selectedShown, status: "rejected", reason });
        }}
      />
    </div>
  );
}

function Lane({
  title,
  help = [],
  children,
  ref,
  anchor,
  select,
}: {
  title: string;
  /** Select mode's "Select all" for this lane's pickable rows. */
  select?: { checked: boolean; onChange: (on: boolean) => void };
  /** How this lane's rows are answered, under its heading (the Needs-you lane). */
  help?: string[];
  children: React.ReactNode;
  ref?: React.Ref<HTMLElement>;
  anchor?: string;
}) {
  const headingId = useId();
  return (
    // tabIndex={-1}: named by its heading, it takes focus when the last row acted on, or the bulk
    // bar, leaves it. Its rows sit in their own list, so a row's neighbours are rows. One card per
    // lane, its rows divided by a hairline (board "Agent inbox, same rows").
    <section ref={ref} tabIndex={-1} aria-labelledby={headingId} id={anchor} className="flex flex-col gap-2 overflow-x-auto outline-none tall:scroll-mt-28">
      <div className="flex items-center gap-2">
        <h2 id={headingId} className="text-title-small">
          {title}
        </h2>
        {select ? <SelectAll {...select} className="ml-auto" /> : null}
      </div>
      {help.map((line) => (
        <p key={line} className="text-muted-foreground max-w-[65ch] text-body-medium">
          {line}
        </p>
      ))}
      <div className="divide-y overflow-clip rounded-corner-md bg-card">{children}</div>
    </section>
  );
}

function SelectAll({ checked, onChange, className }: {
  checked: boolean;
  onChange: (on: boolean) => void;
  className?: string;
}) {
  return (
    <label className={cn("text-muted-foreground inline-flex items-center gap-1.5 text-body-small", className)}>
      <Checkbox checked={checked} onCheckedChange={onChange} />
      Select all
    </label>
  );
}

function ProposalRow({
  proposal,
  lane,
  since,
  duplicateKeys,
  selected,
  selecting,
  onToggleSelected,
  onAct,
  pending,
  actingIds,
  leavingIds,
}: {
  proposal: Proposal;
  lane: LaneKind;
  since: string | null;
  duplicateKeys: Set<string>;
  selected: Set<string>;
  /** Select mode: a checkbox on the row, and a click on the row picks it instead of opening the job. */
  selecting: boolean;
  onToggleSelected: (id: string, next: boolean) => void;
  onAct: (proposal: Proposal, action: RowAction, from: HTMLElement) => void;
  pending?: boolean;
  /** Ids whose Queue or Skip is in flight: this row's buttons give way to a spinner. */
  actingIds: ReadonlySet<string>;
  /** Ids collapsing out (with the status they leave). */
  leavingIds: ReadonlyMap<string, ProposalStatus>;
}) {
  const job = proposal.job;
  const owner = job.ownership;
  const ownership = jobOwnershipView(owner);
  const pickable = bulkActionsOf(proposal, lane).length > 0;
  const acting = actingIds.has(proposal.id);
  const base = chosenBase(proposal);
  const baseName = useBaseResumeName(base ?? "", base !== null);
  const colorOf = useBaseResumeColor();
  const score = chosenScore(proposal);
  const byLine = proposalByLine(proposal.proposed_by, proposal.status);
  const meta = [byLine, formatTimeAgo(proposal.created_at)].filter(Boolean).join(" · ");
  const isDup = duplicateKeys.has(duplicateKey(proposal));
  // What the agent needs, in its words: a question (Keep it or Skip here), or a stop it waits out in its chat.
  const needs = lane === "needs_you" ? needsYouLine(proposal.status, proposal.reason) : null;
  const showKeep = lane === "needs_you" && proposal.status === "needs_decision";
  const showCheckbox = selecting;
  // Skip is in every lane still waiting on you (To review has its own beside Queue). First live run:
  // needs_human rows had NO actions and could only be resolved via an agent.
  const showDecline = lane === "queued" || lane === "needs_you";
  const canDelete = canDeleteIn(proposal, lane);
  // Focusable while any triage runs (a natively disabled button dropped focus to <body>), and one
  // handler for all: the link around the row must not see the click.
  const act = (action: RowAction) => (e: React.MouseEvent<HTMLElement>) => {
    e.preventDefault();
    e.stopPropagation();
    onAct(proposal, action, e.currentTarget);
  };

  return (
    // One child, so the wrapper can close its height (.collapse-exit in globals.css). A row of the lane's
    // card, 60px for two lines; a question from the agent adds one truncated line.
    <div className="collapse-exit" data-leaving={leavingIds.get(proposal.id) === proposal.status || undefined}>
      <div
        className="group flex min-h-15 items-stretch gap-1 transition-colors hover:bg-surface-container-low dark:hover:bg-surface-container-high"
        data-pending={acting ? "true" : undefined}
      >
        {showCheckbox ? (
          <label className="flex items-center pl-5">
            <Checkbox
              disabled={!pickable}
              checked={selected.has(proposal.id)}
              onCheckedChange={(next) => onToggleSelected(proposal.id, next)}
              aria-label={`Select ${job.title ?? "Untitled role"}${job.company ? ` at ${job.company}` : ""}`}
            />
          </label>
        ) : null}
        <Link
          href={`/jobs/${proposal.job_id}?from=proposals`}
          // In select mode the row is a big target for its checkbox (which keyboards use), as in Photos.
          onClick={selecting ? (e) => {
            e.preventDefault();
            if (pickable) onToggleSelected(proposal.id, !selected.has(proposal.id));
          } : undefined}
          // flex-wrap + a real basis on the text, not flex-1 (the job
          // header's fix): with basis-0 the shrink-0 chips kept their width
          // and squeezed the title to a few letters at 768 and to nothing at
          // 375. Narrow, the chips wrap under the text and the decorative
          // monogram steps aside. The focus outline sits inside: the card clips.
          className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1 px-5 py-2.5 text-left -outline-offset-2"
        >
          <CompanyMonogram name={job.company ?? "?"} className="hidden sm:flex" />
          <div className="min-w-0 grow basis-[10rem]">
            <div className="flex flex-wrap items-center gap-2">
              <span className="truncate text-title-small">
                {job.title ?? "Untitled role"}
              </span>
              {job.disqualifying_for_opt && proposal.readiness?.knockout !== "opt" ? (
                <span
                  className="text-warning inline-flex items-center gap-1 text-body-small"
                  title="OPT is the US student work permit"
                >
                  <TriangleAlert className="size-3.5" aria-hidden="true" />
                  May not accept OPT
                </span>
              ) : null}
              {isDup ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-warning-container px-2 py-0.5 text-label-small text-on-warning-container">
                  <TriangleAlert className="size-3 shrink-0" aria-hidden="true" />
                  Possible duplicate
                </span>
              ) : null}
              {isNew(proposal.created_at, since) ? (
                <span className="inline-flex items-center gap-1 text-label-small text-primary">
                  <span className="size-1.5 rounded-full bg-primary" aria-hidden="true" />
                  New
                </span>
              ) : null}
              <ReadinessMarks readiness={proposal.readiness} />
            </div>
            {/* One line: the job's facts, then who filed it and when (the whole sentence on hover). */}
            <div className="text-muted-foreground flex min-w-0 items-center gap-2 text-body-small" title={meta}>
              <span className="min-w-0 truncate">
                {jobMetaLine([job.company, job.location, humanizeEnum(job.work_mode)])}
              </span>
              {byLine ? (
                <>
                  <ActorChip kind={proposal.proposed_by === "you" ? "you" : "agent"} name={agentDisplayName(proposal.proposed_by)} className="min-w-0 shrink" />
                  <span className="shrink-0">{formatTimeAgo(proposal.created_at)}</span>
                </>
              ) : (
                <span className="shrink-0">{formatTimeAgo(proposal.created_at)}</span>
              )}
            </div>
            {/* One line; the agent's whole question on hover and on the job page. */}
            {needs ? <p className="truncate text-body-small" title={needs}>{needs}</p> : null}
          </div>
          {base ? (
            <span className="text-muted-foreground hidden shrink-0 items-center gap-2 text-body-small sm:inline-flex">
              <ResumeTag hue={colorOf(base)}>{baseName}</ResumeTag>
              {score != null ? <ScoreBar value={score} label="Match score" valueText={score.toFixed(1)} /> : null}
            </span>
          ) : null}
          {/* D5: To review, Queued and Applying rows all share one status, so the lane says it. */}
          {lane === "history" || lane === "needs_you" ? (
            <Badge
              className={cn("shrink-0", STATUS_BADGE_CLASS[historyStatusOf(proposal.status, proposal.reason)])}
              variant="secondary"
            >
              {historyLabel(proposal.status, proposal.reason, STATUS_LABELS[proposal.status])}
            </Badge>
          ) : null}
        </Link>
        {/* Always in view, outside the link: a locked job's reason and its request, in a pop-up. */}
        <div className="flex items-center" onClick={(e) => e.stopPropagation()}>
          <JobOwnershipPopover jobId={proposal.job_id} ownership={owner} />
        </div>
        <div
          className={cn(
            "relative flex items-center gap-0.5 pr-2 opacity-0 transition-opacity duration-150 group-hover:opacity-100 focus-within:opacity-100 pointer-coarse:opacity-100",
            // Select mode acts from the bar: a row's own buttons step aside (its spinner still shows).
            selecting && !acting && "hidden",
            // The buttons stay (focus is kept) under the spinner that answers the press; the focus ring moves out here.
            acting && "rounded-full opacity-100 [&_button]:opacity-0! has-[button:focus-visible]:ring-3 has-[button:focus-visible]:ring-ring",
          )}
        >
          {acting ? (
            <span role="status" className="absolute inset-0 flex items-center justify-center">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              <span className="sr-only">Working</span>
            </span>
          ) : null}
          {lane === "triage" ? (
            <>
              <IconButton
                label="Queue"
                icon={<QueueIcon />}
                data-row-action="queue"
                disabled={pending || !ownership.canRequest}
                focusableWhenDisabled
                className="data-disabled:pointer-events-none data-disabled:opacity-50"
                onClick={act("queue")}
              />
              <IconButton
                label="Skip"
                icon={<X />}
                data-row-action="skip"
                disabled={pending || !ownership.canRequest}
                focusableWhenDisabled
                className="data-disabled:pointer-events-none data-disabled:opacity-50"
                onClick={act("skip")}
              />
            </>
          ) : null}
          {showKeep ? (
            <IconButton
              label="Keep it"
              icon={<ApproveIcon />}
              data-row-action="keep"
              disabled={pending}
              {...ownershipControlProps(!ownership.canRequest)}
              focusableWhenDisabled
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              onClick={act("keep")}
            />
          ) : null}
          {showDecline ? (
            <IconButton
              label="Skip"
              icon={<X />}
              data-row-action="skip"
              disabled={pending || !ownership.canRequest}
              focusableWhenDisabled
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              onClick={act("skip")}
            />
          ) : null}
          {canDelete ? (
            <IconButton
              label="Delete proposal"
              icon={<Trash2 />}
              data-row-action="delete"
              disabled={pending || !ownership.canWrite}
              focusableWhenDisabled
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              onClick={act("delete")}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}

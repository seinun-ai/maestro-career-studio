"use client";

import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { useQuery } from "@tanstack/react-query";
import { GuardedLink as Link } from "@/components/guarded-link";
import {
  AlertTriangle,
  BookOpen,
  Bot,
  Check,
  ChevronDown,
  Settings as SettingsIcon,
  Trash2,
  X,
} from "lucide-react";

import { CompanyMonogram } from "@/components/company-monogram";
import { EmptyState } from "@/components/empty-state";
import { ListCapNotice } from "@/components/list-cap-notice";
import { ListSearch } from "@/components/list-search";
import { ListToolbar } from "@/components/list-toolbar";
import { useRoleLabel } from "@/components/role-category-picker";
import {
  BulkBar,
  DeclineDialog,
  useProposalActions,
} from "@/components/proposals/triage-actions";
import { IconButton } from "@/components/icon-button";
import { PROPOSAL_STATUS_CHIP } from "@/components/status-chip";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LoadErrorState } from "@/components/load-error-state";
import { useBaseResumeName } from "@/hooks/use-base-resume-label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AGENT_APPLICATIONS_URL,
  CONNECTED_AGENTS_SETTINGS,
  JOB_HUNT_SKILL_URL,
} from "@/lib/agent-links";
import { proposalByLine } from "@/lib/agent-name";
import { apiFetch } from "@/lib/api";
import { formatTimeAgo } from "@/lib/format-date";
import {
  SCORE_FLOORS,
  type ScoreFloor,
  boardHost,
  chosenScore,
  filterProposals,
} from "@/lib/inbox-filter";
import { finalFocusOn, focusIfDropped, focusSuccessor } from "@/lib/focus";
import {
  INBOX_LANES,
  type InboxLane,
  STATUS_ORDER,
  inLane,
  laneOf,
  selectedAmong,
} from "@/lib/inbox-lanes";
import { isLoadFailure } from "@/lib/query-state";
import { cn } from "@/lib/utils";
import {
  type Proposal,
  type ProposalListResponse,
  type ProposalStatus,
} from "@/lib/types";

const PROPOSALS_KEY = ["proposals"] as const;
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
type RowAction = "queue" | "skip" | "delete";

/**
 * Where focus goes when the control holding it leaves: one row leaving its lane, or the bulk bar leaving.
 * Read at the click, while the row is there (lib/focus.ts `focusSuccessor`).
 */
type Leaving =
  | { kind: "row"; id: string; lane: InboxLane | null; next: () => HTMLElement | null }
  | { kind: "bar"; next: () => HTMLElement | null };

type SortKey = "score" | "newest" | "role" | "company";

// Values that describe themselves: the toolbar has no captions.
const SORT_LABELS: Record<SortKey, string> = {
  score: "Best score first",
  newest: "Newest first",
  role: "Role A–Z",
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
      case "role":
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

export function ProposalsSection() {
  const { data, isLoading, isError, error, isFetching, fetchStatus, refetch, errorUpdateCount } = useQuery({
    queryKey: PROPOSALS_KEY,
    queryFn: () =>
      apiFetch<ProposalListResponse>(`/api/proposals?limit=${PROPOSALS_LIMIT}`),
  });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortKey>("score");
  const [role, setRole] = useState("all");
  const [board, setBoard] = useState("all");
  const [minScore, setMinScore] = useState<ScoreFloor | null>(null);
  const roleLabel = useRoleLabel();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyStatus, setHistoryStatus] = useState<"all" | ProposalStatus>(
    "all",
  );
  const [expandedDays, setExpandedDays] = useState<Set<string> | null>(null);
  const [declineTarget, setDeclineTarget] = useState<
    { mode: "single"; id: string } | { mode: "bulk" } | null
  >(null);

  // Focus never falls to <body> when a Queue, Skip, Delete or Clear takes its control away.
  const leaving = useRef<Leaving | null>(null);
  // Set when a Skip from the dialog succeeds: the dialog's close hands focus on (its opener goes).
  const skipReturn = useRef<(() => HTMLElement | null) | null>(null);
  const toReview = useRef<HTMLElement>(null);
  const historyId = useId();
  const actions = useProposalActions({
    onDone: (ids) => {
      // A row queued, skipped or deleted on its own leaves the selection; so do the bar's rows.
      setSelected((prev) => {
        const copy = new Set(prev);
        for (const id of ids) copy.delete(id);
        return copy;
      });
      if (declineTarget) skipReturn.current = leaving.current?.next ?? null;
      setDeclineTarget(null);
    },
    onUndone: () => {
      leaving.current = null;
    },
  });

  const items = useMemo(() => data?.items ?? [], [data]);

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
    () => sortProposals(inLane(filtered, "queued"), sort),
    [filtered, sort],
  );
  const inFlight = useMemo(
    () => sortProposals(inLane(filtered, "in_flight"), sort),
    [filtered, sort],
  );
  const historyAll = useMemo(() => inLane(filtered, "history"), [filtered]);
  const history = useMemo(() => {
    const scoped =
      historyStatus === "all"
        ? historyAll
        : historyAll.filter((p) => p.status === historyStatus);
    return sortProposals(scoped, sort);
  }, [historyAll, historyStatus, sort]);

  // Bulk actions and the bar's count see only the rows shown: never a row a filter or the search hides.
  const selectedShown = useMemo(() => selectedAmong(triage, selected), [triage, selected]);
  const barShown = selectedShown.length > 0;

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

  // On-screen order for job-page prev/next (same pattern as Applications'
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
        detail={(error as Error)?.message}
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
        description="Proposals come from an AI agent you connect over MCP (Claude, Codex, the ChatGPT desktop app), never from the app itself. Nothing is submitted without your yes."
        action={
          <div className="flex max-w-full flex-col items-center gap-2 px-4">
            {/* The label is long; let it wrap at 375 instead of overflowing. */}
            <Button
              nativeButton={false}
              className="h-auto min-h-8 max-w-full py-1.5 whitespace-normal"
              render={
                <a href={JOB_HUNT_SKILL_URL} target="_blank" rel="noopener noreferrer">
                  <BookOpen className="size-4" aria-hidden="true" />
                  Start a hunt: install the ready-made job-hunt skill
                </a>
              }
            />
            <div className="flex flex-wrap justify-center gap-2">
              <Button
                variant="ghost"
                nativeButton={false}
                render={
                  <a href={AGENT_APPLICATIONS_URL} target="_blank" rel="noopener noreferrer">
                    How agent applications work
                  </a>
                }
              />
              <Button
                variant="ghost"
                nativeButton={false}
                render={
                  <Link href={CONNECTED_AGENTS_SETTINGS}>
                    <SettingsIcon className="size-4" aria-hidden="true" />
                    Connect an agent
                  </Link>
                }
              />
            </div>
          </div>
        }
      />
    );
  }

  const rowProps = {
    duplicateKeys,
    pending: actions.pending,
    onAct: (p: Proposal, action: RowAction, from: HTMLElement) => {
      const l: Leaving = {
        kind: "row",
        id: p.id,
        lane: laneOf(p.status),
        // The next row's same control, else the previous row's, else the lane.
        next: focusSuccessor(from.closest('[data-slot="card"]'), `[data-row-action="${action}"]`),
      };
      leaving.current = l;
      if (action === "queue") actions.transition({ id: p.id, status: "accepted" });
      else if (action === "skip") setDeclineTarget({ mode: "single", id: p.id });
      else actions.remove({ id: p.id, next: l.next });
    },
    selected,
    onToggleSelected: toggleSelected,
  };
  // The bar leaves with its last shown selection: focus goes to the To review lane.
  const leaveBar = () => {
    leaving.current = { kind: "bar", next: () => toReview.current };
  };

  return (
    <div className="flex flex-col gap-6 pb-20">
      {/* The lanes stay later siblings of the toolbar: globals.css clears a
          focused row from under the stuck toolbar (and the bulk bar) only for
          `[data-slot="list-toolbar"] ~ :focus-within`. */}
      <ListToolbar>
        <ListSearch label="Search the Agent inbox" value={q} onChange={setQ} />
        <div className="flex flex-wrap items-center gap-1.5">
          <Select
            value={sort}
            onValueChange={(v) => setSort((v as SortKey) ?? "score")}
          >
            <SelectTrigger className="h-8 min-w-[10rem] rounded-full" aria-label="Sort">
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
          <Select value={role} onValueChange={(v) => setRole(v ?? "all")}>
            <SelectTrigger className="h-8 min-w-[10rem] rounded-full" aria-label="Role">
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
            <SelectTrigger className="h-8 min-w-[10rem] rounded-full" aria-label="Job board">
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
            <SelectTrigger className="h-8 min-w-[8rem] rounded-full" aria-label="Minimum score">
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

      {nothingMatches ? (
        <EmptyState
          title="Nothing matches these filters"
          description="Try another role, board or score, or clear the search."
        />
      ) : (
        <>
          {needsYou.length > 0 ? (
            <Lane title={`Needs you · ${needsYou.length}`}>
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

          <Lane ref={toReview} title={`To review · ${triage.length}`}>
            {dayBatches.length === 0 ? (
              <p className="text-muted-foreground text-sm">Nothing to review.</p>
            ) : (
              dayBatches.map(({ day, items: dayItems }) => {
                const open = effectiveExpandedDays.has(day);
                const ids = dayItems.map((p) => p.id);
                const allSelected = ids.every((id) => selected.has(id));
                return (
                  <div key={day} className="flex flex-col gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        className="text-muted-foreground inline-flex items-center gap-1 text-xs font-medium"
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
                      {open ? (
                        <label className="text-muted-foreground ml-auto inline-flex items-center gap-1.5 text-xs">
                          <Checkbox checked={allSelected && ids.length > 0} onCheckedChange={(next) =>
                              selectAllShown(ids, next)} />
                          Select all shown
                        </label>
                      ) : null}
                    </div>
                    {open ? (
                      // Rows only, so a row's neighbours are rows (focusSuccessor).
                      <div className="flex flex-col gap-2">
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
              })
            )}
          </Lane>

          {queued.length > 0 ? (
            <Lane title={`Queued · ${queued.length}`}>
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

          <section tabIndex={-1} aria-labelledby={historyId} className="flex flex-col gap-2 outline-none">
            <button
              id={historyId}
              type="button"
              className="text-muted-foreground inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide"
              onClick={() => setHistoryOpen((v) => !v)}
            >
              <ChevronDown
                className={cn(
                  "size-3.5 transition-transform",
                  !historyOpen && "-rotate-90",
                )}
                aria-hidden="true"
              />
              History · {historyAll.length}
            </button>
            {historyOpen ? (
              <>
                <div className="flex flex-wrap gap-1.5" role="group" aria-label="History status">
                  {(
                    [
                      "all", ...INBOX_LANES.history,
                    ] as const
                  ).map((status) => {
                    const active = historyStatus === status;
                    const label =
                      status === "all" ? "All" : STATUS_LABELS[status];
                    return (
                      <Button
                        key={status}
                        size="xs"
                        variant={active ? "tonal" : "outline"}
                        aria-pressed={active}
                        className="rounded-full"
                        onClick={() => setHistoryStatus(status)}
                      >
                        {active && <Check />}
                        {label}
                      </Button>
                    );
                  })}
                </div>
                {history.length === 0 ? (
                  <p className="text-muted-foreground text-sm">No history yet.</p>
                ) : (
                  <div className="flex flex-col gap-2">
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
              </>
            ) : null}
          </section>
        </>
      )}

      <ListCapNotice loaded={items.length} limit={PROPOSALS_LIMIT} total={data?.total} noun="proposals" />

      <BulkBar
        selectedCount={selectedShown.length}
        pending={actions.pending}
        onAccept={() => {
          leaveBar();
          actions.bulk({ ids: selectedShown, status: "accepted" });
        }}
        onDecline={() => {
          leaveBar();
          setDeclineTarget({ mode: "bulk" });
        }}
        onClear={() => {
          leaveBar();
          setSelected(new Set());
        }}
      />

      <DeclineDialog
        open={declineTarget != null}
        onOpenChange={(open) => {
          if (open) return;
          // Cancelled: nothing leaves, and Base UI returns focus to the Skip that opened it.
          leaving.current = null;
          setDeclineTarget(null);
        }}
        pending={actions.pending}
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
  children,
  ref,
}: {
  title: string;
  children: React.ReactNode;
  ref?: React.Ref<HTMLElement>;
}) {
  const headingId = useId();
  return (
    // tabIndex={-1}: named by its heading, it takes focus when the last row acted on, or the bulk
    // bar, leaves it. Its rows sit in their own list, so a row's neighbours are rows.
    <section ref={ref} tabIndex={-1} aria-labelledby={headingId} className="flex flex-col gap-2 overflow-x-auto outline-none">
      <h2 id={headingId} className="text-muted-foreground text-xs font-medium uppercase tracking-wide">
        {title}
      </h2>
      <div className="flex flex-col gap-2">{children}</div>
    </section>
  );
}

type LaneKind = "needs_you" | "triage" | "queued" | "in_flight" | "history";

function ProposalRow({
  proposal,
  lane,
  duplicateKeys,
  selected,
  onToggleSelected,
  onAct,
  pending,
}: {
  proposal: Proposal;
  lane: LaneKind;
  duplicateKeys: Set<string>;
  selected: Set<string>;
  onToggleSelected: (id: string, next: boolean) => void;
  onAct: (proposal: Proposal, action: RowAction, from: HTMLElement) => void;
  pending?: boolean;
}) {
  const job = proposal.job;
  const base = chosenBase(proposal);
  const baseName = useBaseResumeName(base ?? "", base !== null);
  const score = chosenScore(proposal);
  const byLine = proposalByLine(proposal.proposed_by, proposal.status);
  const meta = [byLine, formatTimeAgo(proposal.created_at)].filter(Boolean).join(" · ");
  const isDup = duplicateKeys.has(duplicateKey(proposal));
  const showCheckbox = lane === "triage";
  // Decline is available in every non-terminal lane; Delete additionally on
  // needs_you (bogus/dead postings parked there never earn a decline record —
  // the backend 409s deletes only for submitted/uncertain). First live run:
  // needs_human rows had NO actions and could only be resolved via an agent.
  const showDecline = lane === "queued" || lane === "needs_you";
  const canDelete =
    lane === "needs_you" ||
    (lane === "history" &&
      (proposal.status === "rejected" || proposal.status === "expired"));
  // Focusable while any triage runs (a natively disabled button dropped focus to <body>), and one
  // handler for all: the link around the row must not see the click.
  const act = (action: RowAction) => (e: React.MouseEvent<HTMLElement>) => {
    e.preventDefault();
    e.stopPropagation();
    onAct(proposal, action, e.currentTarget);
  };

  return (
    <Card className="group">
      <CardContent className="p-0">
        <div className="flex items-stretch gap-1">
          {showCheckbox ? (
            <label className="flex items-center px-3">
              <Checkbox checked={selected.has(proposal.id)} onCheckedChange={(next) =>
                  onToggleSelected(proposal.id, next)} />
            </label>
          ) : null}
          <Link
            href={`/jobs/${proposal.job_id}?from=proposals`}
            // flex-wrap + a real basis on the text, not flex-1 (the job
            // header's fix): with basis-0 the shrink-0 chips kept their width
            // and squeezed the title to a few letters at 768 and to nothing at
            // 375. Narrow, the chips wrap under the text and the decorative
            // monogram steps aside.
            className="hover:bg-muted/40 flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1.5 rounded-xl p-3 text-left transition-colors sm:p-4"
          >
            <CompanyMonogram name={job.company ?? "?"} className="hidden sm:flex" />
            <div className="min-w-0 grow basis-[10rem]">
              <div className="flex flex-wrap items-center gap-2">
                <span className="truncate text-sm font-medium">
                  {job.title ?? "Untitled role"}
                </span>
                {job.disqualifying_for_opt ? (
                  <span
                    className="inline-flex items-center gap-1 text-xs text-amber-700 dark:text-amber-400"
                    title="Extraction flagged this posting as disqualifying for OPT"
                  >
                    <AlertTriangle className="size-3.5" aria-hidden="true" />
                    OPT
                  </span>
                ) : null}
                {isDup ? (
                  <span className="inline-flex items-center rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-800 dark:text-amber-400">
                    possible duplicate
                  </span>
                ) : null}
              </div>
              <div className="text-muted-foreground truncate text-xs">
                {[job.company, job.location, job.work_mode]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
              <div className="text-muted-foreground truncate text-xs" title={meta}>
                {meta}
              </div>
            </div>
            {base ? (
              <span className="text-muted-foreground hidden shrink-0 rounded-full bg-muted/70 px-2 py-0.5 text-xs sm:inline-flex">
                {baseName}
                {score != null ? ` · ${score}` : ""}
              </span>
            ) : null}
            <Badge
              className={cn("shrink-0", STATUS_BADGE_CLASS[proposal.status])}
              variant="secondary"
            >
              {STATUS_LABELS[proposal.status]}
            </Badge>
          </Link>
          <div className="flex items-center gap-0.5 pr-2 opacity-0 transition-opacity duration-150 group-hover:opacity-100 focus-within:opacity-100 pointer-coarse:opacity-100">
            {lane === "triage" ? (
              <>
                <IconButton
                  label="Accept"
                  icon={<Check />}
                  data-row-action="queue"
                  disabled={pending}
                  focusableWhenDisabled
                  className="data-disabled:pointer-events-none data-disabled:opacity-50"
                  onClick={act("queue")}
                />
                <IconButton
                  label="Skip"
                  icon={<X />}
                  data-row-action="skip"
                  disabled={pending}
                  focusableWhenDisabled
                  className="data-disabled:pointer-events-none data-disabled:opacity-50"
                  onClick={act("skip")}
                />
              </>
            ) : null}
            {showDecline ? (
              <IconButton
                label="Skip"
                icon={<X />}
                data-row-action="skip"
                disabled={pending}
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
                disabled={pending}
                focusableWhenDisabled
                className="data-disabled:pointer-events-none data-disabled:opacity-50"
                onClick={act("delete")}
              />
            ) : null}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

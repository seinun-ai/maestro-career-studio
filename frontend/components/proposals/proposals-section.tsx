"use client";

import { useEffect, useMemo, useState } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Trash2,
  X,
} from "lucide-react";

import { CompanyMonogram } from "@/components/company-monogram";
import { FunnelStrip } from "@/components/proposals/funnel-strip";
import {
  BulkBar,
  DeclineDialog,
  useProposalActions,
} from "@/components/proposals/triage-actions";
import { IconButton } from "@/components/icon-button";
import { PROPOSAL_STATUS_CHIP } from "@/components/status-chip";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LoadErrorState } from "@/components/load-error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  baseResumeLabel,
  type Proposal,
  type ProposalListResponse,
  type ProposalStatus,
} from "@/lib/types";

const PROPOSALS_KEY = ["proposals"] as const;
const SEQUENCE_STORE_KEY = "cs-proposals-seq";

function storeProposalSequence(jobIds: string[]) {
  try {
    sessionStorage.setItem(SEQUENCE_STORE_KEY, JSON.stringify(jobIds));
  } catch {
    // Session memory is a convenience — never let storage failures break the page.
  }
}

/** Display vocabulary — includes accepted triage queue. */
export const STATUS_ORDER: ProposalStatus[] = [
  "needs_decision",
  "needs_human",
  "pending_review",
  "accepted",
  "approved",
  "submitted",
  "submission_uncertain",
  "rejected",
  "expired",
];

// Both derived from the ONE vocabulary in status-chip.tsx. They stay exported
// under these names because they are the established import surface (the job
// page uses them), but they are no longer a second source of truth.
export const STATUS_LABELS = Object.fromEntries(
  STATUS_ORDER.map((k) => [k, PROPOSAL_STATUS_CHIP[k].label]),
) as Record<ProposalStatus, string>;

export const STATUS_BADGE_CLASS = Object.fromEntries(
  STATUS_ORDER.map((k) => [k, PROPOSAL_STATUS_CHIP[k].className]),
) as Record<ProposalStatus, string>;

const NEEDS_YOU: ProposalStatus[] = ["needs_decision", "needs_human"];
const TRIAGE: ProposalStatus[] = ["pending_review"];
const QUEUED: ProposalStatus[] = ["accepted"];
const IN_FLIGHT: ProposalStatus[] = ["approved"];
const HISTORY: ProposalStatus[] = [
  "submitted",
  "submission_uncertain",
  "rejected",
  "expired",
];

type SortKey = "score" | "newest" | "role" | "company";

const SORT_LABELS: Record<SortKey, string> = {
  score: "Best score",
  newest: "Newest",
  role: "Role",
  company: "Company",
};

function normalizeTitle(title: string): string {
  return title.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function duplicateKey(p: Proposal): string {
  return `${(p.job.company ?? "").toLowerCase()}|${normalizeTitle(p.job.title ?? "")}`;
}

function chosenScore(p: Proposal): number | null {
  const fit = (p.fit_json ?? {}) as Record<string, unknown>;
  const chosen = fit.chosen_base;
  const scores = fit.scores;
  if (typeof chosen !== "string" || !scores || typeof scores !== "object") {
    return null;
  }
  const value = (scores as Record<string, unknown>)[chosen];
  return typeof value === "number" ? value : null;
}

function chosenBase(p: Proposal): string | null {
  const fit = (p.fit_json ?? {}) as Record<string, unknown>;
  return typeof fit.chosen_base === "string" ? fit.chosen_base : null;
}

function boardHost(url: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname;
  } catch {
    return null;
  }
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

function filterProposals(
  items: Proposal[],
  {
    role,
    board,
    minScore,
  }: { role: string; board: string; minScore: string },
): Proposal[] {
  const min = minScore.trim() === "" ? null : Number(minScore);
  return items.filter((p) => {
    if (role !== "all" && p.job.role_category !== role) return false;
    if (board !== "all" && boardHost(p.job.source_url) !== board) return false;
    if (min != null && !Number.isNaN(min)) {
      const score = chosenScore(p);
      if (score == null || score < min) return false;
    }
    return true;
  });
}

export function ProposalsSection() {
  const { data, isLoading, isError, error, isFetching, refetch } = useQuery({
    queryKey: PROPOSALS_KEY,
    queryFn: () =>
      apiFetch<ProposalListResponse>("/api/proposals?limit=500"),
  });
  const actions = useProposalActions();

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [sort, setSort] = useState<SortKey>("score");
  const [role, setRole] = useState("all");
  const [board, setBoard] = useState("all");
  const [minScore, setMinScore] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyStatus, setHistoryStatus] = useState<"all" | ProposalStatus>(
    "all",
  );
  const [expandedDays, setExpandedDays] = useState<Set<string> | null>(null);
  const [declineTarget, setDeclineTarget] = useState<
    { mode: "single"; id: string } | { mode: "bulk" } | null
  >(null);

  const items = data?.items ?? [];

  const roles = useMemo(() => {
    const set = new Set<string>();
    for (const p of items) {
      if (p.job.role_category) set.add(p.job.role_category);
    }
    return [...set].sort();
  }, [items]);

  const boards = useMemo(() => {
    const set = new Set<string>();
    for (const p of items) {
      const host = boardHost(p.job.source_url);
      if (host) set.add(host);
    }
    return [...set].sort();
  }, [items]);

  const filtered = useMemo(
    () => filterProposals(items, { role, board, minScore }),
    [items, role, board, minScore],
  );

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
    () =>
      sortProposals(
        filtered.filter((p) => NEEDS_YOU.includes(p.status)),
        sort,
      ),
    [filtered, sort],
  );
  const triage = useMemo(
    () =>
      sortProposals(
        filtered.filter((p) => TRIAGE.includes(p.status)),
        sort,
      ),
    [filtered, sort],
  );
  const queued = useMemo(
    () =>
      sortProposals(
        filtered.filter((p) => QUEUED.includes(p.status)),
        sort,
      ),
    [filtered, sort],
  );
  const inFlight = useMemo(
    () =>
      sortProposals(
        filtered.filter((p) => IN_FLIGHT.includes(p.status)),
        sort,
      ),
    [filtered, sort],
  );
  const history = useMemo(() => {
    const list = filtered.filter((p) => HISTORY.includes(p.status));
    const scoped =
      historyStatus === "all"
        ? list
        : list.filter((p) => p.status === historyStatus);
    return sortProposals(scoped, sort);
  }, [filtered, historyStatus, sort]);

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

  const pending =
    actions.transition.isPending ||
    actions.bulk.isPending ||
    actions.remove.isPending;

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col gap-5">
        <FunnelStrip />
        <LoadErrorState
          title="Couldn't load agent proposals."
          detail={(error as Error)?.message}
          retrying={isFetching}
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col gap-5">
        <FunnelStrip />
        <Card>
          <CardContent className="text-muted-foreground py-10 text-center text-sm">
            No agent proposals yet. Proposals appear here when an agent hunt
            files applications for your review.
          </CardContent>
        </Card>
      </div>
    );
  }

  const rowProps = {
    duplicateKeys,
    pending,
    onAccept: (id: string) =>
      actions.transition.mutate({ id, status: "accepted" }),
    onDecline: (id: string) => setDeclineTarget({ mode: "single", id }),
    onDelete: (id: string) => actions.remove.mutate(id),
    selected,
    onToggleSelected: toggleSelected,
  };

  return (
    <div className="flex flex-col gap-6 pb-20">
      <FunnelStrip />

      <div className="flex flex-wrap items-end gap-2">
        <div className="grid gap-1">
          <span className="text-muted-foreground text-xs">Sort</span>
          <Select
            value={sort}
            onValueChange={(v) => setSort((v as SortKey) ?? "score")}
          >
            <SelectTrigger className="h-8 min-w-[9rem]" aria-label="Sort">
              <SelectValue>{SORT_LABELS[sort]}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
                <SelectItem key={key} value={key}>
                  {SORT_LABELS[key]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-1">
          <span className="text-muted-foreground text-xs">Role</span>
          <Select value={role} onValueChange={(v) => setRole(v ?? "all")}>
            <SelectTrigger className="h-8 min-w-[9rem]" aria-label="Role">
              <SelectValue>
                {role === "all" ? "All roles" : role}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All roles</SelectItem>
              {roles.map((r) => (
                <SelectItem key={r} value={r}>
                  {r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-1">
          <span className="text-muted-foreground text-xs">Board</span>
          <Select value={board} onValueChange={(v) => setBoard(v ?? "all")}>
            <SelectTrigger className="h-8 min-w-[10rem]" aria-label="Board">
              <SelectValue>
                {board === "all" ? "All boards" : board}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All boards</SelectItem>
              {boards.map((b) => (
                <SelectItem key={b} value={b}>
                  {b}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-1">
          <span className="text-muted-foreground text-xs">Min score</span>
          <Input
            type="number"
            inputMode="decimal"
            aria-label="Minimum score"
            placeholder="e.g. 50"
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
            className="h-8 w-24"
          />
        </div>
      </div>

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

      <Lane title={`Triage · ${triage.length}`}>
        {dayBatches.length === 0 ? (
          <p className="text-muted-foreground text-sm">Nothing pending triage.</p>
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
                {open
                  ? dayItems.map((p) => (
                      <ProposalRow
                        key={p.id}
                        proposal={p}
                        lane="triage"
                        {...rowProps}
                      />
                    ))
                  : null}
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
        <Lane title={`In flight · ${inFlight.length}`}>
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

      <section className="flex flex-col gap-2">
        <button
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
          History ·{" "}
          {filtered.filter((p) => HISTORY.includes(p.status)).length}
        </button>
        {historyOpen ? (
          <>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="History status">
              {(
                [
                  "all",
                  ...HISTORY,
                ] as const
              ).map((status) => {
                const active = historyStatus === status;
                const label =
                  status === "all" ? "All" : STATUS_LABELS[status];
                return (
                  <button
                    key={status}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setHistoryStatus(status)}
                    className={cn(
                      "inline-flex h-7 items-center rounded-full border px-3 text-xs font-medium",
                      active
                        ? "border-transparent bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-muted",
                    )}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
            {history.length === 0 ? (
              <p className="text-muted-foreground text-sm">No history yet.</p>
            ) : (
              history.map((p) => (
                <ProposalRow
                  key={p.id}
                  proposal={p}
                  lane="history"
                  {...rowProps}
                />
              ))
            )}
          </>
        ) : null}
      </section>

      <BulkBar
        selectedCount={selected.size}
        pending={pending}
        onAccept={() => {
          const ids = [...selected];
          actions.bulk.mutate(
            { ids, status: "accepted" },
            { onSuccess: () => setSelected(new Set()) },
          );
        }}
        onDecline={() => setDeclineTarget({ mode: "bulk" })}
        onClear={() => setSelected(new Set())}
      />

      <DeclineDialog
        open={declineTarget != null}
        onOpenChange={(open) => {
          if (!open) setDeclineTarget(null);
        }}
        pending={pending}
        onConfirm={(reason) => {
          if (!declineTarget) return;
          if (declineTarget.mode === "single") {
            actions.transition.mutate(
              {
                id: declineTarget.id,
                status: "rejected",
                reason,
              },
              { onSuccess: () => setDeclineTarget(null) },
            );
            return;
          }
          const ids = [...selected];
          actions.bulk.mutate(
            { ids, status: "rejected", reason },
            {
              onSuccess: () => {
                setSelected(new Set());
                setDeclineTarget(null);
              },
            },
          );
        }}
      />
    </div>
  );
}

function Lane({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2 overflow-x-auto">
      <h2 className="text-muted-foreground text-xs font-medium uppercase tracking-wide">
        {title}
      </h2>
      {children}
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
  onAccept,
  onDecline,
  onDelete,
  pending,
}: {
  proposal: Proposal;
  lane: LaneKind;
  duplicateKeys: Set<string>;
  selected: Set<string>;
  onToggleSelected: (id: string, next: boolean) => void;
  onAccept: (id: string) => void;
  onDecline: (id: string) => void;
  onDelete: (id: string) => void;
  pending?: boolean;
}) {
  const job = proposal.job;
  const base = chosenBase(proposal);
  const score = chosenScore(proposal);
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
            className="hover:bg-muted/40 flex min-w-0 flex-1 items-center gap-3 rounded-xl p-4 text-left transition-colors"
          >
            <CompanyMonogram name={job.company ?? "?"} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="truncate text-sm font-medium">
                  {job.title ?? "Untitled role"}
                </span>
                {job.disqualifying_for_opt ? (
                  <span
                    className="inline-flex items-center gap-1 text-xs text-amber-600"
                    title="Extraction flagged this posting as disqualifying for OPT"
                  >
                    <AlertTriangle className="size-3.5" aria-hidden="true" />
                    OPT
                  </span>
                ) : null}
                {isDup ? (
                  <span className="inline-flex items-center rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-400">
                    possible duplicate
                  </span>
                ) : null}
              </div>
              <div className="text-muted-foreground truncate text-xs">
                {[job.company, job.location, job.work_mode]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
            </div>
            {base ? (
              <span className="text-muted-foreground hidden shrink-0 rounded-full bg-muted/70 px-2 py-0.5 text-xs sm:inline-flex">
                {baseResumeLabel(base)}
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
                  disabled={pending}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onAccept(proposal.id);
                  }}
                />
                <IconButton
                  label="Skip"
                  icon={<X />}
                  disabled={pending}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onDecline(proposal.id);
                  }}
                />
              </>
            ) : null}
            {showDecline ? (
              <IconButton
                label="Skip"
                icon={<X />}
                disabled={pending}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onDecline(proposal.id);
                }}
              />
            ) : null}
            {canDelete ? (
              <IconButton
                label="Delete proposal"
                icon={<Trash2 />}
                disabled={pending}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onDelete(proposal.id);
                }}
              />
            ) : null}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

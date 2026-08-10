"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  EllipsisVertical,
  FilePlus2,
  Inbox,
  Search,
  SendHorizontal,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { CompanyMonogram } from "@/components/company-monogram";
import { EmptyState, TableFrame } from "@/components/empty-state";
import { IconButton } from "@/components/icon-button";
import { GettingStartedCard } from "@/components/setup/getting-started-card";
import {
  SourceToggle,
  type SourceFilter,
} from "@/components/source-toggle";
import { SavedJobChip, StatusChip, statusLabel } from "@/components/status-chip";
import { useConfirm } from "@/components/confirm-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
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
import { apiFetch, promoteJobToAgentQueue } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  APPLICATION_STATUSES,
  baseResumeLabel,
  type ApplicationStatus,
  type ApplicationSummary,
  type Job,
} from "@/lib/types";
import { PageHeader, PageShell } from "@/components/page-shell";

// "saved" is the synthetic no-application state (a captured job you haven't
// started on) — one name everywhere, not aspiring/not-applied/jobs.
// Agent-lane filters cover proposal_status on saved jobs. Keys stay distinct
// from APPLICATION_STATUSES — proposal "accepted" (Queued) must not collide
// with application "accepted" (Offer), and proposal "rejected" (you passed on
// the agent's proposal) must not read like application "rejected" (they passed
// on you), hence "skipped". It absorbs expired proposals too: either way you
// are not pursuing that job. The row chip still says Expired for that state.
const AGENT_LANE_FILTERS = [
  "proposed",
  "queued",
  "needs_you",
  "skipped",
] as const;
// The three dropdown groups, in render order — FILTERS is derived from them so
// a new key can never type-check and filter rows yet never appear as an option.
const TOP_FILTERS = ["all", "saved"] as const;
const FILTERS = [
  ...TOP_FILTERS,
  ...APPLICATION_STATUSES,
  ...AGENT_LANE_FILTERS,
] as const;
type Filter = (typeof FILTERS)[number];
type AgentLaneFilter = (typeof AGENT_LANE_FILTERS)[number];

const AGENT_LANE_LABELS: Record<AgentLaneFilter, string> = {
  proposed: "Proposed",
  queued: "Queued",
  needs_you: "Needs you",
  skipped: "Skipped",
};

function filterLabel(value: Filter): string {
  if (value === "all") return "All";
  if (value === "saved") return "Saved";
  if ((AGENT_LANE_FILTERS as readonly string[]).includes(value)) {
    return AGENT_LANE_LABELS[value as AgentLaneFilter];
  }
  return statusLabel(value);
}

// Session-scoped memory: coming back via the sidebar link (no URL params)
// restores the last filter/source instead of resetting to All, and the job
// page's prev/next arrows walk the tracker's last visible row order.
const FILTER_STORE_KEY = "cs-tracker-filter";
const SOURCE_STORE_KEY = "cs-tracker-source";
const SEQUENCE_STORE_KEY = "cs-tracker-seq";

function storedValue(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function storeValue(key: string, value: string) {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    // Session memory is a convenience — never let storage failures break the page.
  }
}

type SortKey = "created_at" | "role" | "status" | "applied_at";
type SortDir = "asc" | "desc";

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
  if (ps === "rejected" || ps === "expired") return "skipped";
  if (ps === "needs_decision" || ps === "needs_human") return "needs_you";
  return "saved";
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  return value.slice(0, 10);
}

function rowCompany(r: Row): string {
  return (r.kind === "saved" ? r.job.company : r.app.job_company) ?? "";
}

function rowTitle(r: Row): string {
  return (r.kind === "saved" ? r.job.title : r.app.job_title) ?? "";
}

function ApplicationsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const qc = useQueryClient();
  const confirm = useConfirm();
  const [filter, setFilter] = useState<Filter>(() => {
    const v = searchParams.get("status") ?? storedValue(FILTER_STORE_KEY);
    return v && (FILTERS as readonly string[]).includes(v)
      ? (v as Filter)
      : "all";
  });
  const [source, setSource] = useState<SourceFilter>(() => {
    const v = searchParams.get("source") ?? storedValue(SOURCE_STORE_KEY);
    return v === "user" || v === "agent" ? v : "all";
  });
  const [q, setQ] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("created_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  // Two queries total: the summary list carries job fields server-side now.
  // One unfiltered fetch also gives the filter chips their counts for free.
  const apps = useQuery({
    queryKey: ["applications"],
    queryFn: () => apiFetch<ApplicationSummary[]>("/api/applications?limit=500"),
  });
  const savedJobs = useQuery({
    queryKey: ["jobs", "without-application"],
    queryFn: () => apiFetch<Job[]>("/api/jobs?without_application=true&limit=500"),
  });

  const patchStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: ApplicationStatus }) =>
      apiFetch<unknown>(`/api/applications/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ["applications"] });
      const jobId = apps.data?.find((a) => a.id === id)?.job_id;
      if (jobId) qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const deleteApp = useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/api/applications/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Application deleted");
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // Promote a scored-but-unproposed capture into the agent queue: file a
  // proposal from the job's stored base scores, then straight to accepted —
  // this click IS the user's triage decision. The escape hatch for good
  // captures that missed the hunt's per-run proposal cap.
  const promoteJob = useMutation({
    mutationFn: (jobId: string) => promoteJobToAgentQueue(jobId),
    onSuccess: () => {
      toast.success("Queued for the next apply run");
      qc.invalidateQueries({ queryKey: ["jobs", "without-application"] });
      qc.invalidateQueries({ queryKey: ["proposals"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const deleteJob = useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/api/jobs/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Job deleted");
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["applications"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const allRows = useMemo<Row[]>(() => {
    const appRows: Row[] = (apps.data ?? []).map((app) => ({
      kind: "application",
      app,
    }));
    // Saved lane: hide agent-captured hunt inventory unless toggle is Agent
    // (proposals page owns that inventory when source is All/You).
    const savedRows: Row[] = (savedJobs.data ?? [])
      .filter((job) =>
        source === "agent" ? job.source === "agent" : job.source !== "agent",
      )
      .map((job) => ({ kind: "saved" as const, job }));
    return [...savedRows, ...appRows];
  }, [apps.data, savedJobs.data, source]);

  // Source filter before counts so chip totals match what is visible.
  const sourceScopedRows = useMemo(() => {
    if (source === "all") return allRows;
    return allRows.filter(
      (r) => r.kind === "saved" || r.app.source === source,
    );
  }, [allRows, source]);

  const counts = useMemo(() => {
    const map = new Map<Filter, number>();
    map.set("all", sourceScopedRows.length);
    for (const r of sourceScopedRows) {
      const key = rowFilterKey(r);
      map.set(key, (map.get(key) ?? 0) + 1);
    }
    return map;
  }, [sourceScopedRows]);

  // Empty buckets are noise — drop them, except "all" and whatever is active
  // (an option must never vanish out from under the user who picked it).
  const visibleFilters = (group: readonly Filter[]) =>
    group.filter((f) => (counts.get(f) ?? 0) > 0 || f === "all" || f === filter);
  const topOptions = visibleFilters(TOP_FILTERS);
  const appOptions = visibleFilters(APPLICATION_STATUSES);
  const laneOptions = visibleFilters(AGENT_LANE_FILTERS);
  const filterOption = (f: Filter) => (
    <SelectItem key={f} value={f}>
      {`${filterLabel(f)} · ${counts.get(f) ?? 0}`}
    </SelectItem>
  );

  const filtered = useMemo(() => {
    let list = sourceScopedRows;
    if (filter !== "all") {
      list = list.filter((r) => rowFilterKey(r) === filter);
    }

    const needle = q.trim().toLowerCase();
    if (needle) {
      list = list.filter((r) =>
        `${rowCompany(r)} ${rowTitle(r)}`.toLowerCase().includes(needle),
      );
    }

    const dir = sortDir === "asc" ? 1 : -1;
    const pick = (r: Row): string => {
      switch (sortKey) {
        case "role":
          return rowTitle(r).toLowerCase();
        case "status":
          return rowFilterKey(r);
        case "applied_at":
          return r.kind === "saved" ? "" : (r.app.applied_at ?? "");
        case "created_at":
        default:
          return r.kind === "saved" ? r.job.created_at : r.app.created_at;
      }
    };
    return [...list].sort((a, b) => {
      const av = pick(a);
      const bv = pick(b);
      if (av === bv) return 0;
      return av < bv ? -dir : dir;
    });
  }, [sourceScopedRows, filter, q, sortKey, sortDir]);

  const loading = apps.isLoading || savedJobs.isLoading;

  const writeUrl = (nextFilter: Filter, nextSource: SourceFilter) => {
    const params = new URLSearchParams();
    if (nextFilter !== "all") params.set("status", nextFilter);
    if (nextSource !== "all") params.set("source", nextSource);
    const qs = params.toString();
    router.replace(qs ? `/applications?${qs}` : "/applications");
  };

  const setFilterAndUrl = (next: Filter) => {
    setFilter(next);
    storeValue(FILTER_STORE_KEY, next);
    writeUrl(next, source);
  };

  const setSourceAndUrl = (next: SourceFilter) => {
    setSource(next);
    storeValue(SOURCE_STORE_KEY, next);
    writeUrl(filter, next);
  };

  // Record the visible row order (job ids) so the job page's prev/next arrows
  // can walk exactly what the user was looking at, filters and sort included.
  useEffect(() => {
    if (loading) return;
    storeValue(
      SEQUENCE_STORE_KEY,
      JSON.stringify(
        filtered.map((r) => (r.kind === "saved" ? r.job.id : r.app.job_id)),
      ),
    );
  }, [filtered, loading]);

  const header = (key: SortKey, label: string, className?: string) => {
    const active = sortKey === key;
    return (
      <TableHead
        aria-sort={
          active ? (sortDir === "asc" ? "ascending" : "descending") : undefined
        }
        className={cn("cursor-pointer select-none", className)}
        onClick={() => {
          if (active) setSortDir(sortDir === "asc" ? "desc" : "asc");
          else {
            setSortKey(key);
            setSortDir("desc");
          }
        }}
      >
        {label}
        {active && (
          <span className="text-muted-foreground ml-1 text-[10px]">
            {sortDir === "asc" ? "▲" : "▼"}
          </span>
        )}
      </TableHead>
    );
  };

  return (
    <PageShell>
      <PageHeader
        title="Applications"
        subtitle="Every job you've captured, from saved to signed."
        actions={
          <Button
            nativeButton={false}
            render={
              <Link href="/new">
                <FilePlus2 className="size-4" />
                New application
              </Link>
            }
          />
        }
      />

      <div className="flex flex-col gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="text-muted-foreground pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2" />
          <Input
            aria-label="Search applications"
            placeholder="Search company or role…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="h-10 rounded-full pl-10"
          />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Select
            value={filter}
            onValueChange={(v) => {
              if (v && (FILTERS as readonly string[]).includes(v)) {
                setFilterAndUrl(v as Filter);
              }
            }}
          >
            <SelectTrigger
              className="h-8 min-w-[11rem] rounded-full"
              aria-label="Filter by status"
            >
              <SelectValue>
                {`${filterLabel(filter)} · ${counts.get(filter) ?? 0}`}
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
                  <SelectLabel>Agent lane</SelectLabel>
                  {laneOptions.map(filterOption)}
                </SelectGroup>
              ) : null}
            </SelectContent>
          </Select>
          <SourceToggle
            className="ml-auto"
            value={source}
            onChange={setSourceAndUrl}
          />
        </div>
      </div>

      {loading ? (
        <div className="space-y-2">
          <Skeleton className="animate-shimmer h-12 w-full" />
          <Skeleton className="animate-shimmer h-12 w-full" />
          <Skeleton className="animate-shimmer h-12 w-full" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="space-y-5">
          {allRows.length === 0 ? <GettingStartedCard /> : null}
          <EmptyState
            icon={Inbox}
            title={
              allRows.length === 0
                ? "No applications yet"
                : "Nothing matches this filter"
            }
            description={
              allRows.length === 0
                ? "Capture a job description to get started."
                : "Try a different status or clear the search."
            }
            action={
              allRows.length === 0 ? (
                <Button
                  variant="outline"
                  nativeButton={false}
                  render={
                    <Link href="/new">
                      <FilePlus2 className="size-4" />
                      New application
                    </Link>
                  }
                />
              ) : null
            }
          />
        </div>
      ) : (
        <TableFrame>
          {/* min-w engages Table's own overflow-x-auto container. Without it the
              table shrinks to whatever width is left — 462px at 768px, where the
              sidebar has not yet collapsed — and because the layout is fixed the
              status chip cannot widen its column, so it paints over the Applied
              date instead. */}
          <Table className="min-w-[52rem] table-fixed">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                {header("role", "Role", "w-[42%]")}
                <TableHead className="w-[16%]">Base</TableHead>
                {header("status", "Status", "w-[14%]")}
                {header("applied_at", "Applied", "w-[12%]")}
                {header("created_at", "Added", "w-[12%]")}
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((r) => {
                const rowKey =
                  r.kind === "saved" ? `job-${r.job.id}` : `app-${r.app.id}`;
                const href =
                  r.kind === "saved"
                    ? `/jobs/${r.job.id}`
                    : `/jobs/${r.app.job_id}`;
                const company = rowCompany(r) || "—";
                const title = rowTitle(r) || "Untitled role";

                return (
                  <TableRow
                    key={rowKey}
                    className="group cursor-pointer"
                    // The row was click-only: no tabIndex, no key handler, no
                    // role. A keyboard user could reach the status chip and the
                    // overflow menu inside the row but had no way to open the
                    // job it points at. Proposals solves the identical case
                    // with a real <Link>; a table row cannot contain one
                    // without breaking the row semantics, so it takes the
                    // link role and the two keys that role implies.
                    role="link"
                    tabIndex={0}
                    onClick={() => router.push(href)}
                    onKeyDown={(e) => {
                      if (e.target !== e.currentTarget) return;
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        router.push(href);
                      }
                    }}
                  >
                    <TableCell className="max-w-0 whitespace-normal py-2.5">
                      <div className="flex min-w-0 items-center gap-3">
                        <CompanyMonogram name={company} className="shrink-0" />
                        <div className="min-w-0 flex-1 overflow-hidden">
                          <p className="flex min-w-0 items-center gap-1.5 text-sm font-medium">
                            <span className="truncate">{company}</span>
                            {(r.kind === "saved" ? r.job.source : r.app.source) ===
                            "agent" ? (
                              <Bot
                                className="text-muted-foreground size-3.5 shrink-0"
                                aria-label="Found by agent"
                              />
                            ) : null}
                          </p>
                          <p className="text-muted-foreground truncate text-xs">
                            {title}
                            {r.kind === "application" && r.app.job_location
                              ? ` · ${r.app.job_location}`
                              : ""}
                          </p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground max-w-0 truncate text-xs">
                      {r.kind === "saved" ? "—" : baseResumeLabel(r.app.base_resume)}
                    </TableCell>
                    <TableCell>
                      {r.kind === "saved" ? (
                        <SavedJobChip proposalStatus={r.job.proposal_status} />
                      ) : (
                        <StatusChip
                          status={r.app.status}
                          pending={
                            patchStatus.isPending &&
                            patchStatus.variables?.id === r.app.id
                          }
                          onSelect={(status) =>
                            patchStatus.mutate({ id: r.app.id, status })
                          }
                        />
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs tabular-nums">
                      {r.kind === "saved" ? "—" : formatDate(r.app.applied_at)}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs tabular-nums">
                      {formatDate(
                        r.kind === "saved" ? r.job.created_at : r.app.created_at,
                      )}
                    </TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1">
                        {r.kind === "saved" && !r.job.proposal_status ? (
                          <IconButton
                            label="Queue for agent apply"
                            icon={<SendHorizontal />}
                            className="opacity-0 transition-opacity duration-150 group-hover:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-100"
                            onClick={(e) => {
                              e.stopPropagation();
                              promoteJob.mutate(r.job.id);
                            }}
                            disabled={promoteJob.isPending}
                          />
                        ) : null}
                        <DropdownMenu>
                          <DropdownMenuTrigger
                            render={
                              <Button
                                variant="ghost"
                                size="icon-sm"
                                aria-label="More actions"
                                className="opacity-0 transition-opacity duration-150 group-hover:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-100"
                              >
                                <EllipsisVertical className="size-4" />
                              </Button>
                            }
                          />
                          <DropdownMenuContent align="end">
                            {r.kind === "saved" ? (
                              <DropdownMenuItem
                                variant="destructive"
                                onClick={async () => {
                                  const ok = await confirm({
                                    title: "Delete this job?",
                                    description: `${company} · ${title}. The job description and extracted metadata will be removed.`,
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
                                onClick={async () => {
                                  const ok = await confirm({
                                    title: "Delete this application?",
                                    description: `${company} · ${title}. Its tailored resume, Q&A history, and rendered PDF will be removed. The job stays saved.`,
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
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableFrame>
      )}
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

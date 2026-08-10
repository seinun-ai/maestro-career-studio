"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CalendarDays,
  Check,
  ChevronDown,
  Pencil,
  Send,
  Trash2,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { DocumentsPanel } from "@/components/career/documents-panel";
import { NotesEditor } from "@/components/career/notes-editor";
import { PointsList } from "@/components/career/points-list";
import { SendToResumeDialog } from "@/components/career/send-to-resume-dialog";
import { TimelinePanel } from "@/components/career/timeline-panel";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PageShell } from "@/components/page-shell";
import { Skeleton } from "@/components/ui/skeleton";
import { deleteKbEntity, getKbEntity, patchKbEntity } from "@/lib/api";
import type {
  KBEntityDetail as KBEntityDetailType,
  KBEntityKind,
  KBEntityPatch,
  KBEntityStatus,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUSES: { value: KBEntityStatus; label: string; chip: string; dot: string }[] = [
  {
    value: "ongoing",
    label: "Ongoing",
    chip: "bg-blue-600/10 text-blue-700 dark:bg-blue-400/15 dark:text-blue-300",
    dot: "bg-blue-600 dark:bg-blue-400",
  },
  {
    value: "completed",
    label: "Completed",
    chip: "bg-emerald-600/10 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300",
    dot: "bg-emerald-600 dark:bg-emerald-400",
  },
  {
    value: "archived",
    label: "Archived",
    chip: "bg-muted text-muted-foreground",
    dot: "bg-muted-foreground/50",
  },
];

const KIND_LABELS: Record<KBEntityKind, string> = {
  experience: "Experience",
  project: "Project",
  education: "Education",
  certification: "Certification",
};

export function EntityDetail({ entityId }: { entityId: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const [sendOpen, setSendOpen] = useState(false);
  const entity = useQuery({
    queryKey: ["kb", "entity", entityId],
    queryFn: () => getKbEntity(entityId),
  });

  const remove = useMutation({
    mutationFn: () => deleteKbEntity(entityId),
    onSuccess: () => {
      toast.success("Career item deleted");
      void queryClient.invalidateQueries({ queryKey: ["kb", "entities"] });
      void queryClient.invalidateQueries({ queryKey: ["kb", "drafts"] });
      router.push("/career");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const requestDelete = async () => {
    if (!entity.data) return;
    const accepted = await confirm({
      title: `Delete ${entity.data.title}?`,
      description:
        "This permanently removes the entity, its points, source documents, and provenance history.",
      confirmLabel: "Delete career item",
      destructive: true,
    });
    if (accepted) remove.mutate();
  };

  if (entity.isLoading) {
    return (
      <PageShell>
        <Skeleton className="h-8 w-36" />
        <Skeleton className="h-44 w-full rounded-2xl" />
        <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(18rem,1fr)]">
          <Skeleton className="h-96 w-full rounded-2xl" />
          <Skeleton className="h-96 w-full rounded-2xl" />
        </div>
      </PageShell>
    );
  }

  if (entity.error || !entity.data) {
    return (
      <PageShell>
        <div role="alert" className="rounded-2xl bg-destructive/10 p-5">
          <p className="font-medium">Couldn&apos;t load this career item.</p>
          <p className="text-muted-foreground mt-1 text-sm">
            {entity.error?.message ?? "The item may no longer exist."}
          </p>
          <div className="mt-4 flex gap-2">
            <Button className="rounded-full" variant="secondary" onClick={() => void entity.refetch()}>
              Try again
            </Button>
            <Button
              className="rounded-full"
              variant="ghost"
              nativeButton={false}
              render={<Link href="/career">Back to Career KB</Link>}
            />
          </div>
        </div>
      </PageShell>
    );
  }

  return (
    <>
      <PageShell>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button
            className="rounded-full"
            variant="ghost"
            size="sm"
            nativeButton={false}
            render={
              <Link href="/career">
                <ArrowLeft aria-hidden="true" /> Career KB
              </Link>
            }
          />
          <div className="flex items-center gap-2">
            <Button className="rounded-full px-4" onClick={() => setSendOpen(true)}>
              <Send aria-hidden="true" /> Send to resume
            </Button>
            <Button
              className="rounded-full"
              variant="ghost"
              onClick={() => void requestDelete()}
              disabled={remove.isPending}
            >
              <Trash2 aria-hidden="true" />
              {remove.isPending ? "Deleting…" : "Delete"}
            </Button>
          </div>
        </div>

        <EntityHeader key={entity.data.id} entity={entity.data} />

        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(19rem,1fr)]">
          <div className="space-y-6">
            <PointsList entityId={entityId} points={entity.data.points} />
            <NotesEditor entityId={entityId} notes={entity.data.notes ?? ""} />
          </div>
          <div className="space-y-6">
            <DocumentsPanel entityId={entityId} documents={entity.data.documents} />
            <TimelinePanel events={entity.data.timeline} />
          </div>
        </div>
      </PageShell>
      {sendOpen ? (
        <SendToResumeDialog
          open={sendOpen}
          onOpenChange={setSendOpen}
          entity={entity.data}
        />
      ) : null}
    </>
  );
}

type SaveVariables = {
  payload: KBEntityPatch;
  success: string;
  exitEdit?: boolean;
};

function EntityHeader({ entity }: { entity: KBEntityDetailType }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(entity.title);
  const [org, setOrg] = useState(entity.org ?? "");
  const [startDate, setStartDate] = useState(entity.start_date ?? "");
  const [endDate, setEndDate] = useState(entity.end_date ?? "");
  const [status, setStatus] = useState<KBEntityStatus>(entity.status);

  const reset = () => {
    setTitle(entity.title);
    setOrg(entity.org ?? "");
    setStartDate(entity.start_date ?? "");
    setEndDate(entity.end_date ?? "");
    setStatus(entity.status);
    setEditing(false);
  };

  const save = useMutation({
    mutationFn: ({ payload }: SaveVariables) => patchKbEntity(entity.id, payload),
    onSuccess: (updated, variables) => {
      queryClient.setQueryData(["kb", "entity", entity.id], updated);
      void queryClient.invalidateQueries({ queryKey: ["kb", "entities"] });
      void queryClient.invalidateQueries({ queryKey: ["kb", "drafts"] });
      setTitle(updated.title);
      setOrg(updated.org ?? "");
      setStartDate(updated.start_date ?? "");
      setEndDate(updated.end_date ?? "");
      setStatus(updated.status);
      if (variables.exitEdit) setEditing(false);
      toast.success(variables.success);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextTitle = title.trim();
    if (!nextTitle) return;
    save.mutate({
      payload: {
        title: nextTitle,
        org: org.trim() || null,
        start_date: startDate.trim() || null,
        end_date: endDate.trim() || null,
        status,
      },
      success: "Career item saved",
      exitEdit: true,
    });
  };

  const dateRange = [entity.start_date, entity.end_date].filter(Boolean).join(" – ");

  if (editing) {
    return (
      <section className="animate-fade-rise rounded-2xl bg-muted/45 p-5 sm:p-6">
        <form
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={submit}
        >
          <div className="grid gap-1.5 sm:col-span-2">
            <Label htmlFor="kb-entity-title">Title</Label>
            <Input
              id="kb-entity-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              disabled={save.isPending}
              autoFocus
              required
            />
          </div>
          <div className="grid gap-1.5 sm:col-span-2">
            <Label htmlFor="kb-entity-org">
              Organization <span className="text-muted-foreground">· optional</span>
            </Label>
            <Input
              id="kb-entity-org"
              value={org}
              onChange={(event) => setOrg(event.target.value)}
              placeholder="Acme Labs"
              disabled={save.isPending}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="kb-entity-start">
              Start date <span className="text-muted-foreground">· optional</span>
            </Label>
            <Input
              id="kb-entity-start"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
              placeholder="Jan 2025"
              disabled={save.isPending}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="kb-entity-end">
              End date <span className="text-muted-foreground">· optional</span>
            </Label>
            <Input
              id="kb-entity-end"
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
              placeholder="Present"
              disabled={save.isPending}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="kb-entity-status">Status</Label>
            <Select
              value={status}
              onValueChange={(value) => value && setStatus(value as KBEntityStatus)}
              disabled={save.isPending}
            >
              <SelectTrigger id="kb-entity-status" className="w-full">
                <SelectValue>{statusLabel(status)}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {STATUSES.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-end justify-end gap-2">
            <Button className="rounded-full" type="button" variant="ghost" onClick={reset} disabled={save.isPending}>
              <X aria-hidden="true" /> Cancel
            </Button>
            <Button className="rounded-full px-4" type="submit" disabled={!title.trim() || save.isPending}>
              {save.isPending ? "Saving…" : "Save details"}
            </Button>
          </div>
        </form>
      </section>
    );
  }

  return (
    <section className="group animate-fade-rise rounded-2xl bg-muted/45 px-5 py-6 sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="bg-background/80 text-muted-foreground inline-flex h-6 items-center rounded-full px-2.5 text-xs font-medium">
              {KIND_LABELS[entity.kind]}
            </span>
            <EntityStatusChip
              status={entity.status}
              pending={save.isPending}
              onSelect={(nextStatus) =>
                save.mutate({
                  payload: { status: nextStatus },
                  success: `Status changed to ${statusLabel(nextStatus).toLowerCase()}`,
                })
              }
            />
          </div>
          <h1 className="mt-3 text-[22px] font-medium tracking-tight">{entity.title}</h1>
          <div className="text-muted-foreground mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            {entity.org ? <span>{entity.org}</span> : null}
            {dateRange ? (
              <span className="inline-flex items-center gap-1.5">
                <CalendarDays className="size-3.5" aria-hidden="true" /> {dateRange}
              </span>
            ) : null}
            {!entity.org && !dateRange ? <span>No organization or dates added</span> : null}
          </div>
        </div>
        <Button
          className="rounded-full opacity-0 transition-opacity duration-150 group-hover:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-100"
          size="sm"
          variant="ghost"
          onClick={() => setEditing(true)}
        >
          <Pencil aria-hidden="true" /> Edit details
        </Button>
      </div>
    </section>
  );
}

function EntityStatusChip({
  status,
  pending,
  onSelect,
}: {
  status: KBEntityStatus;
  pending: boolean;
  onSelect: (status: KBEntityStatus) => void;
}) {
  const current = STATUSES.find((item) => item.value === status) ?? STATUSES[0];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <button
            type="button"
            aria-label={`Status: ${current.label}. Change status`}
            disabled={pending}
            className={cn(
              "inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium transition-[transform,box-shadow] duration-150 ease-out hover:shadow-sm active:scale-[0.97] focus-visible:outline-2 focus-visible:outline-ring/60 disabled:opacity-50",
              current.chip,
            )}
          >
            <span className={cn("size-1.5 rounded-full", current.dot)} />
            {pending ? "Saving…" : current.label}
            <ChevronDown className="size-3 opacity-50" aria-hidden="true" />
          </button>
        }
      />
      <DropdownMenuContent align="start" className="w-40">
        {STATUSES.map((item) => (
          <DropdownMenuItem
            key={item.value}
            onClick={() => {
              if (item.value !== status) onSelect(item.value);
            }}
          >
            <span className={cn("size-2 rounded-full", item.dot)} />
            <span className="flex-1">{item.label}</span>
            {item.value === status ? <Check className="text-muted-foreground size-3.5" /> : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function statusLabel(status: KBEntityStatus) {
  return STATUSES.find((item) => item.value === status)?.label ?? status;
}

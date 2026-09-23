"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal } from "lucide-react";
import { toast } from "sonner";

import { BaseResumeGallery } from "@/components/base-resumes/base-resume-gallery";
import { FirstRunImportCard } from "@/components/career/first-run-import-card";
import { LoadErrorState } from "@/components/load-error-state";
import { useBaseResumes } from "@/hooks/use-base-resume-label";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { NewBaseResumeDialog } from "@/components/base-resumes/new-base-resume-dialog";
import { apiFetch, apiUrlForBrowserPdf } from "@/lib/api";
import { finalFocusOn, focusIfDropped, focusSuccessor } from "@/lib/focus";
import { isLoadFailure } from "@/lib/query-state";
import { notifyRenderNote } from "@/lib/render-note";
import { uniqueSlug } from "@/lib/slug";
import type {
  BaseResumeDetail,
  BaseResumeSummary,
} from "@/lib/types";
import { PageHeader, PageShell } from "@/components/page-shell";


export default function BaseResumesListPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [showArchived, setShowArchived] = useState(false);
  const resumes = useBaseResumes(showArchived);

  const [createOpen, setCreateOpen] = useState(false);

  const [dupOpen, setDupOpen] = useState(false);
  const [dupSource, setDupSource] = useState<string | null>(null);
  const [dupDisplay, setDupDisplay] = useState("");

  const [deleteTarget, setDeleteTarget] = useState<BaseResumeSummary | null>(
    null,
  );
  // A delete removes the card and its ⋯: once confirmed, the dialog returns to
  // the next card (else the previous, else the list), read when Delete was
  // chosen. Cancel returns to ⋯ as before.
  const deleteNext = useRef<() => HTMLElement | null>(() => null);
  const afterDelete = useRef<(() => HTMLElement | null) | null>(null);
  const visibleResumes = resumes.data ?? [];

  const invalidate = () => qc.invalidateQueries({ queryKey: ["base-resumes"] });

  const duplicate = useMutation({
    mutationFn: () => {
      if (!dupSource) throw new Error("missing source slug");
      return apiFetch<BaseResumeDetail>(
        `/api/base-resumes/${dupSource}/duplicate`,
        {
          method: "POST",
          body: JSON.stringify({
            new_slug: uniqueSlug(dupDisplay || `${dupSource} copy`, (resumes.data ?? []).map((r) => r.slug)),
            new_display_name: dupDisplay || null,
          }),
        },
      );
    },
    onSuccess: (created) => {
      setDupOpen(false);
      setDupSource(null);
      setDupDisplay("");
      invalidate();
      notifyRenderNote(created);
      router.push(`/base-resumes/${created.slug}`);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const del = useMutation({
    mutationFn: (slug: string) =>
      apiFetch<void>(`/api/base-resumes/${slug}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Deleted");
      afterDelete.current = deleteNext.current;
      setDeleteTarget(null);
      invalidate();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const archive = useMutation({
    mutationFn: ({ slug, archived }: { slug: string; archived: boolean }) =>
      apiFetch<BaseResumeDetail>(
        `/api/base-resumes/${slug}/${archived ? "unarchive" : "archive"}`,
        { method: "POST" },
      ),
    onSuccess: (_data, vars) => {
      toast.success(vars.archived ? "Restored" : "Archived");
      invalidate();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  return (
    <PageShell>
      <PageHeader
        title="Base Resumes"
        subtitle="One source of truth per career track. Edits auto-render a fresh PDF."
        actions={
          <>
            <label className="text-muted-foreground mr-2 flex items-center gap-2 text-sm">
              <Switch
                aria-label="Show archived base resumes"
                checked={showArchived}
                onCheckedChange={setShowArchived}
              />
              Show archived
            </label>
            {/* Sentence case, like every other "new X" in the app. */}
            <Button onClick={() => setCreateOpen(true)}>New base resume</Button>
          </>
        }
      />

      <FirstRunImportCard />

      {isLoadFailure(resumes) ? (
        <LoadErrorState
          title="Couldn't load your base resumes."
          detail={(resumes.error as Error)?.message}
          retrying={resumes.isFetching}
          onRetry={() => void resumes.refetch()}
        />
      ) : resumes.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      ) : (
        // Where focus lands when archiving removes the last card.
        <section aria-label="Your base resumes" tabIndex={-1} className="flex flex-col gap-4 outline-none">
          {visibleResumes.length > 0 ? (
            <BaseResumeGallery
              resumes={visibleResumes}
              href={(r) => `/base-resumes/${r.slug}`}
              renderActions={(r) => (
                <CardMenu
                  resume={r}
                  hidesArchived={!showArchived}
                  onDuplicate={() => {
                    setDupSource(r.slug);
                    setDupDisplay(`${r.display_name ?? r.slug} (copy)`);
                    setDupOpen(true);
                  }}
                  onToggleArchive={() =>
                    archive.mutate({
                      slug: r.slug,
                      archived: !!r.archived_at,
                    })
                  }
                  onDelete={(next) => {
                    deleteNext.current = next;
                    setDeleteTarget(r);
                  }}
                />
              )}
            />
          ) : (
            <p className="text-muted-foreground text-sm">
              No career-track resumes yet.
            </p>
          )}
        </section>
      )}

      <NewBaseResumeDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        existingResumes={resumes.data ?? []}
      />

      <Dialog open={dupOpen} onOpenChange={setDupOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Duplicate {dupSource}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-1.5">
            <Label htmlFor="dup_display">New name</Label>
            <Input
              id="dup_display"
              placeholder="e.g. Data Scientist (1 page)"
              value={dupDisplay}
              onChange={(e) => setDupDisplay(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDupOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => duplicate.mutate()}
              disabled={!dupDisplay.trim() || duplicate.isPending}
            >
              {duplicate.isPending ? "Copying…" : "Duplicate"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
      >
        <DialogContent
          finalFocus={() => {
            const back = afterDelete.current;
            afterDelete.current = null;
            return back ? finalFocusOn(back()) : true;
          }}
        >
          <DialogHeader>
            <DialogTitle>Delete {deleteTarget?.slug}?</DialogTitle>
          </DialogHeader>
          <p className="text-muted-foreground text-sm">
            This removes the resume, its rendered PDF, and the JSON file. This
            can&apos;t be undone.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteTarget && del.mutate(deleteTarget.slug)}
              disabled={del.isPending}
              // Disables itself while deleting: a disabled <button> drops focus.
              focusableWhenDisabled
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
            >
              {del.isPending ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}

/**
 * A card's ⋯ menu. Archive (with archived cards hidden) removes the card and
 * this trigger with it, so when the menu's popup goes, a focus it dropped moves
 * to the next card, else the previous one, else the list. Read at the popup's
 * close, not after the refetch: the refetch can land first, and then this menu
 * unmounts with its card. The menu moves focus itself (a microtask after the
 * unmount) because Base UI 1.4.1 reads a function `finalFocus` after a pointer
 * close but does not apply it. Every close returns `false` to Base UI: an
 * overlay an item opened (Duplicate, Delete) keeps its initial focus, and the
 * `DropdownMenu` primitive still moves any other dropped focus back to ⋯.
 */
function CardMenu({
  resume,
  hidesArchived,
  onDuplicate,
  onToggleArchive,
  onDelete,
}: {
  resume: BaseResumeSummary;
  hidesArchived: boolean;
  onDuplicate: () => void;
  onToggleArchive: () => void;
  /** Gets where focus goes if the delete is confirmed: this card is gone by then. */
  onDelete: (next: () => HTMLElement | null) => void;
}) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const leaving = useRef<(() => HTMLElement | null) | null>(null);
  const name = resume.display_name ?? resume.slug;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button ref={triggerRef} size="icon-sm" variant="ghost" aria-label={`Actions for ${name}`}>
            <MoreHorizontal className="size-4" />
          </Button>
        }
      />
      <DropdownMenuContent
        align="end"
        finalFocus={() => {
          const back = leaving.current;
          leaving.current = null;
          if (back) queueMicrotask(() => focusIfDropped(back()));
          return false;
        }}
      >
        <DropdownMenuItem onClick={onDuplicate}>Duplicate</DropdownMenuItem>
        <DropdownMenuItem
          disabled={!resume.pdf_rendered_at}
          render={
            <a
              href={apiUrlForBrowserPdf(`/api/base-resumes/${resume.slug}/pdf`)}
              download={`${name.replace(/[^A-Za-z0-9]+/g, "_")}.pdf`}
            >
              Download PDF
            </a>
          }
        />
        <DropdownMenuItem
          onClick={() => {
            if (hidesArchived && !resume.archived_at)
              leaving.current = focusSuccessor(triggerRef.current?.closest('[data-slot="card"]'));
            onToggleArchive();
          }}
        >
          {resume.archived_at ? "Unarchive" : "Archive"}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          variant="destructive"
          onClick={() => onDelete(focusSuccessor(triggerRef.current?.closest('[data-slot="card"]')))}
        >
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

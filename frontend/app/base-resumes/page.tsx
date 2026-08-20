"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal } from "lucide-react";
import { toast } from "sonner";

import { BaseResumeGallery } from "@/components/base-resumes/base-resume-gallery";
import { FirstRunImportCard } from "@/components/career/first-run-import-card";
import { LoadErrorState } from "@/components/load-error-state";
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
  const resumes = useQuery({
    queryKey: ["base-resumes", showArchived],
    queryFn: () =>
      apiFetch<BaseResumeSummary[]>(
        `/api/base-resumes${showArchived ? "?include_archived=true" : ""}`,
      ),
  });

  const [createOpen, setCreateOpen] = useState(false);

  const [dupOpen, setDupOpen] = useState(false);
  const [dupSource, setDupSource] = useState<string | null>(null);
  const [dupDisplay, setDupDisplay] = useState("");

  const [deleteTarget, setDeleteTarget] = useState<BaseResumeSummary | null>(
    null,
  );
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
      router.push(`/base-resumes/${created.slug}`);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const del = useMutation({
    mutationFn: (slug: string) =>
      apiFetch<void>(`/api/base-resumes/${slug}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Deleted");
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

      {resumes.isError ? (
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
        <div className="flex flex-col gap-4">
          {visibleResumes.length > 0 ? (
            <BaseResumeGallery
              resumes={visibleResumes}
              href={(r) => `/base-resumes/${r.slug}`}
              renderActions={(r) => (
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        aria-label={`Actions for ${r.display_name ?? r.slug}`}
                      >
                        <MoreHorizontal className="size-4" />
                      </Button>
                    }
                  />
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem
                      onClick={() => {
                        setDupSource(r.slug);
                        setDupDisplay(`${r.display_name ?? r.slug} (copy)`);
                        setDupOpen(true);
                      }}
                    >
                      Duplicate
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      disabled={!r.pdf_rendered_at}
                      render={
                        <a
                          href={apiUrlForBrowserPdf(
                            `/api/base-resumes/${r.slug}/pdf`,
                          )}
                          download={`${(r.display_name ?? r.slug).replace(
                            /[^A-Za-z0-9]+/g,
                            "_",
                          )}.pdf`}
                        >
                          Download PDF
                        </a>
                      }
                    />
                    <DropdownMenuItem
                      onClick={() =>
                        archive.mutate({
                          slug: r.slug,
                          archived: !!r.archived_at,
                        })
                      }
                    >
                      {r.archived_at ? "Unarchive" : "Archive"}
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      variant="destructive"
                      onClick={() => setDeleteTarget(r)}
                    >
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            />
          ) : (
            <p className="text-muted-foreground text-sm">
              No career-track resumes yet.
            </p>
          )}
        </div>
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
              placeholder="Data Scientist (1 page)"
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
        <DialogContent>
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
            >
              {del.isPending ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}

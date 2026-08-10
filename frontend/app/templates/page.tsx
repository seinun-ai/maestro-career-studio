"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal } from "lucide-react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { TemplateGallery } from "@/components/templates/template-gallery";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import type { TemplateDetail, TemplateSummary } from "@/lib/types";
import { PageHeader, PageShell } from "@/components/page-shell";

const SLUG_RE = /^[a-z0-9_-]+$/;

export default function TemplatesListPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const confirm = useConfirm();

  const templates = useQuery({
    queryKey: ["templates"],
    queryFn: () => apiFetch<TemplateSummary[]>("/api/templates"),
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [newId, setNewId] = useState("");
  const [newDisplay, setNewDisplay] = useState("");

  const invalidate = () => qc.invalidateQueries({ queryKey: ["templates"] });

  const idValid = SLUG_RE.test(newId);
  const idError = newId.length > 0 && !idValid;

  const create = useMutation({
    mutationFn: () =>
      // validate=true so the new draft compiles immediately and is not stuck
      // in "draft" (unusable) until the editor is opened and re-validated.
      apiFetch<TemplateDetail>("/api/templates?validate=true", {
        method: "POST",
        body: JSON.stringify({
          id: newId,
          // backend TemplateCreate.display_name is a required non-null string;
          // fall back to the slug when the field is left blank.
          display_name: newDisplay.trim() || newId,
          // no source -> the server injects its canonical starter
          origin: "frontend",
        }),
      }),
    onSuccess: (created) => {
      setCreateOpen(false);
      setNewId("");
      setNewDisplay("");
      invalidate();
      router.push(`/templates/${created.id}`);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const duplicate = useMutation({
    mutationFn: async (template: TemplateSummary) => {
      const detail = await apiFetch<TemplateDetail>(
        `/api/templates/${template.id}`,
      );
      return apiFetch<TemplateDetail>("/api/templates", {
        method: "POST",
        body: JSON.stringify({
          id: `${template.id}_copy`,
          display_name: `${template.display_name ?? template.id} copy`,
          source: detail.source,
          origin: "frontend",
          engine: detail.engine,
        }),
      });
    },
    onSuccess: () => {
      toast.success("Duplicated");
      invalidate();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const setDefault = useMutation({
    mutationFn: (id: string) =>
      apiFetch<TemplateDetail>(`/api/templates/${id}/set-default`, {
        method: "POST",
      }),
    onSuccess: () => {
      toast.success("Default updated");
      invalidate();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const revalidate = useMutation({
    mutationFn: (id: string) =>
      apiFetch<{ ok: boolean; error: string | null }>(
        `/api/templates/${id}/validate`,
        { method: "POST" },
      ),
    onSuccess: (res) => {
      invalidate();
      if (res.ok) toast.success("Re-validated");
      else toast.error(res.error ?? "Validation failed");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const del = useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/api/templates/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Deleted");
      invalidate();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const onDelete = async (template: TemplateSummary) => {
    const ok = await confirm({
      title: `Delete ${template.display_name ?? template.id}?`,
      description:
        "This removes the template source and its compiled assets. This can't be undone.",
      confirmLabel: "Delete",
      destructive: true,
    });
    if (ok) del.mutate(template.id);
  };

  return (
    <PageShell>
      <PageHeader
        title="Templates"
        subtitle="Templates used to render resumes."
        actions={
          <Button onClick={() => setCreateOpen(true)}>New template</Button>
        }
      />

      {templates.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      ) : (templates.data ?? []).length > 0 ? (
        <TemplateGallery
          templates={templates.data ?? []}
          // The card IS the Edit affordance now — no button needed.
          href={(t) => `/templates/${t.id}`}
          renderActions={(t) => (
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    aria-label={`Actions for ${t.display_name ?? t.id}`}
                  >
                    <MoreHorizontal className="size-4" />
                  </Button>
                }
              />
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  disabled={revalidate.isPending}
                  onClick={() => revalidate.mutate(t.id)}
                >
                  Re-validate
                </DropdownMenuItem>
                <DropdownMenuItem
                  disabled={t.status !== "ready" || t.is_default}
                  onClick={() => setDefault.mutate(t.id)}
                >
                  Set default
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => duplicate.mutate(t)}>
                  Duplicate
                </DropdownMenuItem>
                <DropdownMenuItem
                  variant="destructive"
                  disabled={t.is_default}
                  onClick={() => onDelete(t)}
                >
                  Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        />
      ) : (
        <p className="text-muted-foreground text-sm">No templates yet.</p>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New template</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="new_id">ID</Label>
              <Input
                id="new_id"
                placeholder="classic_serif"
                value={newId}
                onChange={(e) => setNewId(e.target.value)}
                aria-invalid={idError}
              />
              {idError && (
                <p className="text-destructive text-xs">
                  Use only lowercase letters, numbers, hyphens, and underscores.
                </p>
              )}
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="new_display">Display name</Label>
              <Input
                id="new_display"
                value={newDisplay}
                onChange={(e) => setNewDisplay(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => create.mutate()}
              disabled={!idValid || create.isPending}
            >
              {create.isPending ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}

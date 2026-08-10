"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

import { ArrowLeft } from "lucide-react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { FormattingPanel } from "@/components/resume-editor/formatting-panel";
import { PdfPagesPreview } from "@/components/resume-editor/pdf-pages-preview";
import { LatexEditor } from "@/components/templates/latex-editor";
import { EditorShell } from "@/components/resume-editor/editor-shell";
import { Badge } from "@/components/ui/badge";
import { IconButton } from "@/components/icon-button";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiFetch, apiUrlForBrowserPdf } from "@/lib/api";
import { FORMATTING_DEFAULTS, type ResumeFormatting } from "@/lib/formatting";
import type { TemplateDetail, TemplateValidationResult } from "@/lib/types";

export default function TemplateEditorPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();

  const tq = useQuery({
    queryKey: ["template", id],
    queryFn: () => apiFetch<TemplateDetail>(`/api/templates/${id}`),
  });

  const [tab, setTab] = useState("knobs");
  const [source, setSource] = useState("");
  const [dirty, setDirty] = useState(false);
  const [previewNonce, setPreviewNonce] = useState(0);
  const [defaultFormatting, setDefaultFormatting] =
    useState<Partial<ResumeFormatting> | null>(null);
  const [validation, setValidation] = useState<TemplateValidationResult | null>(
    null,
  );

  // Seed `source`/`defaultFormatting` once per template id, so a background
  // refetch never clobbers in-progress edits. Re-seed only when switching to a
  // different template.
  const seededId = useRef<string | null>(null);
  useEffect(() => {
    if (tq.data && seededId.current !== tq.data.id) {
      seededId.current = tq.data.id;
      setSource(tq.data.source);
      setDefaultFormatting(
        (tq.data.default_formatting as Partial<ResumeFormatting> | null) ??
          null,
      );
      setDirty(false);
      setValidation(null);
    }
  }, [tq.data]);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["template", id] });
    qc.invalidateQueries({ queryKey: ["templates"] });
  };

  const saveM = useMutation({
    mutationFn: () =>
      apiFetch<TemplateDetail>(`/api/templates/${id}`, {
        method: "PUT",
        body: JSON.stringify({ source }),
      }),
    onSuccess: () => {
      setDirty(false);
      invalidate();
      toast.success("Saved");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const recompileM = useMutation({
    // Single round trip: save + validate. The returned row's status/last_error
    // carry the compile result.
    mutationFn: async (): Promise<TemplateValidationResult> => {
      const row = await apiFetch<TemplateDetail>(
        `/api/templates/${id}?validate=true`,
        {
          method: "PUT",
          body: JSON.stringify({ source }),
        },
      );
      return { ok: row.status === "ready", error: row.last_error };
    },
    onSuccess: (res) => {
      setDirty(false);
      setValidation(res);
      invalidate();
      if (res.ok) {
        setPreviewNonce((n) => n + 1);
        toast.success("Compiled");
      } else {
        toast.error("LaTeX error. See the preview panel.");
      }
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // Persist a knob change to the theme's default overlay. The endpoint is
  // self-contained (it persists AND re-renders the stored preview), so there is
  // no source-update recompile: that path 403s on the default template and would
  // piggyback the (possibly unsaved) source. Bump the preview nonce on success
  // to cache-bust the refreshed preview images.
  const defaultFmtM = useMutation({
    mutationFn: (next: Partial<ResumeFormatting> | null) =>
      apiFetch<TemplateDetail>(`/api/templates/${id}/default-formatting`, {
        method: "PUT",
        body: JSON.stringify({ formatting: next }),
      }),
    onSuccess: () => {
      invalidate();
      setPreviewNonce((n) => n + 1);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // Debounce knob-change persistence: a slider drag emits many onChange events,
  // and each PUT triggers a pdflatex round trip. Fire one ~400ms after the last
  // change so the last value wins.
  const fmtTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Holds the value awaiting the debounce; read only while a timer is pending.
  const pendingFmtRef = useRef<Partial<ResumeFormatting> | null>(null);
  // Keep the latest mutate so the unmount flush isn't a stale closure.
  const defaultFmtMutateRef = useRef(defaultFmtM.mutate);
  useEffect(() => {
    defaultFmtMutateRef.current = defaultFmtM.mutate;
  }, [defaultFmtM.mutate]);
  useEffect(
    () => () => {
      // A pending timer on unmount means the last knob change hasn't persisted
      // yet. Flush it (fire the PUT now) instead of clearing, so navigating away
      // mid-debounce doesn't silently drop the change.
      if (fmtTimer.current) {
        clearTimeout(fmtTimer.current);
        fmtTimer.current = null;
        defaultFmtMutateRef.current(pendingFmtRef.current);
      }
    },
    [],
  );
  const scheduleDefaultFmt = (next: Partial<ResumeFormatting> | null) => {
    if (fmtTimer.current) clearTimeout(fmtTimer.current);
    pendingFmtRef.current = next;
    fmtTimer.current = setTimeout(() => {
      fmtTimer.current = null;
      defaultFmtM.mutate(next);
    }, 400);
  };

  const setDefaultM = useMutation({
    mutationFn: () =>
      apiFetch<TemplateDetail>(`/api/templates/${id}/set-default`, {
        method: "POST",
      }),
    onSuccess: () => {
      invalidate();
      toast.success("Default updated");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  if (tq.isError) {
    return (
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4 p-6">
        <p className="text-destructive">
          {(tq.error as Error)?.message ?? "Failed to load template."}
        </p>
        <Button
          render={<Link href="/templates">Back to templates</Link>}
          nativeButton={false}
          variant="outline"
        />
      </main>
    );
  }

  if (tq.isLoading || !tq.data) {
    return (
      <main className="flex w-full flex-1 flex-col gap-4 p-6">
        <Skeleton className="h-10 w-60" />
        <Skeleton className="h-96 w-full" />
      </main>
    );
  }

  const status = tq.data.status;
  const isReady = status === "ready" || validation?.ok === true;
  const compileError =
    validation && !validation.ok
      ? validation.error
      : status !== "ready"
        ? tq.data.last_error
        : null;
  // Cache-bust the page images on both a compile (validated_at moves) and any
  // save/recompile round trip (local nonce).
  const previewVersion = `${tq.data.validated_at ?? ""}:${previewNonce}`;

  return (
    // <main> here rather than inside EditorShell: the studio route already
    // wraps the shell in its own <main> alongside a page header, and two of
    // them would nest.
    <main className="flex min-h-0 w-full flex-1 flex-col">
    <EditorShell
      fullHeightLeft
      storageKey="templateEditor"
      editor={
        <Tabs
          value={tab}
          onValueChange={(v) => setTab(v as string)}
          className="flex h-full min-h-0 flex-col gap-0"
        >
          <div className="flex flex-wrap items-center gap-2 border-b p-2">
            <div className="mr-auto flex min-w-0 items-center gap-2 text-sm font-medium">
              {/* This page had NO heading and no way back: the template's name
                  was a bare <span>, so the route had no <h1> at all and the
                  only exit was the browser button. Every other editor in the
                  app leads with a back control. */}
              <IconButton
                label="Back to templates"
                icon={<ArrowLeft className="size-4" />}
                size="icon-sm"
                className="shrink-0"
                nativeButton={false}
                render={
                  <Link href="/templates" className="text-muted-foreground" />
                }
              />
              <h1 className="truncate text-sm font-medium">
                {tq.data.display_name ?? id}
              </h1>
              <Badge variant={status === "ready" ? "secondary" : "outline"}>
                {status}
              </Badge>
              {tq.data.is_default && <Badge variant="secondary">default</Badge>}
              <Badge variant="outline" className="font-mono">
                {tq.data.engine}
              </Badge>
              {dirty && (
                <span className="text-xs text-amber-600">unsaved</span>
              )}
            </div>
            <TabsList>
              <TabsTrigger value="knobs">Knobs</TabsTrigger>
              <TabsTrigger value="code">Code</TabsTrigger>
            </TabsList>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => saveM.mutate()}
                disabled={saveM.isPending || !dirty}
              >
                Save
              </Button>
              <Button
                size="sm"
                onClick={() => recompileM.mutate()}
                disabled={recompileM.isPending}
              >
                {recompileM.isPending ? "Recompiling…" : "Recompile"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setDefaultM.mutate()}
                disabled={
                  status !== "ready" || tq.data.is_default || setDefaultM.isPending
                }
              >
                Set default
              </Button>
            </div>
          </div>

          <TabsContent
            value="knobs"
            className="min-h-0 flex-1 overflow-y-auto"
          >
            {/* Edits store the diff from schema defaults — exactly the theme's
                default_formatting overlay. `onChange(null)` clears it. */}
            <FormattingPanel
              value={defaultFormatting}
              onChange={(next) => {
                setDefaultFormatting(next);
                scheduleDefaultFmt(next);
              }}
              supportedKeys={tq.data.supported_fmt_keys}
              baseline={FORMATTING_DEFAULTS}
              collapsible={false}
            />
            <p className="text-muted-foreground px-3 py-2 text-xs">
              Defaults for this theme. A resume that selects it inherits these,
              then layers its own overrides on top.
            </p>
          </TabsContent>

          <TabsContent
            value="code"
            className="flex min-h-0 flex-1 flex-col"
          >
            <div className="min-h-0 flex-1 p-2">
              <LatexEditor
                value={source}
                onChange={(v) => {
                  setSource(v);
                  setDirty(true);
                }}
                height="100%"
              />
            </div>
          </TabsContent>
        </Tabs>
      }
      previewHeader={
        <a
          className="text-muted-foreground hover:text-foreground text-xs underline"
          href={apiUrlForBrowserPdf(`/api/templates/${id}/preview.pdf`)}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open PDF
        </a>
      }
      preview={
        compileError ? (
          <div className="m-2 space-y-1">
            <p className="text-muted-foreground text-xs">
              Last compile failed. Fix the source and Recompile.
            </p>
            <pre className="bg-destructive/10 text-destructive max-h-full overflow-auto rounded p-2 text-xs">
              {compileError}
            </pre>
          </div>
        ) : isReady ? (
          <PdfPagesPreview
            basePath={`/api/templates/${id}`}
            version={previewVersion}
            emptyMessage="Recompile to generate a preview."
          />
        ) : (
          <div className="text-muted-foreground p-3 text-sm">
            Recompile to generate a preview.
          </div>
        )
      }
    />
    </main>
  );
}

"use client";

import { useId, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Copy,
  Download,
  FileText,
  Loader2,
  Pencil,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { IconButton } from "@/components/icon-button";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LoadErrorState } from "@/components/load-error-state";
import { useEditorFocusReturn } from "@/hooks/use-confirm-discard";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { apiFetch, apiUrlForBrowserPdf } from "@/lib/api";
import { couldnt, loadErrorDetail } from "@/lib/error-text";
import { isLoadFailure } from "@/lib/query-state";
import { notifyRenderNote } from "@/lib/render-note";
import type { QAEntry, QAResponse } from "@/lib/types";

const TONES = ["balanced", "enthusiastic", "formal", "concise"];

const TONE_LABELS: Record<string, string> = {
  balanced: "Balanced",
  enthusiastic: "Enthusiastic",
  formal: "Formal",
  concise: "Concise",
};

const KIND_LABELS: Record<string, string> = {
  cover_letter: "Cover letter",
};

export function QATab({ applicationId }: { applicationId: string }) {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const { data: entries, isError, error, isFetching, fetchStatus, refetch, errorUpdateCount } = useQuery({
    queryKey: ["qa", applicationId],
    queryFn: () =>
      apiFetch<QAEntry[]>(
        `/api/qa?application_id=${encodeURIComponent(applicationId)}`,
      ),
  });

  const [questions, setQuestions] = useState("");
  const [tone, setTone] = useState<string>("balanced");
  const questionsHintId = useId();
  const historyHeadingId = useId();

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["qa", applicationId] });

  // Takes the text it sends: the box stays editable while it answers, and
  // only that text is cleared when the answers land.
  const askQuestions = useMutation({
    mutationFn: (sent: string) => {
      const list = sent
        .split("\n")
        .map((q) => q.trim())
        .filter((q) => q.length > 0);
      if (list.length === 0) throw new Error("Type at least one question.");
      return apiFetch<QAResponse>("/api/qa", {
        method: "POST",
        body: JSON.stringify({
          application_id: applicationId,
          questions: list,
        }),
      });
    },
    onSuccess: (_answers, sent) => {
      setQuestions((current) => (current === sent ? "" : current));
      toast.success("Answers ready");
      invalidate();
    },
    onError: (err: Error) => toast.error(couldnt("answer the questions", err)),
  });

  const coverLetter = useMutation({
    mutationFn: () =>
      apiFetch<QAResponse>("/api/qa", {
        method: "POST",
        body: JSON.stringify({
          application_id: applicationId,
          cover_letter: { tone },
        }),
      }),
    onSuccess: () => {
      toast.success("Cover letter ready");
      invalidate();
    },
    onError: (err: Error) => toast.error(couldnt("write the cover letter", err)),
  });

  const deleteEntry = useMutation({
    mutationFn: (entryId: string) =>
      apiFetch<void>(`/api/qa/${entryId}`, { method: "DELETE" }),
    onSuccess: invalidate,
    onError: (err: Error) => toast.error(couldnt("delete the answer", err)),
  });

  const regenerateEntry = useMutation({
    mutationFn: (entry: QAEntry) =>
      apiFetch<QAEntry>(`/api/qa/${entry.id}/regenerate`, {
        method: "POST",
        body: JSON.stringify(entry.kind === "cover_letter" ? { tone } : {}),
      }),
    onSuccess: () => {
      toast.success("New version ready");
      invalidate();
    },
    onError: (err: Error) => toast.error(couldnt("write a new version", err)),
  });

  const editEntry = useMutation({
    mutationFn: ({ id, answer }: { id: string; answer: string }) =>
      apiFetch<QAEntry>(`/api/qa/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ answer }),
      }),
    onSuccess: (updated) => {
      // Show the saved text at once: the editor closes on this, not before
      // it, and the refetch below would otherwise flash the old letter.
      qc.setQueryData<QAEntry[]>(["qa", applicationId], (prev) =>
        prev?.map((e) => (e.id === updated.id ? updated : e)),
      );
      toast.success("Cover letter saved");
      invalidate();
    },
    // Toasts; the card stays in edit mode with the typed text.
    onError: (err: Error) => toast.error(couldnt("save the cover letter", err)),
  });

  // One request per click: a double click read isPending === false twice and
  // paid for two generations.
  const askOnce = useSingleFlight(askQuestions.mutate);
  const coverOnce = useSingleFlight(coverLetter.mutate);
  const regenerateOnce = useSingleFlight(regenerateEntry.mutate);

  // No "was edited" signal is stored, so any saved letter may hold the
  // user's own edits: replacing it asks. Generate replaces every saved letter
  // once the new one is written, so it asks too.
  const hasCoverLetter = entries?.some((e) => e.kind === "cover_letter" && e.answer) ?? false;
  const confirmReplaceLetter = () =>
    confirm({
      title: "Replace your cover letter?",
      description: "A new letter replaces the saved one, including any edits you made to it.",
      confirmLabel: "Replace",
      destructive: true,
    });
  // Cover letters open for editing. While one is open no letter is generated
  // (Generate would replace it under the draft, and the next Save overwrite
  // the new one), and while a letter generates none opens for editing.
  const [editingIds, setEditingIds] = useState<string[]>([]);
  const letterEditing = entries?.some((e) => editingIds.includes(e.id)) ?? false;
  const setLetterEditing = (id: string, on: boolean) =>
    setEditingIds((ids) => (on ? [...ids, id] : ids.filter((x) => x !== id)));
  const generateCoverLetter = async () => {
    if (hasCoverLetter && !(await confirmReplaceLetter())) return;
    coverOnce();
  };

  const renderEntry = useMutation({
    mutationFn: (id: string) =>
      apiFetch<QAEntry>(`/api/qa/${id}/render`, { method: "POST" }),
    onSuccess: (entry) => {
      notifyRenderNote(entry);
      toast.success("Cover letter PDF ready");
      invalidate();
    },
    onError: (err: Error) => toast.error(couldnt("create the PDF", err)),
  });

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Application questions</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <p id={questionsHintId} className="text-muted-foreground text-xs">
            One question per line.
          </p>
          <Textarea
            aria-label="Application questions"
            aria-describedby={questionsHintId}
            value={questions}
            onChange={(e) => setQuestions(e.target.value)}
            rows={4}
          />
          <Button
            onClick={() => askOnce(questions)}
            disabled={askQuestions.isPending}
            focusableWhenDisabled
            className="data-disabled:pointer-events-none data-disabled:opacity-50"
          >
            {askQuestions.isPending ? "Answering…" : "Answer questions"}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Cover letter</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-2">
          <div className="grid gap-1.5">
            <Label htmlFor="tone">Tone</Label>
            <Select value={tone} onValueChange={(v) => setTone(v ?? "balanced")}>
              <SelectTrigger id="tone" className="w-44">
                <SelectValue>{TONE_LABELS[tone] ?? tone}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {TONES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {TONE_LABELS[t] ?? t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button
            onClick={() => void generateCoverLetter()}
            disabled={coverLetter.isPending || letterEditing}
            focusableWhenDisabled
            className="data-disabled:pointer-events-none data-disabled:opacity-50"
          >
            {coverLetter.isPending ? "Writing…" : "Write cover letter"}
          </Button>
        </CardContent>
      </Card>

      {/* tabIndex={-1}: where focus lands when the error below recovers. Named
          by its heading, since it can hold focus. */}
      <section tabIndex={-1} aria-labelledby={historyHeadingId} className="space-y-3 outline-none">
        <h3 id={historyHeadingId} className="text-sm font-semibold">History</h3>
        {isLoadFailure({ data: entries, isError, fetchStatus, errorUpdateCount }) ? (
          <LoadErrorState
            className="py-8"
            title="Couldn't load your answers."
            detail={loadErrorDetail(error)}
            retrying={isFetching}
            onRetry={() => void refetch()}
          />
        ) : !entries || entries.length === 0 ? (
          <p className="text-muted-foreground text-sm">No answers yet.</p>
        ) : (
          entries.map((entry, i) => {
            const isRegenerating =
              regenerateEntry.isPending && regenerateEntry.variables?.id === entry.id;
            const isSaving =
              editEntry.isPending && editEntry.variables?.id === entry.id;
            const isRendering =
              renderEntry.isPending && renderEntry.variables === entry.id;
            return (
              <QAEntryCard
                key={entry.id}
                entry={entry}
                index={i}
                isDeleting={deleteEntry.isPending}
                isRegenerating={isRegenerating}
                regenerateBusy={regenerateEntry.isPending}
                editing={editingIds.includes(entry.id)}
                onEditingChange={(on) => setLetterEditing(entry.id, on)}
                letterEditing={letterEditing}
                generating={coverLetter.isPending}
                isRendering={isRendering}
                isSaving={isSaving}
                onDelete={async () => {
                  const ok = await confirm({
                    title: "Delete this answer?",
                    description:
                      entry.kind === "cover_letter"
                        ? "This deletes the cover letter."
                        : "This deletes the question and its answer.",
                    confirmLabel: "Delete",
                    destructive: true,
                  });
                  if (!ok) return;
                  deleteEntry.mutate(entry.id);
                }}
                onRegenerate={async () => {
                  if (entry.kind === "cover_letter" && entry.answer && !(await confirmReplaceLetter())) return;
                  regenerateOnce(entry);
                }}
                onRender={() => renderEntry.mutate(entry.id)}
                onSave={(answer) => editEntry.mutateAsync({ id: entry.id, answer })}
              />
            );
          })
        )}
      </section>
    </>
  );
}

function QAEntryCard({
  entry,
  index,
  isDeleting,
  isRegenerating,
  regenerateBusy,
  editing,
  onEditingChange,
  letterEditing,
  generating,
  isRendering,
  isSaving,
  onDelete,
  onRegenerate,
  onRender,
  onSave,
}: {
  entry: QAEntry;
  index: number;
  isDeleting: boolean;
  isRegenerating: boolean;
  /** Any entry is regenerating: one generation at a time. */
  regenerateBusy: boolean;
  /** This letter is open for editing (the state lives in QATab). */
  editing: boolean;
  onEditingChange: (editing: boolean) => void;
  /** Some cover letter is open for editing: no letter regenerates. */
  letterEditing: boolean;
  /** Generate cover letter is running: it replaces every saved letter. */
  generating: boolean;
  isRendering: boolean;
  isSaving: boolean;
  onDelete: () => void;
  onRegenerate: () => void;
  onRender: () => void;
  /** Resolves once the save landed; rejects when it failed. */
  onSave: (answer: string) => Promise<unknown>;
}) {
  const [draft, setDraft] = useState(entry.answer ?? "");
  useLeaveGuard(editing && draft !== (entry.answer ?? ""));
  // Save and Cancel unmount the pressed button with the editor; focus goes
  // back to Edit.
  const { editRef, returnFocus } = useEditorFocusReturn(editing);
  const closeEditor = () => { returnFocus(); onEditingChange(false); };
  const isCoverLetter = entry.kind === "cover_letter";
  // Generated documents (vs question answers) get edit-in-place.
  const isDocument = isCoverLetter;
  // Only question/cover_letter can be regenerated server-side; retired/unknown
  // kinds would 400. Copy and delete stay available for every kind.
  const isRegenerable =
    entry.kind === "question" || entry.kind === "cover_letter";

  return (
    <Card
      className="animate-fade-rise"
      style={{ animationDelay: `${Math.min(index, 6) * 40}ms` }}
      data-pending={isRegenerating || isRendering || isSaving || undefined}
    >
      <CardHeader className="flex flex-row items-start justify-between gap-2 pb-2">
        <CardTitle className="text-sm">
          {isDocument ? KIND_LABELS[entry.kind] : entry.prompt}
        </CardTitle>
        <div className="flex shrink-0 gap-1">
          {isDocument && !editing ? (
            <IconButton
              ref={editRef}
              label="Edit"
              icon={<Pencil />}
              onClick={() => {
                setDraft(entry.answer ?? "");
                onEditingChange(true);
              }}
              disabled={isSaving || isRendering || isRegenerating || generating}
            />
          ) : null}
          <IconButton
            label="Copy"
            icon={<Copy />}
            onClick={() => {
              navigator.clipboard
                .writeText(entry.answer ?? "")
                .then(() => toast.success("Copied"));
            }}
          />
          {isCoverLetter ? (
            <IconButton
              label="Create PDF"
              icon={isRendering ? <Loader2 className="animate-spin" /> : <FileText />}
              onClick={onRender}
              disabled={isRendering || isSaving || editing}
            />
          ) : null}
          {isCoverLetter && entry.pdf_path ? (
            <IconButton
              label="Download PDF"
              icon={<Download />}
              onClick={() =>
                window.open(apiUrlForBrowserPdf(`/api/qa/${entry.id}/pdf`), "_blank")
              }
            />
          ) : null}
          {isRegenerable ? (
            <IconButton
              label="Write a new version"
              icon={
                isRegenerating ? <Loader2 className="animate-spin" /> : <RefreshCw />
              }
              onClick={onRegenerate}
              // A letter waits while any letter is open for editing: a new
              // one would land under the draft and the next Save overwrite it.
              disabled={regenerateBusy || isSaving || isRendering || (isCoverLetter && letterEditing)}
              focusableWhenDisabled
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
            />
          ) : null}
          <IconButton
            label="Delete"
            icon={<Trash2 />}
            onClick={onDelete}
            disabled={isDeleting}
          />
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {isDocument && editing ? (
          <>
            <Textarea
              aria-label="Cover letter text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              // Keys typed after Save would be dropped when the editor closes.
              readOnly={isSaving}
              rows={10}
              className="text-sm"
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={isSaving}
                focusableWhenDisabled
                className="data-disabled:pointer-events-none data-disabled:opacity-50"
                onClick={async () => {
                  // A failed save stays open with the text intact.
                  try { await onSave(draft); } catch { return; }
                  closeEditor();
                }}
              >
                {isSaving ? "Saving…" : "Save"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => { setDraft(entry.answer ?? ""); closeEditor(); }}
                disabled={isSaving}
              >
                Cancel
              </Button>
            </div>
          </>
        ) : (
          <p className="text-sm whitespace-pre-wrap">{entry.answer}</p>
        )}
      </CardContent>
    </Card>
  );
}

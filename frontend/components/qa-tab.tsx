"use client";

import { useState } from "react";
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
import { apiFetch, apiUrlForBrowserPdf } from "@/lib/api";
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
  const { data: entries } = useQuery({
    queryKey: ["qa", applicationId],
    queryFn: () =>
      apiFetch<QAEntry[]>(
        `/api/qa?application_id=${encodeURIComponent(applicationId)}`,
      ),
  });

  const [questions, setQuestions] = useState("");
  const [tone, setTone] = useState<string>("balanced");

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["qa", applicationId] });

  const askQuestions = useMutation({
    mutationFn: () => {
      const list = questions
        .split("\n")
        .map((q) => q.trim())
        .filter((q) => q.length > 0);
      if (list.length === 0) throw new Error("No questions to ask");
      return apiFetch<QAResponse>("/api/qa", {
        method: "POST",
        body: JSON.stringify({
          application_id: applicationId,
          questions: list,
        }),
      });
    },
    onSuccess: () => {
      setQuestions("");
      toast.success("Answers generated");
      invalidate();
    },
    onError: (err: Error) => toast.error(err.message),
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
      toast.success("Cover letter generated");
      invalidate();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const deleteEntry = useMutation({
    mutationFn: (entryId: string) =>
      apiFetch<void>(`/api/qa/${entryId}`, { method: "DELETE" }),
    onSuccess: invalidate,
    onError: (err: Error) => toast.error(err.message),
  });

  const regenerateEntry = useMutation({
    mutationFn: (entry: QAEntry) =>
      apiFetch<QAEntry>(`/api/qa/${entry.id}/regenerate`, {
        method: "POST",
        body: JSON.stringify(entry.kind === "cover_letter" ? { tone } : {}),
      }),
    onSuccess: () => {
      toast.success("Regenerated");
      invalidate();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const editEntry = useMutation({
    mutationFn: ({ id, answer }: { id: string; answer: string }) =>
      apiFetch<QAEntry>(`/api/qa/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ answer }),
      }),
    onSuccess: () => {
      toast.success("Saved");
      invalidate();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const renderEntry = useMutation({
    mutationFn: (id: string) =>
      apiFetch<QAEntry>(`/api/qa/${id}/render`, { method: "POST" }),
    onSuccess: () => {
      toast.success("Cover letter PDF ready");
      invalidate();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Ask questions</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Textarea
            aria-label="Questions to ask, one per line"
            placeholder="One question per line…"
            value={questions}
            onChange={(e) => setQuestions(e.target.value)}
            rows={4}
          />
          <Button
            onClick={() => askQuestions.mutate()}
            disabled={askQuestions.isPending}
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
            onClick={() => coverLetter.mutate()}
            disabled={coverLetter.isPending}
          >
            {coverLetter.isPending ? "Generating…" : "Generate cover letter"}
          </Button>
        </CardContent>
      </Card>

      <div className="space-y-3">
        <h3 className="text-sm font-semibold">History</h3>
        {!entries || entries.length === 0 ? (
          <p className="text-muted-foreground text-sm">No Q&amp;A entries yet.</p>
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
                isRendering={isRendering}
                isSaving={isSaving}
                onDelete={async () => {
                  const ok = await confirm({
                    title: "Delete this Q&A entry?",
                    description:
                      entry.kind === "question"
                        ? "The question and its answer will be removed from history."
                        : `The ${KIND_LABELS[entry.kind]?.toLowerCase() ?? "entry"} will be removed from history.`,
                    confirmLabel: "Delete",
                    destructive: true,
                  });
                  if (!ok) return;
                  deleteEntry.mutate(entry.id);
                }}
                onRegenerate={() => regenerateEntry.mutate(entry)}
                onRender={() => renderEntry.mutate(entry.id)}
                onSave={(answer) => editEntry.mutate({ id: entry.id, answer })}
              />
            );
          })
        )}
      </div>
    </>
  );
}

function QAEntryCard({
  entry,
  index,
  isDeleting,
  isRegenerating,
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
  isRendering: boolean;
  isSaving: boolean;
  onDelete: () => void;
  onRegenerate: () => void;
  onRender: () => void;
  onSave: (answer: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(entry.answer ?? "");
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
              label="Edit"
              icon={<Pencil />}
              onClick={() => {
                setDraft(entry.answer ?? "");
                setEditing(true);
              }}
              disabled={isSaving || isRendering || isRegenerating}
            />
          ) : null}
          <IconButton
            label="Copy to clipboard"
            icon={<Copy />}
            onClick={() => {
              navigator.clipboard
                .writeText(entry.answer ?? "")
                .then(() => toast.success("Copied"));
            }}
          />
          {isCoverLetter ? (
            <IconButton
              label="Render PDF"
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
              label="Regenerate"
              icon={
                isRegenerating ? <Loader2 className="animate-spin" /> : <RefreshCw />
              }
              onClick={onRegenerate}
              disabled={isRegenerating || isSaving || isRendering}
            />
          ) : null}
          <IconButton
            label="Delete entry"
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
              rows={10}
              className="text-sm"
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={() => {
                  onSave(draft);
                  setEditing(false);
                }}
                disabled={isSaving}
              >
                {isSaving ? "Saving..." : "Save"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setDraft(entry.answer ?? "");
                  setEditing(false);
                }}
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

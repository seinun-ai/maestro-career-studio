"use client";

import { DragEvent, useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileText, RefreshCw, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  deleteKbDocument,
  getKbEntity,
  remintKbDocument,
  uploadKbDocument,
} from "@/lib/api";
import {
  documentAddedWords,
  documentReadAgainWords,
  documentStatusLabel,
  draftsFromDocument,
} from "@/lib/document-words";
import { couldnt } from "@/lib/error-text";
import { formatAbsoluteDateTime } from "@/lib/format-date";
import type { KBDocumentOut, KBEntityDetail } from "@/lib/types";
import { cn } from "@/lib/utils";
import { DOCUMENT_ACCEPT } from "@/lib/upload-accept";

export function DocumentsPanel({
  entityId,
  documents,
}: {
  entityId: string;
  documents: KBDocumentOut[];
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const queryClient = useQueryClient();
  const confirm = useConfirm();

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["kb", "entity", entityId] });
    void queryClient.invalidateQueries({ queryKey: ["kb", "entities"] });
    void queryClient.invalidateQueries({ queryKey: ["kb", "drafts"] });
  };

  // The item's bullets as the server has them now (and in the cache): how many
  // drafts a read made is counted from them, never claimed.
  const freshDetail = () =>
    queryClient.fetchQuery<KBEntityDetail>({
      queryKey: ["kb", "entity", entityId],
      queryFn: () => getKbEntity(entityId),
      staleTime: 0,
    });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const document = await uploadKbDocument(entityId, file);
      const detail = await freshDetail().catch(() => undefined);
      return { document, drafted: draftsFromDocument(detail?.points, document.id) };
    },
    onSuccess: ({ document, drafted }) => {
      // Says what reading did: new bullets, none, or a failed suggestion step.
      const words = documentAddedWords(document, drafted);
      if (document.ingest_status === "failed") toast.warning(words);
      else toast.success(words);
      if (inputRef.current) inputRef.current.value = "";
      invalidate();
    },
    onError: (error: Error) => toast.error(couldnt("add the document", error)),
  });

  const remint = useMutation({
    mutationFn: async (documentId: string) => {
      const before = draftsFromDocument(
        queryClient.getQueryData<KBEntityDetail>(["kb", "entity", entityId])?.points,
        documentId,
      );
      const document = await remintKbDocument(documentId);
      const detail = await freshDetail().catch(() => undefined);
      return { document, drafted: Math.max(0, draftsFromDocument(detail?.points, documentId) - before) };
    },
    onSuccess: ({ document, drafted }) => {
      const words = documentReadAgainWords(document, drafted);
      if (document.ingest_status === "failed") toast.error(words);
      else toast.success(words);
      invalidate();
    },
    onError: (error: Error) => toast.error(couldnt("read the document again", error)),
  });

  const remove = useMutation({
    mutationFn: (documentId: string) => deleteKbDocument(documentId),
    onSuccess: () => {
      toast.success("Document deleted");
      invalidate();
    },
    onError: (error: Error) => toast.error(couldnt("delete the document", error)),
  });

  const receiveFile = (file: File | undefined) => {
    if (file && !upload.isPending) upload.mutate(file);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    receiveFile(event.dataTransfer.files[0]);
  };

  const requestDelete = async (document: KBDocumentOut) => {
    const accepted = await confirm({
      title: `Delete ${document.filename}?`,
      description:
        "Bullets made from it stay.",
      confirmLabel: "Delete document",
      destructive: true,
    });
    if (accepted) remove.mutate(document.id);
  };

  return (
    <Card className="rounded-2xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileText className="size-4" aria-hidden="true" /> Documents
          <Badge className="rounded-full" variant="secondary">
            {documents.length}
          </Badge>
        </CardTitle>
        <p className="text-muted-foreground text-sm">We read these to suggest bullets for you to review.</p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div
          className="rounded-2xl bg-muted/45 p-5 text-center transition-colors duration-150 ease-out hover:bg-muted/70"
          onDragOver={(event) => event.preventDefault()}
          onDrop={onDrop}
        >
          <input
            ref={inputRef}
            type="file"
            className="sr-only"
            accept={DOCUMENT_ACCEPT}
            onChange={(event) => receiveFile(event.target.files?.[0])}
            disabled={upload.isPending}
            aria-label="Upload document"
          />
          <span className="mx-auto flex size-9 items-center justify-center rounded-full bg-background/80">
            <Upload className="text-muted-foreground size-4" aria-hidden="true" />
          </span>
          <p className="mt-2 text-sm font-medium">Drop a file here</p>
          <p className="text-muted-foreground mt-1 text-xs">PDF, Word, image or text, up to 10 MB</p>
          <Button
            className="mt-3 rounded-full"
            size="sm"
            variant="secondary"
            onClick={() => inputRef.current?.click()}
            disabled={upload.isPending}
          >
            {upload.isPending ? "Reading…" : "Choose file"}
          </Button>
        </div>

        {documents.length === 0 ? (
          <div className="py-3 text-center">
            <p className="text-sm font-medium">No documents yet</p>
          </div>
        ) : (
          <ul className="divide-y divide-foreground/10">
            {documents.map((document) => {
              const canRemint = ["failed", "extracted"].includes(document.ingest_status);
              return (
                <li key={document.id} className="group/document py-3">
                  <div className="flex items-start gap-3">
                    <span className="bg-muted flex size-8 shrink-0 items-center justify-center rounded-full">
                      <FileText className="text-muted-foreground size-3.5" aria-hidden="true" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium" title={document.filename}>
                            {document.filename}
                          </p>
                          <p className="text-muted-foreground text-xs">
                            {formatBytes(document.size_bytes)} · {formatAbsoluteDateTime(document.created_at)}
                          </p>
                        </div>
                        <DocumentStatus document={document} />
                      </div>
                      {document.ingest_summary ? (
                        <p className="text-muted-foreground mt-2 text-xs leading-relaxed">
                          {document.ingest_summary}
                        </p>
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-2 flex justify-end gap-1 opacity-0 transition-opacity duration-150 group-hover/document:opacity-100 focus-within:opacity-100 pointer-coarse:opacity-100">
                    {canRemint ? (
                      <Button
                        size="sm"
                        className="rounded-full"
                        variant="ghost"
                        onClick={() => remint.mutate(document.id)}
                        disabled={remint.isPending || remove.isPending}
                      >
                        <RefreshCw aria-hidden="true" /> Read again
                      </Button>
                    ) : null}
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      className="text-destructive hover:text-destructive"
                      aria-label={`Delete ${document.filename}`}
                      title={`Delete ${document.filename}`}
                      onClick={() => void requestDelete(document)}
                      disabled={remove.isPending || remint.isPending}
                    >
                      <Trash2 aria-hidden="true" />
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

// The stored status (extracted|minted|failed) in words: `documentStatusLabel`.
function DocumentStatus({ document }: { document: KBDocumentOut }) {
  const failed = document.ingest_status === "failed";
  const minted = document.ingest_status === "minted";
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1.5 rounded-full px-2 text-xs font-medium",
        failed && "bg-destructive/10 text-destructive",
        minted && "bg-emerald-600/10 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-300",
        !failed && !minted && "bg-muted text-muted-foreground",
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          failed && "bg-destructive",
          minted && "bg-emerald-600 dark:bg-emerald-400",
          !failed && !minted && "bg-muted-foreground/50",
        )}
      />
      {documentStatusLabel(document)}
    </span>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

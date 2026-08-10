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
  remintKbDocument,
  uploadKbDocument,
} from "@/lib/api";
import { formatAbsoluteDateTime } from "@/lib/format-date";
import type { KBDocumentOut } from "@/lib/types";
import { cn } from "@/lib/utils";

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

  const upload = useMutation({
    mutationFn: (file: File) => uploadKbDocument(entityId, file),
    onSuccess: (document) => {
      toast.success(
        document.ingest_status === "minted"
          ? "Document uploaded and drafts minted"
          : `Document uploaded (${document.ingest_status})`,
      );
      if (inputRef.current) inputRef.current.value = "";
      invalidate();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remint = useMutation({
    mutationFn: (documentId: string) => remintKbDocument(documentId),
    onSuccess: () => {
      toast.success("Document reprocessed");
      invalidate();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (documentId: string) => deleteKbDocument(documentId),
    onSuccess: () => {
      toast.success("Source document deleted");
      invalidate();
    },
    onError: (error: Error) => toast.error(error.message),
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
        "The source file will be removed. Points already minted from it remain in the Career KB.",
      confirmLabel: "Delete document",
      destructive: true,
    });
    if (accepted) remove.mutate(document.id);
  };

  return (
    <Card className="rounded-2xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileText className="size-4" aria-hidden="true" /> Source documents
          <Badge className="rounded-full" variant="secondary">
            {documents.length}
          </Badge>
        </CardTitle>
        <p className="text-muted-foreground text-sm">Evidence that can mint reviewable draft points.</p>
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
            accept=".pdf,.docx,.md,.markdown,.txt,.tex,.png,.jpg,.jpeg,.webp"
            onChange={(event) => receiveFile(event.target.files?.[0])}
            disabled={upload.isPending}
            aria-label="Upload source document"
          />
          <span className="mx-auto flex size-9 items-center justify-center rounded-full bg-background/80">
            <Upload className="text-muted-foreground size-4" aria-hidden="true" />
          </span>
          <p className="mt-2 text-sm font-medium">Drop a source file</p>
          <p className="text-muted-foreground mt-1 text-xs">PDF, DOCX, image, text, or Markdown · 10 MB max</p>
          <Button
            className="mt-3 rounded-full"
            size="sm"
            variant="secondary"
            onClick={() => inputRef.current?.click()}
            disabled={upload.isPending}
          >
            {upload.isPending ? "Extracting and minting…" : "Choose file"}
          </Button>
        </div>

        {documents.length === 0 ? (
          <div className="py-3 text-center">
            <p className="text-sm font-medium">No source documents yet</p>
            <p className="text-muted-foreground mt-1 text-xs">Uploads and their extraction status appear here.</p>
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
                        <DocumentStatus status={document.ingest_status} />
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
                        <RefreshCw aria-hidden="true" /> Re-mint
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

function DocumentStatus({ status }: { status: string }) {
  const failed = status === "failed";
  const minted = status === "minted";
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1.5 rounded-full px-2 text-xs font-medium capitalize",
        failed && "bg-destructive/10 text-destructive",
        minted && "bg-emerald-600/10 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300",
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
      {status}
    </span>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

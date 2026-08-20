"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadErrorState } from "@/components/load-error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { canApplyAsyncDraft, nextQueuedSave } from "@/lib/onboarding";
import type { SettingValue } from "@/lib/types";

export function TextSettingSection({
  anchorId,
  settingKey,
  title,
  description,
  placeholder,
  draftAction,
}: {
  anchorId?: string;
  settingKey: "persona";
  title: string;
  description: string;
  placeholder?: string;
  draftAction?: { label: string; endpoint: string; disabledReason?: string };
}) {
  const query = useQuery({
    queryKey: ["settings", settingKey],
    queryFn: () => apiFetch<SettingValue>(`/api/settings/${settingKey}`),
  });

  return (
    <Card id={anchorId}>
      {query.isError ? (
        <>
          <CardHeader>
            <CardTitle>{title}</CardTitle>
            <p className="text-muted-foreground text-xs">{description}</p>
          </CardHeader>
          <CardContent>
            <LoadErrorState
              className="py-8"
              title="Couldn't load this setting."
              detail={(query.error as Error)?.message}
              retrying={query.isFetching}
              onRetry={() => void query.refetch()}
            />
          </CardContent>
        </>
      ) : query.isLoading || !query.data ? (
        <>
          <CardHeader>
            <CardTitle>{title}</CardTitle>
            <p className="text-muted-foreground text-xs">{description}</p>
          </CardHeader>
          <CardContent>
            <Skeleton className="h-40 w-full" />
          </CardContent>
        </>
      ) : (
        <TextSettingEditor
          settingKey={settingKey}
          title={title}
          description={description}
          initial={query.data.value}
          placeholder={placeholder}
          draftAction={draftAction}
        />
      )}
    </Card>
  );
}

function TextSettingEditor({
  settingKey,
  title,
  description,
  initial,
  placeholder,
  draftAction,
}: {
  settingKey: "persona";
  title: string;
  description: string;
  initial: string;
  placeholder?: string;
  draftAction?: { label: string; endpoint: string; disabledReason?: string };
}) {
  const qc = useQueryClient();
  const [value, setValue] = useState(initial);
  const [savedValue, setSavedValue] = useState(initial);
  const valueRef = useRef(initial);
  const savedValueRef = useRef(initial);
  const editRevisionRef = useRef(0);
  const saveInFlightRef = useRef(false);
  const draftInFlightRef = useRef(false);
  const submittedValueRef = useRef<string | null>(null);
  const queuedSaveRef = useRef<string | null>(null);

  const save = useMutation({
    mutationFn: (next: string) =>
      apiFetch<SettingValue>(`/api/settings/${settingKey}`, {
        method: "PUT",
        body: JSON.stringify({ value: next }),
      }),
    onSuccess: (result, submitted) => {
      savedValueRef.current = result.value;
      setSavedValue(result.value);
      if (valueRef.current === submitted) {
        valueRef.current = result.value;
        setValue(result.value);
      }
      qc.setQueryData(["settings", settingKey], result);
      void qc.invalidateQueries({ queryKey: ["setup-status"] });
      toast.success(`${title} saved`);
    },
    onError: (err: Error) => toast.error(err.message),
    onSettled: () => {
      saveInFlightRef.current = false;
      submittedValueRef.current = null;

      const queued = queuedSaveRef.current;
      queuedSaveRef.current = null;
      if (queued !== null && queued !== savedValueRef.current) {
        saveInFlightRef.current = true;
        submittedValueRef.current = queued;
        save.mutate(queued);
      }
    },
  });
  const draft = useMutation({
    mutationFn: (requestRevision: number) => {
      if (!draftAction) throw new Error("No draft action is available.");
      return apiFetch<{ draft: string }>(draftAction.endpoint, {
        method: "POST",
      }).then((result) => ({ ...result, requestRevision }));
    },
    onSuccess: (result) => {
      if (
        !canApplyAsyncDraft(
          result.requestRevision,
          editRevisionRef.current,
        )
      ) {
        toast.info("Draft finished, but your newer edits were kept.");
        return;
      }
      valueRef.current = result.draft;
      setValue(result.draft);
      editRevisionRef.current += 1;
      toast.success("Draft ready to review");
    },
    onError: (err: Error) => toast.error(err.message),
    onSettled: () => {
      draftInFlightRef.current = false;
    },
  });

  const requestSave = (next: string) => {
    if (saveInFlightRef.current) {
      queuedSaveRef.current = nextQueuedSave(
        submittedValueRef.current,
        next,
      );
      return;
    }
    if (next === savedValueRef.current) return;

    saveInFlightRef.current = true;
    submittedValueRef.current = next;
    save.mutate(next);
  };

  const dirty = value !== savedValue;
  const requestDraft = () => {
    if (draftInFlightRef.current) return;
    draftInFlightRef.current = true;
    draft.mutate(editRevisionRef.current);
  };

  return (
    <>
      <CardHeader className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
        <div>
          <CardTitle>{title}</CardTitle>
          <p className="text-muted-foreground text-xs">{description}</p>
        </div>
        {draftAction ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={requestDraft}
            disabled={draft.isPending || Boolean(draftAction.disabledReason)}
            title={draftAction.disabledReason}
          >
            {draft.isPending ? <Loader2 className="animate-spin" /> : null}
            {draftAction.label}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        <Textarea
          rows={10}
          value={value}
          placeholder={placeholder}
          aria-label={title}
          onChange={(e) => {
            valueRef.current = e.target.value;
            setValue(e.target.value);
            editRevisionRef.current += 1;
          }}
          onBlur={() => {
            if (valueRef.current !== savedValueRef.current) {
              requestSave(valueRef.current);
            }
          }}
        />
        {dirty ? (
          <div className="mt-3 flex items-center justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => {
                valueRef.current = savedValueRef.current;
                setValue(savedValueRef.current);
                editRevisionRef.current += 1;
              }}
              disabled={save.isPending}
            >
              Discard
            </Button>
            <Button
              type="button"
              size="sm"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => requestSave(valueRef.current)}
              disabled={save.isPending}
            >
              {save.isPending ? <Loader2 className="animate-spin" /> : null}
              Save
            </Button>
          </div>
        ) : null}
      </CardContent>
    </>
  );
}

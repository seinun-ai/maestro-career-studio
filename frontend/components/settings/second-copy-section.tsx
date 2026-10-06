"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { SettingCard } from "@/components/settings/setting-card";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";

type SecondCopy = {
  enabled: boolean;
  open_until: string | null;
  last_paired_at: string | null;
};
const QUERY = ["settings", "second-copy"];
const PATH = "/api/settings/second-copy";

function usePairingClock(until: string | null | undefined) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!until) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [until]);
  return now;
}

function countdown(seconds: number) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function SecondCopyBody({ data, seconds, pending, act }: {
  data: SecondCopy;
  seconds: number;
  pending: boolean;
  act: (action: "allow" | "stop") => void;
}) {
  return (
    <div className="grid gap-4">
      {seconds > 0 ? (
        <div className="flex items-center gap-4">
          <p role="timer" aria-live="off" className="body-medium tabular-nums">
            Pairing allowed for {countdown(seconds)}
          </p>
          <Button variant="link" size="sm" pending={pending} onClick={() => act("stop")}>Stop</Button>
        </div>
      ) : (
        <Button variant="tonal" pending={pending} onClick={() => act("allow")}>
          Allow pairing for 10 minutes
        </Button>
      )}
      {data.last_paired_at && (
        <p className="body-medium text-muted-foreground" role="status">
          Paired with your bot at <time dateTime={data.last_paired_at}>
            {new Date(data.last_paired_at).toLocaleString()}
          </time>
        </p>
      )}
    </div>
  );
}

export function SecondCopySection() {
  const qc = useQueryClient();
  const setting = useQuery({
    queryKey: QUERY,
    queryFn: () => apiFetch<SecondCopy>(PATH),
    refetchInterval: (query) => {
      const until = query.state.data?.open_until;
      return until && Date.parse(until) > Date.now() ? 3000 : false;
    },
  });
  const now = usePairingClock(setting.data?.open_until);
  const save = useMutation({
    mutationFn: (action: "allow" | "stop") => apiFetch<{ open_until: string | null }>(PATH, {
      method: action === "allow" ? "POST" : "DELETE",
    }),
    onSuccess: (result) => {
      qc.setQueryData<SecondCopy>(QUERY, (old) => ({
        enabled: true, last_paired_at: old?.last_paired_at ?? null, ...result,
      }));
      void qc.invalidateQueries({ queryKey: QUERY });
    },
    onError: (error: Error) => toast.error(couldnt("change pairing", error)),
  });
  return (
    <SettingCard id="second-copy" title="Second copy" query={setting} skeleton="h-12 w-full"
      description="Lets your always-on copy fetch the sync key once, through its tunnel. Nothing to copy or paste."
      errorTitle="Couldn't load the second copy setting.">
      {(data) => <SecondCopyBody data={data} pending={save.isPending} act={save.mutate}
        seconds={data.open_until ? Math.max(0, Math.ceil((Date.parse(data.open_until) - now) / 1000)) : 0} />}
    </SettingCard>
  );
}

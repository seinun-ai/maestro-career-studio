"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { CopyButton } from "@/components/copy-button";
import { SettingCard } from "@/components/settings/setting-card";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { couldnt } from "@/lib/error-text";

type SecondCopy = {
  enabled: boolean;
  open_until: string | null;
  last_paired_at: string | null;
};
type Opened = { code: string; open_until: string | null };
const QUERY = ["settings", "second-copy"];
const PATH = "/api/settings/second-copy";
const PASTE = "Paste this code to your bot. It works once, for 10 minutes.";

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

function PairingCode({ code }: { code: string }) {
  return (
    <div className="grid gap-2">
      <p className="text-label-medium text-muted-foreground flex items-center gap-2">
        <CONCEPT_ICONS.laptop className="size-4 shrink-0" aria-hidden="true" />
        This laptop
      </p>
      <div className="flex items-center gap-2">
        <p className="font-mono text-headline-small tabular-nums tracking-wider">{code}</p>
        <CopyButton text={code} label="Copy pairing code" />
      </div>
      <p className="body-medium max-w-[65ch]">{PASTE}</p>
    </div>
  );
}

function PairingStatus({ at }: { at: string }) {
  return (
    <p className="body-medium text-muted-foreground flex items-center gap-2" role="status">
      <CONCEPT_ICONS.agentInbox className="size-4 shrink-0" aria-hidden="true" />
      Paired with your bot at <time dateTime={at}>{new Date(at).toLocaleString()}</time>
    </p>
  );
}

export function SecondCopyBody({ data, seconds, pending, code, act }: {
  data: SecondCopy;
  seconds: number;
  pending: boolean;
  code: string | null;
  act: (action: "allow" | "stop") => void;
}) {
  const visible = seconds > 0 ? code : null;
  return (
    <div className="grid gap-4">
      {visible ? <PairingCode code={visible} /> : null}
      {seconds > 0 ? (
        <div className="flex items-center gap-4">
          <p role="timer" aria-live="off" className="body-medium tabular-nums">
            Expires in {countdown(seconds)}
          </p>
          <Button variant="link" size="sm" pending={pending} onClick={() => act("stop")}>Stop</Button>
        </div>
      ) : null}
      {visible ? null : (
        <Button variant="tonal" pending={pending} onClick={() => act("allow")}>
          Show a pairing code
        </Button>
      )}
      {data.last_paired_at ? <PairingStatus at={data.last_paired_at} /> : null}
    </div>
  );
}

function rememberOpened(
  result: Opened | { open_until: string | null },
  action: "allow" | "stop",
  setCode: (code: string | null) => void,
) {
  if (action === "stop") setCode(null);
  if (action === "allow" && "code" in result) setCode(result.code);
}

export function SecondCopySection() {
  const qc = useQueryClient();
  const [code, setCode] = useState<string | null>(null);
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
    mutationFn: (action: "allow" | "stop") => action === "stop"
      ? apiFetch<{ open_until: string | null }>(PATH, { method: "DELETE" })
      : apiFetch<Opened>(PATH, { method: "POST" }),
    onSuccess: (result, action) => {
      rememberOpened(result, action, setCode);
      qc.setQueryData<SecondCopy>(QUERY, (old) => ({
        enabled: true, last_paired_at: old?.last_paired_at ?? null, open_until: result.open_until,
      }));
      void qc.invalidateQueries({ queryKey: QUERY });
    },
    onError: (error: Error) => toast.error(couldnt("change pairing", error)),
  });
  const until = setting.data?.open_until;
  const seconds = until ? Math.max(0, Math.ceil((Date.parse(until) - now) / 1000)) : 0;
  return (
    <SettingCard id="second-copy" title="Second copy" query={setting} skeleton="h-12 w-full"
      description={PASTE}
      errorTitle="Couldn't load the second copy setting.">
      {(data) => <SecondCopyBody data={data} pending={save.isPending} act={save.mutate}
        code={code} seconds={seconds} />}
    </SettingCard>
  );
}

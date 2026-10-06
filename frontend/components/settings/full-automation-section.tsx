"use client";

import { useId, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { LoadErrorState } from "@/components/load-error-state";
import { SettingCard } from "@/components/settings/setting-card";
import { ACTION_ROW, GROUP_HEADING, SwitchRow } from "@/components/settings/setting-layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { apiFetch } from "@/lib/api";
import { couldnt, loadErrorDetail } from "@/lib/error-text";
import { isLoadFailure } from "@/lib/query-state";
import type { AutoApplySettings, JobSiteLoginStatus, SettingEnvelope } from "@/lib/types";

type AutoApplySetting = SettingEnvelope<AutoApplySettings>;
const AUTO_APPLY_KEY = ["settings", "auto-apply"] as const;
const AUTOMATIONS_KEY = ["automations"] as const;
const LOGIN_KEY = ["settings", "job-site-login"] as const;
const LOGIN_PATH = "/api/settings/job-site-login";

export function FullAutomationSection() {
  const query = useQuery({
    queryKey: AUTO_APPLY_KEY,
    queryFn: () => apiFetch<AutoApplySetting>("/api/settings/auto-apply"),
  });
  return (
    <SettingCard
      id="full-automation"
      title="Full automation"
      description="When this is on, your connected agent submits a queued job without asking when its final review shows nothing to check. It asks you about the rest."
      errorTitle="Couldn't load full automation settings."
      skeleton="h-11 w-full"
      query={query}
    >
      {(data) => <FullAutomationControls initial={data.value} />}
    </SettingCard>
  );
}

function useFullAutomation() {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const asking = useRef(false);
  const save = useMutation({
    scope: { id: "settings-auto-apply" },
    mutationFn: (enabled: boolean) => {
      return apiFetch<AutoApplySetting>("/api/settings/full-automation", {
        method: "PUT",
        body: JSON.stringify({ value: enabled }),
      });
    },
    onSuccess: (result) => {
      qc.setQueryData(AUTO_APPLY_KEY, result);
      void qc.invalidateQueries({ queryKey: AUTOMATIONS_KEY });
      toast.success(result.value.full_automation ? "Full automation is on" : "Full automation is off");
    },
    onError: (error: Error) => toast.error(couldnt("save full automation settings", error)),
  });
  const saveOnce = useSingleFlight(save.mutate);
  const change = async (enabled: boolean) => {
    if (asking.current || save.isPending) return;
    asking.current = true;
    try {
      if (enabled && !(await confirm({
        title: "Turn on full automation?",
        description: "Your agent will submit queued jobs whose final review is clean, without asking each time. The daily limit still applies. You can turn this off at any time.",
        confirmLabel: "Turn on",
        cancelLabel: "Cancel",
        consent: true,
      }))) return;
      saveOnce(enabled);
    } finally {
      asking.current = false;
    }
  };
  return { change, pending: save.isPending };
}

function FullAutomationControls({ initial }: { initial: AutoApplySettings }) {
  const id = useId();
  const { change, pending } = useFullAutomation();
  return (
    <div className="grid gap-6">
      <SwitchRow htmlFor={id} label="Submit clean applications without asking">
        <Switch
          id={id}
          checked={initial.full_automation}
          disabled={pending}
          onCheckedChange={(checked) => void change(checked)}
        />
      </SwitchRow>
      {pending && <p role="status" className="text-muted-foreground text-body-small">Saving…</p>}
      <JobSiteLoginSection enabled={initial.full_automation} />
    </div>
  );
}

// Project both reads and writes before caching, even if a response gains extra fields.
function loginStatus({ email, password_set }: JobSiteLoginStatus): JobSiteLoginStatus {
  return { email, password_set };
}

function jobSiteLoginPayload(email: string, newPassword: string) {
  return { email, ...(newPassword ? { password: newPassword } : {}) };
}

function JobSiteLoginSection({ enabled }: { enabled: boolean }) {
  const login = useQuery({
    queryKey: LOGIN_KEY,
    queryFn: async () => loginStatus(await apiFetch<JobSiteLoginStatus>(LOGIN_PATH)),
    enabled,
  });
  return (
    <section className="grid gap-4" aria-label="Job-site login" hidden={!enabled}>
      <div className="grid gap-1.5">
        <h3 className={GROUP_HEADING}>Job-site login</h3>
        <p className="text-muted-foreground text-body-small">
          {"Used only for job-site accounts. Your agent gets it while full automation is on, so it passes through your agent's AI provider. Use it for nothing else."}
        </p>
      </div>
      {isLoadFailure(login) && !login.data ? (
        <LoadErrorState
          className="py-8"
          title="Couldn't load your job-site login."
          detail={loadErrorDetail(login.error)}
          retrying={login.isFetching}
          onRetry={() => void login.refetch()}
        />
      ) : !login.data ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <JobSiteLoginEditor initial={login.data} />
      )}
    </section>
  );
}

function useJobSiteLoginEditor(initial: JobSiteLoginStatus) {
  const qc = useQueryClient();
  const [emailDraft, setEmailDraft] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const email = emailDraft ?? initial.email ?? "";
  const dirty = email !== (initial.email ?? "") || newPassword !== "";
  useLeaveGuard(dirty || busy);

  // Direct requests keep the password out of react-query's mutation variables/cache.
  const write = async (clear: boolean) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    try {
      const result = clear
        ? await apiFetch<void>(LOGIN_PATH, { method: "DELETE" })
          .then(() => ({ email: null, password_set: false }))
        : await apiFetch<JobSiteLoginStatus>(LOGIN_PATH, {
          method: "PUT",
          body: JSON.stringify(jobSiteLoginPayload(email, newPassword)),
        });
      qc.setQueryData(LOGIN_KEY, loginStatus(result));
      setEmailDraft(null);
      setNewPassword("");
      toast.success(clear ? "Job-site login cleared" : "Job-site login saved");
    } catch (error) {
      toast.error(couldnt(clear ? "clear the job-site login" : "save the job-site login", error));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };
  return { email, newPassword, setEmailDraft, setNewPassword, busy, dirty,
    save: () => write(false), clear: () => write(true) };
}

function JobSiteLoginEditor({ initial }: { initial: JobSiteLoginStatus }) {
  const editor = useJobSiteLoginEditor(initial);
  return (
    <form className="grid gap-6" onSubmit={(event) => {
      event.preventDefault();
      if (editor.dirty && !editor.busy) void editor.save();
    }}>
      <JobSiteLoginFields editor={editor} passwordSet={initial.password_set} />
      <JobSiteLoginActions editor={editor} saved={Boolean(initial.email || initial.password_set)} />
    </form>
  );
}

type LoginEditor = ReturnType<typeof useJobSiteLoginEditor>;

function JobSiteLoginFields({ editor, passwordSet }: { editor: LoginEditor; passwordSet: boolean }) {
  const { email, newPassword, setEmailDraft, setNewPassword, busy } = editor;
  const id = useId();
  const hintId = `${id}-password-hint`;
  return (
    <div className="grid gap-4 @lg/setting:grid-cols-2">
      <div className="grid gap-1.5">
        <Label htmlFor={`${id}-email`}>Email</Label>
        <Input
          id={`${id}-email`}
          type="email"
          autoComplete="email"
          maxLength={320}
          value={email}
          readOnly={busy}
          onChange={(event) => setEmailDraft(event.target.value)}
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${id}-password`}>Password</Label>
        <p id={hintId} className="text-muted-foreground text-body-small">
          {passwordSet ? "A password is saved. Type a new one to replace it." : "At least 8 characters."}
        </p>
        <Input
          id={`${id}-password`}
          type="password"
          autoComplete="new-password"
          aria-describedby={hintId}
          minLength={8}
          maxLength={200}
          value={newPassword}
          readOnly={busy}
          onChange={(event) => setNewPassword(event.target.value)}
        />
      </div>
    </div>
  );
}

function JobSiteLoginActions({ editor, saved }: { editor: LoginEditor; saved: boolean }) {
  const { busy, dirty } = editor;
  const confirm = useConfirm();
  const clear = async () => {
    if (busy || !(await confirm({
      title: "Clear job-site login?",
      description: "This removes the saved email and password for job-site accounts.",
      confirmLabel: "Clear",
      destructive: true,
    }))) return;
    await editor.clear();
  };
  return (
    <div className={ACTION_ROW}>
      <Button
        type="button"
        variant="outline"
        focusableWhenDisabled
        disabled={busy || (!saved && !dirty)}
        onClick={() => void clear()}
      >
        Clear
      </Button>
      <Button type="submit" focusableWhenDisabled disabled={!dirty || busy}>
        {busy ? "Saving…" : "Save"}
      </Button>
    </div>
  );
}

"use client";

import { useId, type RefObject } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Plus } from "lucide-react";
import { toast } from "sonner";

import { useRoleCategories } from "@/components/role-category-picker";
import { RolePicker, favoredRoleFromTag, roleIdentity } from "@/components/role-picker";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useBaseResumes } from "@/hooks/use-base-resume-label";
import { useMoney } from "@/hooks/use-money";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import type { FavoredRole, JobPreferences, MarketSettingResponse, SettingEnvelope } from "@/lib/types";
import { useAutosave } from "@/lib/use-autosave";

type Place = { home: string; apply_in: string[] };

const WORK_MODES = [
  { value: "onsite", label: "On-site" },
  { value: "hybrid", label: "Hybrid" },
  { value: "remote", label: "Remote" },
] as const;

/**
 * Step 3, where and what. You live in (one country: the home currency and date format) and You apply in
 * (chips, each with its own work-permit answers) save to the market setting (`PUT /api/settings/market`);
 * the roles you want, offered from your base resumes' roles, and the work mode save to job preferences
 * (`PUT /api/settings/job-preferences`). Both save as you go. Pay follows where you live unless you chose a
 * currency (the money setting, read here, never written).
 */
export function SetupWhereStep({
  market,
  prefs,
  headingRef,
}: {
  market: MarketSettingResponse;
  prefs: JobPreferences;
  headingRef: RefObject<HTMLHeadingElement | null>;
}) {
  const qc = useQueryClient();
  const money = useMoney();
  const homeId = useId();
  const homeHintId = useId();
  const applyLabelId = useId();
  const applyHintId = useId();
  const modeLabelId = useId();
  const markets = market.markets ?? [];

  const saveMarket = useMutation({
    mutationFn: (next: Place) =>
      apiFetch<MarketSettingResponse>("/api/settings/market", {
        method: "PUT",
        body: JSON.stringify({ value: next }),
      }),
    onSuccess: (result) => {
      qc.setQueryData(["settings", "market"], (prev: MarketSettingResponse | undefined) =>
        prev ? { ...prev, ...result } : prev,
      );
      // The home currency, the questions each country asks and the work-permit view all follow.
      for (const key of [["setup-status"], ["settings", "market"], ["settings", "money"], ["settings", "autofill"]]) {
        void qc.invalidateQueries({ queryKey: key });
      }
    },
    onError: (err: Error) => toast.error(couldnt("save your countries", err)),
  });
  const place = useAutosave<Place>({ home: market.home, apply_in: market.apply_in }, (next) =>
    saveMarket.mutateAsync(next),
  );

  const savePrefs = useMutation({
    // role_categories is the server's projection of favored_roles: it recomputes it on every write.
    mutationFn: (next: JobPreferences) =>
      apiFetch<SettingEnvelope<JobPreferences>>("/api/settings/job-preferences", {
        method: "PUT",
        body: JSON.stringify({ value: { ...next, role_categories: undefined } }),
      }),
    onSuccess: (result) => {
      qc.setQueryData(["settings", "job-preferences"], result);
      void qc.invalidateQueries({ queryKey: ["setup-status"] });
    },
    onError: (err: Error) => toast.error(couldnt("save your job preferences", err)),
  });
  const wants = useAutosave<JobPreferences>(prefs, (next) => savePrefs.mutateAsync(next));

  const roles = useRoleCategories();
  const bases = useBaseResumes();
  const picked = new Set(wants.value.favored_roles.map(roleIdentity));
  // Your base resumes' roles, the ones not picked yet, each once.
  const suggested = [
    ...new Map(
      (bases.data ?? [])
        .map((b) => favoredRoleFromTag(b.role_category, b.role_label, roles.data))
        .filter((role): role is FavoredRole => role !== null && !picked.has(roleIdentity(role)))
        .map((role) => [roleIdentity(role), role]),
    ).values(),
  ];

  const home = markets.find((m) => m.key === place.value.home);
  const applyIn = place.value.apply_in;
  const setHome = (next: string) =>
    place.update((current) => ({
      home: next,
      // While you apply only where you live, the list follows you (Profile's Where you apply does the same).
      apply_in: current.apply_in.length === 1 && current.apply_in[0] === current.home ? [next] : current.apply_in,
    }));
  const toggleCountry = (key: string) =>
    place.update((current) =>
      current.apply_in.includes(key)
        ? current.apply_in.length === 1
          ? current // At least one: an empty list reads as where you live anyway.
          : { ...current, apply_in: current.apply_in.filter((k) => k !== key) }
        : { ...current, apply_in: [...current.apply_in, key] },
    );

  return (
    <section aria-labelledby="setup-where-title" className="flex flex-col gap-7">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1.5">
          <h2 id="setup-where-title" ref={headingRef} tabIndex={-1} className="text-headline-small outline-none">
            Where and what you&apos;re looking for
          </h2>
          <p className="max-w-[65ch] text-body-medium text-muted-foreground">
            Your countries set your currency and the questions job forms ask you.
          </p>
        </div>
        <AutosaveStatus
          pending={place.pending || wants.pending}
          failed={place.failed || wants.failed}
          onRetry={() => {
            if (place.failed) place.retry();
            if (wants.failed) wants.retry();
          }}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,16rem)_minmax(0,1fr)]">
        <div className="grid content-start gap-1.5">
          <Label htmlFor={homeId}>You live in</Label>
          <p id={homeHintId} className="text-body-small text-muted-foreground">
            {money.home ? `Pay shows in ${money.home}.` : "Sets your home currency and date format."}
          </p>
          <Select value={place.value.home} onValueChange={(next) => next && setHome(String(next))}>
            <SelectTrigger id={homeId} aria-describedby={homeHintId} className="w-full">
              <SelectValue>{home ? home.label : place.value.home}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {markets.map((m) => (
                <SelectItem key={m.key} value={m.key}>
                  {m.label} ({m.currency})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid content-start gap-1.5">
          <span id={applyLabelId} className="text-label-large">
            You apply in
          </span>
          <p id={applyHintId} className="text-body-small text-muted-foreground">
            {applyIn.length === 1
              ? "1 country, with its own work-permit answers. Keep at least one."
              : `${applyIn.length} countries, each with its own work-permit answers.`}
          </p>
          <div role="group" aria-labelledby={applyLabelId} aria-describedby={applyHintId} className="flex flex-wrap gap-2">
            {markets.map((m) => {
              const on = applyIn.includes(m.key);
              return (
                <Button
                  key={m.key}
                  type="button"
                  size="sm"
                  variant={on ? "tonal" : "outline"}
                  aria-pressed={on}
                  onClick={() => toggleCountry(m.key)}
                >
                  {on ? <Check aria-hidden="true" /> : null}
                  {m.label}
                </Button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="grid gap-2">
        <Label htmlFor="setup-roles">Roles you want</Label>
        <RolePicker
          mode="multiple"
          id="setup-roles"
          value={wants.value.favored_roles}
          onValueChange={(next) => wants.update((current) => ({ ...current, favored_roles: next }))}
          roleCategories={roles.data}
        />
        {suggested.length > 0 ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-body-small text-muted-foreground">From your resumes</span>
            {suggested.map((role) => (
              <Button
                key={roleIdentity(role)}
                type="button"
                size="sm"
                variant="outline"
                onClick={() =>
                  wants.update((current) => ({ ...current, favored_roles: [...current.favored_roles, role] }))
                }
              >
                <Plus aria-hidden="true" />
                {role.label}
              </Button>
            ))}
          </div>
        ) : null}
      </div>

      <div className="grid gap-2">
        <span id={modeLabelId} className="text-label-large">
          Work mode
        </span>
        <div role="group" aria-labelledby={modeLabelId} className="flex flex-wrap gap-2">
          {WORK_MODES.map((mode) => {
            const on = wants.value.remote === mode.value;
            return (
              <Button
                key={mode.value}
                type="button"
                size="sm"
                variant={on ? "tonal" : "outline"}
                aria-pressed={on}
                // One mode; pressing the chosen one again is no preference.
                onClick={() => wants.update((current) => ({ ...current, remote: on ? null : mode.value }))}
              >
                {on ? <Check aria-hidden="true" /> : null}
                {mode.label}
              </Button>
            );
          })}
        </div>
      </div>
    </section>
  );
}

"use client";

import { useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { toast } from "sonner";

import { TileCard, type TileView } from "@/components/profile/tile";
import { RolePicker } from "@/components/role-picker";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { SettingCardAction } from "@/components/settings/setting-card";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { useMoney } from "@/hooks/use-money";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { useAutosave } from "@/lib/use-autosave";
import type {
  FavoredRole,
  JobPreferences,
  RoleCategory,
  SettingEnvelope,
} from "@/lib/types";

type JobPreferencesSetting = SettingEnvelope<JobPreferences>;

// "No preference" writes null. A stored "any" (the old second option that
// meant the same) reads "No preference" too; nothing migrates it.
const NO_PREFERENCE = "__no_preference__";
const REMOTE_OPTIONS = ["remote", "hybrid", "onsite"] as const;
const EMPLOYMENT_TYPES = ["full_time", "contract", "part_time", "internship"] as const;
const EMPLOYMENT_LABEL = {
  full_time: "Full-time",
  contract: "Contract",
  part_time: "Part-time",
  internship: "Internship",
} as const;
const REMOTE_LABEL = {
  remote: "Remote",
  hybrid: "Hybrid",
  onsite: "On-site",
} as const;

function isRemoteOption(value: string): value is (typeof REMOTE_OPTIONS)[number] {
  return (REMOTE_OPTIONS as readonly string[]).includes(value);
}

export function useJobPreferencesQuery() {
  return useQuery({
    queryKey: ["settings", "job-preferences"],
    queryFn: () =>
      apiFetch<JobPreferencesSetting>("/api/settings/job-preferences"),
  });
}

/** Each answer Jobs you want holds, set or not: what the tile counts. */
function setCount(p: JobPreferences): number {
  return [
    p.favored_roles.length > 0,
    p.years_experience != null,
    p.remote != null && isRemoteOption(p.remote),
    p.locations.length > 0,
    p.min_salary?.amount != null,
    p.employment_types.length > 0,
  ].filter(Boolean).length;
}

/** Jobs you want: the roles, years, work location, places, lowest pay and job types (job preferences),
 *  which suggest base resumes. Saves as you go. */
export function useJobsTile(done: boolean | undefined): TileView {
  const preferences = useJobPreferencesQuery();
  const value = preferences.data?.value;
  const roles = value?.favored_roles.map((role) => role.label) ?? [];
  const mode = value?.remote && isRemoteOption(value.remote) ? REMOTE_LABEL[value.remote] : null;
  const words = [roles.slice(0, 2).join(", "), mode].filter(Boolean).join(" · ");
  return {
    state: done
      ? { kind: "ready" }
      : value
        ? { kind: "count", text: `${setCount(value)} of 6` }
        : { kind: "none" },
    summary: <span className="line-clamp-2">{value ? words || "No roles picked yet" : "Loading…"}</span>,
    note: "Used to suggest base resumes",
    panel: <JobsCard />,
  };
}

function JobsCard() {
  const preferences = useJobPreferencesQuery();
  // Not gated through `also`: the picker degrades to free text without the
  // catalog, so a slow or failed role fetch must not hold up the whole card.
  const roles = useQuery({
    queryKey: ["role-categories"],
    queryFn: () => apiFetch<RoleCategory[]>("/api/role-categories"),
  });

  return (
    <TileCard
      tile="jobs"
      description="The jobs you want. Used to suggest base resumes."
      errorTitle="Couldn't load your job preferences."
      skeleton="h-56 w-full"
      query={preferences}
    >
      {(data) => (
        <JobPreferencesEditor
          initial={data.value}
          roleCategories={roles.data}
        />
      )}
    </TileCard>
  );
}

function JobPreferencesEditor({
  initial,
  roleCategories,
}: {
  initial: JobPreferences;
  roleCategories?: RoleCategory[];
}) {
  const qc = useQueryClient();
  const money = useMoney();
  const employmentLabelId = useId();
  const [locationsText, setLocationsText] = useState(initial.locations.join("\n"));

  const save = useMutation({
    mutationFn: (next: JobPreferences) => {
      // role_categories is a projection of favored_roles that the server
      // recomputes on every write, so our copy is redundant at best and a
      // contradiction at worst. JSON.stringify drops the undefined.
      const value = { ...next, role_categories: undefined };
      return apiFetch<JobPreferencesSetting>("/api/settings/job-preferences", {
        method: "PUT",
        body: JSON.stringify({ value }),
      });
    },
    onSuccess: (result) => {
      qc.setQueryData(["settings", "job-preferences"], result);
      qc.invalidateQueries({ queryKey: ["setup-status"] });
    },
    // Errors still toast: a FAILED save is exactly the thing you must notice.
    onError: (err: Error) => toast.error(couldnt("save your job preferences", err)),
  });

  const {
    value: preferences,
    update,
    pending,
    failed,
    retry,
  } = useAutosave(initial, (next) => save.mutateAsync(next));
  useLeaveGuard(failed);

  const toggleEmployment = (value: string) => {
    update((current) => ({
      ...current,
      employment_types: current.employment_types.includes(value)
        ? current.employment_types.filter((item) => item !== value)
        : [...current.employment_types, value],
    }));
  };
  const remote =
    preferences.remote && isRemoteOption(preferences.remote) ? preferences.remote : NO_PREFERENCE;

  // Minimum salary is an amount in a currency, your home one unless you pick another; the list is the
  // currencies pay can be compared in (the ECB's), plus your own.
  const minSalary = preferences.min_salary;
  const salaryCurrency = minSalary?.currency ?? money.home ?? null;
  const currencies = [
    ...new Set(
      [salaryCurrency, money.home, money.rates?.base, ...Object.keys(money.rates?.rates ?? {})].filter(
        (code): code is string => Boolean(code),
      ),
    ),
  ].sort();

  const setFavoredRoles = (next: FavoredRole[]) => {
    update((current) => ({ ...current, favored_roles: next }));
  };

  return (
    <div className="grid gap-6">
      <SettingCardAction>
        <AutosaveStatus pending={pending} failed={failed} onRetry={retry} />
      </SettingCardAction>
      <div className="grid gap-1.5">
        <Label htmlFor="job-preferences-roles" optional>
          Roles you want
        </Label>
        <RolePicker
          mode="multiple"
          id="job-preferences-roles"
          value={preferences.favored_roles}
          onValueChange={setFavoredRoles}
          roleCategories={roleCategories}
        />
      </div>

      <div className="grid items-start gap-4 @lg/setting:grid-cols-2">
        <div className="grid gap-1.5">
          <Label htmlFor="job-preferences-years" optional>
            Years of experience
          </Label>
          <Input
            id="job-preferences-years"
            type="number"
            min={0}
            max={60}
            value={preferences.years_experience ?? ""}
            onChange={(event) => {
              const raw = event.target.value;
              update((current) => {
                if (raw === "") {
                  return { ...current, years_experience: null };
                }
                const n = Number(raw);
                if (Number.isNaN(n)) return current;
                return {
                  ...current,
                  years_experience: Math.min(60, Math.max(0, Math.trunc(n))),
                };
              });
            }}
          />
        </div>

        <div className="grid gap-1.5">
          <Label htmlFor="job-preferences-remote" optional>
            Work location
          </Label>
          <Select
            value={remote}
            onValueChange={(value) =>
              update((current) => ({
                ...current,
                remote: value !== null && isRemoteOption(value) ? value : null,
              }))
            }
          >
            <SelectTrigger id="job-preferences-remote" className="w-full">
              <SelectValue>
                {remote === NO_PREFERENCE ? "No preference" : REMOTE_LABEL[remote]}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NO_PREFERENCE}>No preference</SelectItem>
              {REMOTE_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {REMOTE_LABEL[option]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid gap-1.5">
          <Label htmlFor="job-preferences-locations" optional>
            Locations
          </Label>
          <p id="job-preferences-locations-hint" className="text-muted-foreground text-body-small">
            One location per line.
          </p>
          <Textarea
            aria-describedby="job-preferences-locations-hint"
            id="job-preferences-locations"
            value={locationsText}
            rows={2}
            onChange={(event) => {
              const value = event.target.value;
              setLocationsText(value);
              update((current) => ({
                ...current,
                locations: value
                  .split(/\r?\n/)
                  .map((location) => location.trim())
                  .filter(Boolean),
              }));
            }}
          />
        </div>

        <div className="grid gap-1.5">
          <Label htmlFor="job-preferences-min-salary" optional>
            Minimum salary
          </Label>
          <p id="job-preferences-min-salary-hint" className="text-muted-foreground text-body-small">
            A year.
            {minSalary?.text && minSalary.amount == null
              ? ` You wrote “${minSalary.text}”. Add it as a number to compare pay.`
              : null}
          </p>
          <div className="flex gap-2">
            <Input
              aria-describedby="job-preferences-min-salary-hint"
              id="job-preferences-min-salary"
              type="number"
              min={0}
              inputMode="numeric"
              value={minSalary?.amount ?? ""}
              onChange={(event) => {
                const raw = event.target.value;
                const amount = raw === "" ? null : Math.max(0, Math.trunc(Number(raw)));
                if (amount !== null && Number.isNaN(amount)) return;
                update((current) => ({
                  ...current,
                  min_salary:
                    amount === null
                      ? null
                      : { amount, currency: current.min_salary?.currency ?? salaryCurrency, text: null },
                }));
              }}
            />
            <Select
              value={salaryCurrency ?? ""}
              onValueChange={(value) =>
                update((current) => ({
                  ...current,
                  min_salary: {
                    amount: current.min_salary?.amount ?? null,
                    currency: value || null,
                    text: current.min_salary?.text ?? null,
                  },
                }))
              }
            >
              <SelectTrigger aria-label="Currency" className="w-28">
                <SelectValue>{salaryCurrency ?? ""}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {currencies.map((code) => (
                  <SelectItem key={code} value={code}>
                    {code}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      <div className="grid gap-1.5">
        <Label id={employmentLabelId} optional>
          Job types
        </Label>
        <div role="group" aria-labelledby={employmentLabelId} className="flex flex-wrap gap-2">
          {EMPLOYMENT_TYPES.map((type) => {
            const selected = preferences.employment_types.includes(type);
            return (
              <Button
                key={type}
                type="button"
                size="sm"
                variant={selected ? "tonal" : "outline"}
                aria-pressed={selected}
                onClick={() => toggleEmployment(type)}
              >
                {selected && <Check />}
                {EMPLOYMENT_LABEL[type]}
              </Button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

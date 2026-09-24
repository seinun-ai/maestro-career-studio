"use client";

import { useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { toast } from "sonner";

import { RolePicker } from "@/components/role-picker";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { SettingCard, SettingCardAction } from "@/components/settings/setting-card";
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
import { useAutosave } from "@/lib/use-autosave";
import type {
  FavoredRole,
  JobPreferences,
  RoleCategory,
  SettingEnvelope,
} from "@/lib/types";

type JobPreferencesSetting = SettingEnvelope<JobPreferences>;

const NOT_SPECIFIED = "__not_specified__";
const REMOTE_OPTIONS = ["remote", "hybrid", "onsite", "any"] as const;
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
  any: "Any",
} as const;

function isRemoteOption(
  value: string,
): value is NonNullable<JobPreferences["remote"]> {
  return (REMOTE_OPTIONS as readonly string[]).includes(value);
}

export function JobPreferencesSection() {
  const preferences = useQuery({
    queryKey: ["settings", "job-preferences"],
    queryFn: () =>
      apiFetch<JobPreferencesSetting>("/api/settings/job-preferences"),
  });
  // Not gated through `also`: the picker degrades to free text without the
  // catalog, so a slow or failed role fetch must not hold up the whole card.
  const roles = useQuery({
    queryKey: ["role-categories"],
    queryFn: () => apiFetch<RoleCategory[]>("/api/role-categories"),
  });

  return (
    <SettingCard
      id="job-preferences"
      title="Job preferences"
      description="Roles and conditions you're targeting. Drives base-resume suggestions."
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
    </SettingCard>
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
    onError: (err: Error) => toast.error(err.message),
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
  const remote = preferences.remote ?? NOT_SPECIFIED;

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
          Favored roles
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
            Remote
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
                {remote === NOT_SPECIFIED
                  ? "Not specified"
                  : isRemoteOption(remote)
                    ? REMOTE_LABEL[remote]
                    : remote}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NOT_SPECIFIED}>Not specified</SelectItem>
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
          <p id="job-preferences-locations-hint" className="text-muted-foreground text-xs">
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
            Min salary
          </Label>
          <Input
            id="job-preferences-min-salary"
            value={preferences.min_salary ?? ""}
            onChange={(event) =>
              update((current) => ({
                ...current,
                min_salary: event.target.value || null,
              }))
            }
          />
        </div>
      </div>

      <div className="grid gap-1.5">
        <Label id={employmentLabelId} optional>
          Employment types
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

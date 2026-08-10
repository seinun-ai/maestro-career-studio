"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { AutosaveStatus } from "@/components/settings/autosave-status";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import type { JobPreferences, RoleCategory } from "@/lib/types";

type JobPreferencesSetting = { key: string; value: JobPreferences };

const NOT_SPECIFIED = "__not_specified__";
const LEVELS = ["junior", "mid", "senior", "staff", "lead"];
const REMOTE_OPTIONS = ["remote", "hybrid", "onsite", "any"] as const;
const EMPLOYMENT_TYPES = ["full_time", "contract", "part_time", "internship"];

function humanize(value: string) {
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

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
  const roles = useQuery({
    queryKey: ["role-categories"],
    queryFn: () => apiFetch<RoleCategory[]>("/api/role-categories"),
  });

  return (
    <Card id="job-preferences">
      <CardHeader>
        <CardTitle>Job preferences</CardTitle>
        <p className="text-muted-foreground text-xs">
          Roles and conditions you&apos;re targeting. Drives base-resume
          suggestions.
        </p>
      </CardHeader>
      <CardContent>
        {preferences.isLoading || !preferences.data ? (
          <Skeleton className="h-56 w-full" />
        ) : (
          <JobPreferencesEditor
            initial={preferences.data.value}
            roleCategories={roles.data}
          />
        )}
      </CardContent>
    </Card>
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
  const [preferences, setPreferences] = useState(initial);
  const [locationsText, setLocationsText] = useState(initial.locations.join("\n"));
  const queuedPreferences = useRef(initial);
  const inFlightPreferences = useRef<JobPreferences | null>(null);
  const save = useMutation({
    mutationFn: (next: JobPreferences) =>
      apiFetch<JobPreferencesSetting>("/api/settings/job-preferences", {
        method: "PUT",
        body: JSON.stringify({ value: next }),
      }),
    onSuccess: (result) => {
      if (queuedPreferences.current === inFlightPreferences.current) {
        qc.setQueryData(["settings", "job-preferences"], result);
      }
      qc.invalidateQueries({ queryKey: ["setup-status"] });
    },
    // Errors still toast: a FAILED save is exactly the thing you must notice.
    onError: (err: Error) => toast.error(err.message),
    onSettled: () => {
      if (queuedPreferences.current !== inFlightPreferences.current) {
        flush();
      } else {
        inFlightPreferences.current = null;
      }
    },
  });

  const flush = () => {
    const next = queuedPreferences.current;
    inFlightPreferences.current = next;
    save.mutate(next);
  };
  const update = (getNext: (current: JobPreferences) => JobPreferences) => {
    const next = getNext(queuedPreferences.current);
    queuedPreferences.current = next;
    setPreferences(next);
    if (inFlightPreferences.current === null) flush();
  };
  const toggle = (
    key: "role_categories" | "employment_types" | "levels",
    value: string,
  ) => {
    update((current) => ({
      ...current,
      [key]: current[key].includes(value)
        ? current[key].filter((item) => item !== value)
        : [...current[key], value],
    }));
  };
  const selectableRoles = (roleCategories ?? []).filter(
    (category) => !category.reserved || category.key === "other",
  );
  const remote = preferences.remote ?? NOT_SPECIFIED;

  return (
    <div className="space-y-5">
      {/* Status sits with the fields rather than in the card header, because
          the mutation lives in this component — lifting it would mean syncing
          state upward through an effect for a cosmetic placement. */}
      <div className="flex justify-end">
        <AutosaveStatus pending={save.isPending} />
      </div>
      <div className="grid gap-1.5">
        <Label className="text-xs">
          Favored roles<span className="text-muted-foreground"> · optional</span>
        </Label>
        <div className="flex flex-wrap gap-2">
          {selectableRoles.map((category) => {
            const selected = preferences.role_categories.includes(category.key);
            return (
              <Button
                key={category.key}
                type="button"
                size="sm"
                variant={selected ? "default" : "outline"}
                onClick={() => toggle("role_categories", category.key)}
                aria-pressed={selected}
                disabled={!roleCategories}
              >
                {category.label}
              </Button>
            );
          })}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label className="text-xs">
            Level<span className="text-muted-foreground"> · optional</span>
          </Label>
          <div className="flex flex-wrap gap-2">
            {LEVELS.map((option) => {
              const selected = preferences.levels.includes(option);
              return (
                <Button
                  key={option}
                  type="button"
                  size="sm"
                  variant={selected ? "default" : "outline"}
                  onClick={() => toggle("levels", option)}
                  aria-pressed={selected}
                >
                  {humanize(option)}
                </Button>
              );
            })}
          </div>
        </div>

        <div className="grid gap-1.5">
          <Label htmlFor="job-preferences-remote" className="text-xs">
            Remote<span className="text-muted-foreground"> · optional</span>
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
                {remote === NOT_SPECIFIED ? "Not specified" : humanize(remote)}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NOT_SPECIFIED}>Not specified</SelectItem>
              {REMOTE_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {humanize(option)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid gap-1.5">
          <Label htmlFor="job-preferences-locations" className="text-xs">
            Locations<span className="text-muted-foreground"> · optional</span>
          </Label>
          <Textarea
            id="job-preferences-locations"
            value={locationsText}
            rows={2}
            placeholder={"e.g. Chicago, IL\nNew York, NY"}
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
          <p className="text-muted-foreground text-xs">One location per line.</p>
        </div>

        <div className="grid gap-1.5">
          <Label htmlFor="job-preferences-min-salary" className="text-xs">
            Min salary<span className="text-muted-foreground"> · optional</span>
          </Label>
          <Input
            id="job-preferences-min-salary"
            value={preferences.min_salary ?? ""}
            placeholder="e.g. $140,000"
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
        <Label className="text-xs">
          Employment types<span className="text-muted-foreground"> · optional</span>
        </Label>
        <div className="flex flex-wrap gap-2">
          {EMPLOYMENT_TYPES.map((type) => {
            const selected = preferences.employment_types.includes(type);
            return (
              <Button
                key={type}
                type="button"
                size="sm"
                variant={selected ? "default" : "outline"}
                onClick={() => toggle("employment_types", type)}
                aria-pressed={selected}
              >
                {humanize(type)}
              </Button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

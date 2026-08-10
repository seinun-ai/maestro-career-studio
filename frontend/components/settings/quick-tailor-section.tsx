"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

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
import { Switch } from "@/components/ui/switch";
import { apiFetch } from "@/lib/api";
import type { BaseResumeSummary } from "@/lib/types";

type QuickTailorProfile = {
  keywords_into_skills: boolean;
  mirror_wording: boolean;
  summary_rename: boolean;
  project_keyword_injection: boolean;
  default_base_resume: string;
  instruction: string;
};

type QuickTailorSetting = { key: string; value: QuickTailorProfile };
type BooleanPreference = Exclude<
  keyof QuickTailorProfile,
  "default_base_resume" | "instruction"
>;

const SWITCH_ROWS: {
  key: BooleanPreference;
  label: string;
}[] = [
  {
    key: "keywords_into_skills",
    label: "Add missing JD keywords to skills",
  },
  {
    key: "mirror_wording",
    label: "Mirror JD wording where evidence exists",
  },
  {
    key: "summary_rename",
    label: "Refresh summary / title alignment",
  },
  {
    key: "project_keyword_injection",
    label: "Allow placements into projects",
  },
];

export function QuickTailorSection() {
  const profile = useQuery({
    queryKey: ["settings", "quick-tailor"],
    queryFn: () =>
      apiFetch<QuickTailorSetting>("/api/settings/quick-tailor"),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Quick tailor</CardTitle>
        <p className="text-muted-foreground text-xs">
          What one-shot tailoring is allowed to change. Used by Quick tailor on the gap
          analysis page and by the browser extension&apos;s Fast tailor.
        </p>
      </CardHeader>
      <CardContent>
        {profile.isLoading || !profile.data ? (
          <Skeleton className="h-48 w-full" />
        ) : (
          <QuickTailorEditor initial={profile.data.value} />
        )}
      </CardContent>
    </Card>
  );
}

function QuickTailorEditor({ initial }: { initial: QuickTailorProfile }) {
  const qc = useQueryClient();
  const [profile, setProfile] = useState(initial);
  const [dirty, setDirty] = useState(false);
  const [lastInitial, setLastInitial] = useState(initial);

  const baseResumes = useQuery({
    queryKey: ["base-resumes"],
    queryFn: () => apiFetch<BaseResumeSummary[]>("/api/base-resumes"),
  });

  if (!dirty && initial !== lastInitial) {
    setLastInitial(initial);
    setProfile(initial);
  }

  const selectedBase = baseResumes.data?.find(
    (resume) => resume.slug === profile.default_base_resume,
  );

  const setField = <K extends keyof QuickTailorProfile>(
    key: K,
    value: QuickTailorProfile[K],
  ) => {
    setDirty(true);
    setProfile((current) => ({ ...current, [key]: value }));
  };

  const save = useMutation({
    mutationFn: () =>
      apiFetch<QuickTailorSetting>("/api/settings/quick-tailor", {
        method: "PUT",
        body: JSON.stringify({ value: profile }),
      }),
    onSuccess: (result) => {
      qc.setQueryData(["settings", "quick-tailor"], result);
      setDirty(false);
      toast.success("Quick-tailor preferences saved");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <div className="space-y-5">
      <div className="space-y-3">
        {SWITCH_ROWS.map((row) => {
          const id = `quick-tailor-${row.key}`;
          return (
            <div
              key={row.key}
              className="flex items-center justify-between gap-4 px-3 py-2.5"
            >
              <Label htmlFor={id} className="text-sm">
                {row.label}
              </Label>
              <Switch
                id={id}
                checked={profile[row.key]}
                onCheckedChange={(checked) => setField(row.key, checked)}
              />
            </div>
          );
        })}
      </div>

      <div className="grid gap-1.5">
        <Label htmlFor="quick-tailor-base" className="text-xs">
          Default base resume
        </Label>
        <Select
          value={profile.default_base_resume || undefined}
          onValueChange={(value) =>
            setField("default_base_resume", value ?? "")
          }
        >
          <SelectTrigger id="quick-tailor-base" className="w-full">
            <SelectValue placeholder="Choose a base resume">
              {selectedBase
                ? (selectedBase.display_name ?? selectedBase.slug)
                : undefined}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {(baseResumes.data ?? []).map((resume) => (
              <SelectItem key={resume.slug} value={resume.slug}>
                {resume.display_name ?? resume.slug}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="grid gap-1.5">
        <Label htmlFor="quick-tailor-instruction" className="text-xs">
          Standing instruction
          <span className="text-muted-foreground"> · optional</span>
        </Label>
        <Input
          id="quick-tailor-instruction"
          value={profile.instruction}
          placeholder="e.g. keep bullets under two lines"
          onChange={(event) => setField("instruction", event.target.value)}
        />
      </div>

      <div className="flex justify-end">
        <Button
          onClick={() => save.mutate()}
          disabled={save.isPending || !dirty}
        >
          {save.isPending ? "Saving…" : "Save quick-tailor preferences"}
        </Button>
      </div>
    </div>
  );
}

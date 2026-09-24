"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { toast } from "sonner";

import { IconButton } from "@/components/icon-button";
import { SettingCard } from "@/components/settings/setting-card";
import { ACTION_ROW } from "@/components/settings/setting-layout";
import { useFocusOnNextCommit } from "@/hooks/use-focus-return";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import type { AutoApplySettings, SettingEnvelope } from "@/lib/types";

type AutoApplySetting = SettingEnvelope<AutoApplySettings>;

// Numeric knobs surfaced in the card; deprecated cooldown_days stays hidden
// but is preserved on save (the backend model is extra="forbid" and declines
// are posting-scoped now — the field is dormant, not meaningful).
const AUTO_APPLY_FIELDS: {
  key:
    | "max_submissions_per_day"
    | "max_proposals_per_run"
    | "proposal_expiry_days"
    | "auto_pick_floor"
    | "auto_pick_margin";
  label: string;
  hint: string;
  min: number;
  max?: number;
}[] = [
  {
    key: "max_submissions_per_day",
    label: "Applications per day",
    // services/proposals.py: a yes to submit (approved) reserves a slot; a decline frees it.
    hint: "Each application you say yes to submit counts for 24 hours.",
    min: 1,
    max: 100,
  },
  {
    key: "max_proposals_per_run",
    label: "Jobs per search",
    // Enforced agent-side only (job_search_brief hands it over; the server counts nothing).
    hint: "Agents are told to file no more than this from one search.",
    min: 1,
    max: 100,
  },
  {
    key: "proposal_expiry_days",
    // expire_stale: To review and Needs you decisions become "expired", which the
    // inbox lists under History; nothing is deleted. The clock starts at filing.
    label: "Move unreviewed jobs to History after (days)",
    hint: "Counts from when the job was filed. Queued jobs stay.",
    min: 1,
    max: 90,
  },
  {
    key: "auto_pick_floor",
    // ATS is spelled out once on this tab, here, where it first appears. Both
    // pick limits are playbook rules the agent is given (docs/playbooks/agent-apply.md).
    label: "Lowest ATS score to pick a resume",
    hint: "An ATS score is how an applicant tracking system rates a resume for a job. Below this, agents ask you which base resume to use.",
    min: 0,
    max: 100,
  },
  {
    key: "auto_pick_margin",
    label: "Lead needed to pick a resume",
    hint: "Agents pick a base resume on their own only when its ATS score leads the next one by this many points.",
    min: 0,
    max: 100,
  },
];

export function AutoApplySection() {
  const query = useQuery({
    queryKey: ["settings", "auto-apply"],
    queryFn: () => apiFetch<AutoApplySetting>("/api/settings/auto-apply"),
  });

  return (
    <SettingCard
      id="auto-apply"
      title="Auto-apply"
      description="Limits on what connected agents may do when they find and apply to jobs."
      errorTitle="Couldn't load your auto-apply settings."
      skeleton="h-24 w-full"
      query={query}
    >
      {(data) => <AutoApplyEditor initial={data.value} />}
    </SettingCard>
  );
}

/** Explicit Save: every knob here bounds what the agent lane may do on its own,
 *  which is the blast-radius half of the rule in `autosave-status.tsx`. */
function AutoApplyEditor({ initial }: { initial: AutoApplySettings }) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<AutoApplySettings | null>(null);
  const [blockInput, setBlockInput] = useState("");
  const value = draft ?? initial;
  // Unsaved limits survive a tab switch, but a navigation dropped them silently.
  // A company typed but not yet added is unsaved too.
  useLeaveGuard(draft !== null || blockInput.trim() !== "");
  // Discard unmounts itself; focus goes to Save, which stays (dimmed, focusable).
  const saveRef = useRef<HTMLButtonElement>(null);
  // A removed company takes its focused × with it; focus goes to the add field.
  const blockInputRef = useRef<HTMLInputElement>(null);
  const focusNext = useFocusOnNextCommit();

  const save = useMutation({
    mutationFn: (next: AutoApplySettings) =>
      apiFetch<AutoApplySetting>("/api/settings/auto-apply", {
        method: "PUT",
        body: JSON.stringify({ value: next }),
      }),
    onSuccess: (result) => {
      toast.success("Auto-apply settings saved");
      setDraft(null);
      qc.setQueryData(["settings", "auto-apply"], result);
      // The Agent inbox and Analytics' Agent pipeline read the cap.
      qc.invalidateQueries({ queryKey: ["proposals", "funnel"] });
    },
    onError: (err: Error) => toast.error(couldnt("save auto-apply settings", err)),
  });
  const saveOnce = useSingleFlight(save.mutate);

  const patch = (partial: Partial<AutoApplySettings>) =>
    setDraft({ ...value, ...partial });

  const addBlocked = () => {
    const name = blockInput.trim();
    if (!name) return;
    if (value.company_blocklist.some((c) => c.toLowerCase() === name.toLowerCase())) {
      setBlockInput("");
      return;
    }
    patch({ company_blocklist: [...value.company_blocklist, name] });
    setBlockInput("");
  };

  return (
    <div className="grid gap-6">
      <div className="grid gap-4 @lg/setting:grid-cols-2">
        {AUTO_APPLY_FIELDS.map((f) => (
          // `grid`, not `space-y`: a bare <label> is display:inline, so
          // on a block stack it shared a line with the input and the two
          // visibly overlapped. Grid puts every child on its own row, and
          // the shared <Label> is a flex container rather than inline.
          <div key={f.key} className="grid gap-1.5">
            <Label htmlFor={`aa-${f.key}`}>{f.label}</Label>
            {/* Hint above the control and wired with aria-describedby:
                read it before you type, not after. A field whose label
                already says it carries no hint at all. */}
            {f.hint && (
              <p id={`aa-${f.key}-hint`} className="text-muted-foreground text-xs">
                {f.hint}
              </p>
            )}
            <Input
              id={`aa-${f.key}`}
              aria-describedby={f.hint ? `aa-${f.key}-hint` : undefined}
              type="number"
              min={f.min}
              max={f.max}
              value={value[f.key]}
              onChange={(e) => {
                const n = Number(e.target.value);
                if (Number.isFinite(n)) patch({ [f.key]: n });
              }}
              className="max-w-[10rem]"
            />
          </div>
        ))}
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="aa-blocklist">Companies to skip</Label>
        <p id="aa-blocklist-hint" className="text-muted-foreground text-xs">
          {/* The server refuses only a proposal here (routers/proposals.py):
              an agent can still save a job at one of these companies. */}
          Connected agents can&apos;t propose jobs at these companies.
          Skipping one job does not block its company.
        </p>
        {value.company_blocklist.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {value.company_blocklist.map((name) => (
              <span
                key={name}
                // min-h, not h: on a coarse pointer the × is 44px, and a
                // fixed 28px chip let it overlap the row below.
                className="bg-muted inline-flex min-h-7 items-center gap-1 rounded-full pr-0.5 pl-3 text-xs"
              >
                {name}
                <IconButton
                  size="icon-xs"
                  label={`Remove ${name}`}
                  icon={<X />}
                  className="text-muted-foreground hover:bg-background rounded-full"
                  onClick={() => {
                    patch({
                      company_blocklist: value.company_blocklist.filter(
                        (c) => c !== name,
                      ),
                    });
                    focusNext(blockInputRef);
                  }}
                />
              </span>
            ))}
          </div>
        ) : null}
        <div className="flex max-w-sm gap-2">
          <Input
            ref={blockInputRef}
            id="aa-blocklist"
            aria-describedby="aa-blocklist-hint"
            value={blockInput}
            onChange={(e) => setBlockInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addBlocked();
              }
            }}
          />
          <Button type="button" variant="outline" onClick={addBlocked}>
            Add
          </Button>
        </div>
      </div>
      <div className={ACTION_ROW}>
        {draft ? (
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setDraft(null);
              focusNext(saveRef);
            }}
          >
            Discard
          </Button>
        ) : null}
        <Button
          ref={saveRef}
          type="button"
          focusableWhenDisabled
          disabled={!draft || save.isPending}
          className="data-disabled:pointer-events-none data-disabled:opacity-50"
          onClick={() => draft && saveOnce(draft)}
        >
          {save.isPending ? "Saving…" : "Save"}
        </Button>
      </div>
    </div>
  );
}

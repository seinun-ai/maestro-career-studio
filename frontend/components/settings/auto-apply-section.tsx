"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { SettingCard } from "@/components/settings/setting-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";
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
    label: "Daily submission cap",
    hint: "Approving a proposal reserves a slot for 24 hours.",
    min: 1,
    max: 100,
  },
  {
    key: "max_proposals_per_run",
    label: "Proposals per hunt run",
    // No hint: the label already says it.
    hint: "",
    min: 1,
    max: 100,
  },
  {
    key: "proposal_expiry_days",
    label: "Unreviewed proposal expiry (days)",
    hint: "Accepted proposals never expire.",
    min: 1,
    max: 90,
  },
  {
    key: "auto_pick_floor",
    label: "Auto-pick score floor",
    hint: "Minimum ATS score to auto-pick a base resume.",
    min: 0,
    max: 100,
  },
  {
    key: "auto_pick_margin",
    label: "Auto-pick margin",
    hint: "Points the top base must beat the runner-up by.",
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
      description="Guardrails for the agent hunt-and-apply lane."
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
      // The proposals funnel strip renders the cap readout — refresh it.
      qc.invalidateQueries({ queryKey: ["proposals", "funnel"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

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
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
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
        <Label htmlFor="aa-blocklist">Company blocklist</Label>
        <p id="aa-blocklist-hint" className="text-muted-foreground text-xs">
          The hunt never captures or proposes these companies. Skipping a single
          posting does not block its company.
        </p>
        {value.company_blocklist.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {value.company_blocklist.map((name) => (
              <span
                key={name}
                className="bg-muted inline-flex h-7 items-center gap-1 rounded-full pr-1.5 pl-3 text-xs"
              >
                {name}
                <button
                  type="button"
                  aria-label={`Remove ${name} from blocklist`}
                  className="hover:bg-background text-muted-foreground rounded-full px-1"
                  onClick={() =>
                    patch({
                      company_blocklist: value.company_blocklist.filter(
                        (c) => c !== name,
                      ),
                    })
                  }
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        ) : null}
        <div className="flex max-w-sm gap-2">
          <Input
            id="aa-blocklist"
            aria-describedby="aa-blocklist-hint"
            placeholder="e.g. Acme Corp"
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
      <div className="flex items-center gap-3">
        <Button
          type="button"
          disabled={!draft || save.isPending}
          onClick={() => draft && save.mutate(draft)}
        >
          {save.isPending ? "Saving…" : "Save"}
        </Button>
        {draft ? (
          <Button type="button" variant="ghost" onClick={() => setDraft(null)}>
            Cancel
          </Button>
        ) : null}
      </div>
    </div>
  );
}

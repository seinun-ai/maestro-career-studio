"use client";

import { useId } from "react";

import { AutosaveStatus } from "@/components/settings/autosave-status";
import { useMoneySetting, useSaveMoney } from "@/components/settings/money-section";
import { SettingCard, SettingCardAction } from "@/components/settings/setting-card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { HOURS_PER_YEAR } from "@/lib/money";
import { useAutosave } from "@/lib/use-autosave";

/** Settings › Advanced: the hours an hourly rate is made yearly with (the money setting's). */
export function HoursPerYearSection() {
  const setting = useMoneySetting();
  return (
    <SettingCard
      id="hours-per-year"
      title="Hours per year"
      errorTitle="Couldn't load how pay reads."
      skeleton="h-16 w-full"
      query={setting}
    >
      {(data) => <HoursEditor initial={data.value.hours_per_year} />}
    </SettingCard>
  );
}

function HoursEditor({ initial }: { initial: number }) {
  const id = useId();
  const hintId = useId();
  const save = useSaveMoney();
  // Typed digits coalesce: one write in flight, the newest queued (useAutosave).
  const { value, update, pending, failed, retry } = useAutosave(initial, (hours) =>
    save.mutateAsync({ hours_per_year: hours }),
  );
  useLeaveGuard(failed);
  return (
    <div className="grid gap-1.5">
      <SettingCardAction>
        <AutosaveStatus pending={pending} failed={failed} onRetry={retry} />
      </SettingCardAction>
      <Label htmlFor={id}>Hours per year</Label>
      <p id={hintId} className="text-muted-foreground text-body-small">
        Hourly pay is made yearly with this many hours. {HOURS_PER_YEAR.toLocaleString("en-US")} is 40
        hours a week for 52 weeks.
      </p>
      <Input
        id={id}
        type="number"
        min={1}
        max={8784}
        aria-describedby={hintId}
        defaultValue={value}
        className="max-w-[10rem]"
        onChange={(event) => {
          const hours = Number(event.target.value);
          // A blank or out-of-range field saves nothing; the last good number stays.
          if (Number.isInteger(hours) && hours >= 1 && hours <= 8784) update(() => hours);
        }}
      />
    </div>
  );
}

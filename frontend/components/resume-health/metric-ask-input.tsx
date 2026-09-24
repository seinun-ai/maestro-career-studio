"use client";

import { useId } from "react";

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
import {
  METRIC_UNITS,
  composeMetricContext,
  type MetricUnit,
} from "@/lib/health-report";

export type MetricAskValue = {
  amount: string;
  /** Empty until the user picks one: a preset unit claimed "users" nobody said. */
  unit: MetricUnit | "";
  unitOther: string;
  timeframe: string;
  freeText: string;
  somethingElse: boolean;
};

export function emptyMetricAsk(): MetricAskValue {
  return {
    amount: "",
    unit: "",
    unitOther: "",
    timeframe: "",
    freeText: "",
    somethingElse: false,
  };
}

export function metricContextFromValue(value: MetricAskValue): string {
  if (value.somethingElse) return value.freeText.trim();
  // No unit chosen yet: nothing to write from (Write stays off until there is).
  if (!value.unit) return "";
  return composeMetricContext({
    amount: value.amount,
    unit: value.unit,
    unitOther: value.unitOther,
    timeframe: value.timeframe,
  });
}

export function MetricAskInput({
  id,
  value,
  onChange,
  disabled,
}: {
  id?: string;
  value: MetricAskValue;
  onChange: (next: MetricAskValue) => void;
  disabled?: boolean;
}) {
  const set = (patch: Partial<MetricAskValue>) => onChange({ ...value, ...patch });
  // Each field has a visible name; none holds an example (Microcopy rules).
  const uid = useId();
  const ids = {
    amount: id ?? `${uid}-amount`,
    unit: `${uid}-unit`,
    unitOther: `${uid}-unit-other`,
    timeframe: `${uid}-timeframe`,
  };

  if (value.somethingElse) {
    return (
      <div className="space-y-2">
        <Textarea
          id={id}
          rows={2}
          aria-label="Your answer"
          value={value.freeText}
          onChange={(e) => set({ freeText: e.target.value })}
          disabled={disabled}
          className="max-w-[65ch] text-sm"
        />
        <Button
          type="button"
          size="xs"
          variant="ghost"
          onClick={() => set({ somethingElse: false })}
          disabled={disabled}
        >
          Use the number fields
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex min-w-0 flex-wrap items-end gap-2">
        <div className="grid gap-1">
          <Label htmlFor={ids.amount}>Number</Label>
          <Input
            id={ids.amount}
            type="text"
            inputMode="decimal"
            value={value.amount}
            onChange={(e) => set({ amount: e.target.value })}
            disabled={disabled}
            className="w-28"
          />
        </div>
        <div className="grid gap-1">
          <Label htmlFor={ids.unit}>Unit</Label>
          <Select
            value={value.unit}
            onValueChange={(unit) => set({ unit: unit as MetricUnit })}
            disabled={disabled}
          >
            <SelectTrigger id={ids.unit} size="sm" className="w-40">
              <SelectValue>
                {METRIC_UNITS.find((u) => u.id === value.unit)?.label ?? "Choose"}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {METRIC_UNITS.map((unit) => (
                <SelectItem key={unit.id} value={unit.id}>
                  {unit.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {value.unit === "other" && (
          <div className="grid gap-1">
            <Label htmlFor={ids.unitOther}>Your unit</Label>
            <Input
              id={ids.unitOther}
              value={value.unitOther}
              onChange={(e) => set({ unitOther: e.target.value })}
              disabled={disabled}
              className="w-32"
            />
          </div>
        )}
        <div className="grid gap-1">
          <Label htmlFor={ids.timeframe} optional>Time period</Label>
          <Input
            id={ids.timeframe}
            value={value.timeframe}
            onChange={(e) => set({ timeframe: e.target.value })}
            disabled={disabled}
            className="w-36"
          />
        </div>
      </div>
      <Button
        type="button"
        size="xs"
        variant="ghost"
        className="w-fit"
        onClick={() => set({ somethingElse: true })}
        disabled={disabled}
      >
        Something else…
      </Button>
    </div>
  );
}

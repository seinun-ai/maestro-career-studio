"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  unit: MetricUnit;
  unitOther: string;
  timeframe: string;
  freeText: string;
  somethingElse: boolean;
};

export function emptyMetricAsk(): MetricAskValue {
  return {
    amount: "",
    unit: "users",
    unitOther: "",
    timeframe: "",
    freeText: "",
    somethingElse: false,
  };
}

export function metricContextFromValue(value: MetricAskValue): string {
  if (value.somethingElse) return value.freeText.trim();
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
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <Input
          id={id}
          type="text"
          inputMode="decimal"
          aria-label="Number"
          placeholder="5,000"
          value={value.amount}
          onChange={(e) => set({ amount: e.target.value })}
          disabled={disabled}
          className="w-28"
        />
        <Select
          value={value.unit}
          onValueChange={(unit) => set({ unit: unit as MetricUnit })}
          disabled={disabled}
        >
          <SelectTrigger size="sm" className="w-40" aria-label="Unit">
            <SelectValue>
              {METRIC_UNITS.find((u) => u.id === value.unit)?.label ?? value.unit}
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
        {value.unit === "other" && (
          <Input
            aria-label="Custom unit"
            placeholder="unit"
            value={value.unitOther}
            onChange={(e) => set({ unitOther: e.target.value })}
            disabled={disabled}
            className="w-32"
          />
        )}
        <Input
          aria-label="Timeframe (optional)"
          placeholder="6 months"
          value={value.timeframe}
          onChange={(e) => set({ timeframe: e.target.value })}
          disabled={disabled}
          className="w-36"
        />
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

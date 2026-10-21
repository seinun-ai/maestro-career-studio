"use client";

import { useId } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { AutosaveStatus } from "@/components/settings/autosave-status";
import { SettingCard, SettingCardAction } from "@/components/settings/setting-card";
import { SegmentedChoice, SwitchRow } from "@/components/settings/setting-layout";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { apiFetch } from "@/lib/api";
import { couldnt, errorDetail } from "@/lib/error-text";
import { formatShortDate } from "@/lib/format-date";
import { inOrder } from "@/lib/in-order";
import { useAutosave } from "@/lib/use-autosave";
import type {
  FxRatesResponse,
  MarketSettingResponse,
  MoneySettings,
  MoneySettingsResponse,
} from "@/lib/types";

// The keys and reads `useMoney` (hooks/use-money.ts) shares, so a change here reads everywhere at once.
const MONEY_KEY = ["settings", "money"] as const;
const RATES_KEY = ["fx-rates"] as const;
const HOUR = 60 * 60 * 1000;
/** The select's value for "follow where you live" (`home_currency: null`). */
const WHERE_YOU_LIVE = "where-you-live";

const PERIODS = [
  { value: "year", label: "Year" },
  { value: "month", label: "Month" },
  { value: "hour", label: "Hour" },
] as const satisfies readonly { value: MoneySettings["period"]; label: string }[];

export function useMoneySetting() {
  return useQuery({
    queryKey: MONEY_KEY,
    queryFn: () => apiFetch<MoneySettingsResponse>("/api/settings/money"),
  });
}

/**
 * Writes one card's fields onto the newest stored value, one write at a time: Money (Basics) and Hours
 * per year (Advanced) write the one setting, so neither may send the other's field stale. Each write
 * stores its answer before the next one reads the cache, so a queued write never undoes the one before.
 */
export function useSaveMoney() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<MoneySettings>) =>
      inOrder("settings-money", async () => {
        const stored = qc.getQueryData<MoneySettingsResponse>(MONEY_KEY)?.value;
        const result = await apiFetch<MoneySettingsResponse>("/api/settings/money", {
          method: "PUT",
          body: JSON.stringify({ value: { ...stored, ...patch } }),
        });
        qc.setQueryData(MONEY_KEY, result);
        return result;
      }),
    onError: (err: Error) => toast.error(couldnt("save how pay reads", err)),
  });
}

type MoneyChoices = Pick<MoneySettings, "home_currency" | "period" | "show_posted">;

/** "EUR · Euro"; the code alone where the browser has no name for it. */
function currencyName(code: string): string {
  try {
    const name = new Intl.DisplayNames(undefined, { type: "currency" }).of(code);
    return name && name !== code ? `${code} · ${name}` : code;
  } catch {
    return code;
  }
}

/**
 * How pay reads everywhere (owner decision D8): the home currency (where you live unless you pick
 * one), the period figures are shown per, the ECB reference rates conversions use, and whether a
 * converted figure keeps the posted amount under it. Hours per year is under Advanced
 * (hours-per-year-section.tsx).
 */
export function MoneySection() {
  const setting = useMoneySetting();
  const rates = useQuery({
    queryKey: RATES_KEY,
    queryFn: () => apiFetch<FxRatesResponse>("/api/fx/rates"),
    staleTime: HOUR,
  });
  return (
    <SettingCard
      id="money"
      title="Money"
      errorTitle="Couldn't load how pay reads."
      skeleton="h-40 w-full"
      query={setting}
      also={[rates]}
    >
      {(data) => <MoneyEditor stored={data} rates={rates.data!} />}
    </SettingCard>
  );
}

function MoneyEditor({ stored, rates }: { stored: MoneySettingsResponse; rates: FxRatesResponse }) {
  const qc = useQueryClient();
  const currencyId = useId();
  const currencyHintId = useId();
  const periodLabelId = useId();
  const postedId = useId();
  const postedHintId = useId();
  // Where you live, for the "follow it" choice: the market setting names its currency.
  const market = useQuery({
    queryKey: ["settings", "market"],
    queryFn: () => apiFetch<MarketSettingResponse>("/api/settings/market"),
  });
  const save = useSaveMoney();
  // A pick shows at once; one write is in flight and only the newest pick waits (useAutosave).
  const { value, update, pending, failed, retry } = useAutosave<MoneyChoices>(
    {
      home_currency: stored.value.home_currency,
      period: stored.value.period,
      show_posted: stored.value.show_posted,
    },
    (next) => save.mutateAsync(next),
  );
  const change = (patch: Partial<MoneyChoices>) => update((current) => ({ ...current, ...patch }));
  // A pick the server lacks after a failed write asks before leaving (the autosave rule).
  useLeaveGuard(failed);

  const refresh = useMutation({
    mutationFn: () => apiFetch<FxRatesResponse>("/api/fx/rates/refresh", { method: "POST" }),
    onSuccess: (result) => {
      qc.setQueryData(RATES_KEY, result);
      toast.success(result.date ? `Rates from ${formatShortDate(result.date)}` : "Rates updated");
    },
    // The server's sentence says what failed (a 502 when the ECB can't be reached); the rates kept stay.
    onError: (err: Error) => toast.error(errorDetail(err) ?? "Couldn't update the rates. Try again."),
  });
  const refreshOnce = useSingleFlight(refresh.mutate);

  const live = market.data?.currency;
  // The currencies pay converts between (the ECB's), plus where you live and your pick.
  const codes = [
    ...new Set(
      [value.home_currency, live, rates.base, ...Object.keys(rates.rates)].filter(
        (code): code is string => Boolean(code),
      ),
    ),
  ].sort();
  const liveLabel = live ? `Where you live: ${live}` : "Where you live";

  return (
    <div className="grid gap-6">
      <SettingCardAction>
        <AutosaveStatus pending={pending} failed={failed} onRetry={retry} />
      </SettingCardAction>

      <div className="grid items-start gap-4 @lg/setting:grid-cols-2">
        <div className="grid gap-1.5">
          <Label htmlFor={currencyId}>Home currency</Label>
          <p id={currencyHintId} className="text-muted-foreground text-body-small">
            Every figure shows in it. It follows where you live until you pick one.
          </p>
          <Select
            value={value.home_currency ?? WHERE_YOU_LIVE}
            onValueChange={(next) => {
              if (next) change({ home_currency: next === WHERE_YOU_LIVE ? null : String(next) });
            }}
          >
            <SelectTrigger id={currencyId} aria-describedby={currencyHintId} className="w-full">
              <SelectValue>
                {value.home_currency ? currencyName(value.home_currency) : liveLabel}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={WHERE_YOU_LIVE}>{liveLabel}</SelectItem>
              {codes.map((code) => (
                <SelectItem key={code} value={code}>
                  {currencyName(code)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid gap-1.5">
          <Label id={periodLabelId}>Show pay per</Label>
          <SegmentedChoice
            labelledBy={periodLabelId}
            value={value.period}
            options={PERIODS}
            onChange={(period) => change({ period })}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <p className="grid gap-0.5">
          <span className="text-body-medium">
            {rates.date ? `Rates from ${formatShortDate(rates.date)}` : "No rates yet. Pay shows as posted."}
          </span>
          <span className="text-muted-foreground text-body-small">{rates.source}, once a day</span>
        </p>
        <Button size="sm" variant="outline" pending={refresh.isPending} onClick={() => refreshOnce(undefined)}>
          Update
        </Button>
      </div>

      <div className="grid gap-1">
        <SwitchRow htmlFor={postedId} label="Show the posted amount too">
          <Switch
            id={postedId}
            aria-describedby={postedHintId}
            checked={value.show_posted}
            onCheckedChange={(show_posted) => change({ show_posted })}
          />
        </SwitchRow>
        <p id={postedHintId} className="text-muted-foreground text-body-small">
          Under every converted figure.
        </p>
      </div>
    </div>
  );
}

"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { FxRates, PayOptions } from "@/lib/money";
import type { FxRatesResponse, MoneySettingsResponse } from "@/lib/types";

const HOUR = 60 * 60 * 1000;

/** The rates `formatPay` converts with; null while there are none (pay then reads as posted). */
export function toFxRates(body: FxRatesResponse | undefined): FxRates | null {
  if (!body?.date || Object.keys(body.rates).length === 0) return null;
  return { base: body.base, date: body.date, rates: body.rates };
}

/**
 * Everything `formatPay` needs from the server: the home currency and period from the money
 * setting, the ECB rates from `GET /api/fx/rates` (which fetches at most once a day). Until the
 * setting loads, `home` is absent and pay reads as posted; until rates load, nothing converts.
 */
export function useMoney(): PayOptions & { showPosted: boolean; ratesReady: boolean } {
  const settings = useQuery({
    queryKey: ["settings", "money"],
    queryFn: () => apiFetch<MoneySettingsResponse>("/api/settings/money"),
  });
  const rates = useQuery({
    queryKey: ["fx-rates"],
    queryFn: () => apiFetch<FxRatesResponse>("/api/fx/rates"),
    // The server refreshes at most once a day; an hour here keeps pages from asking more.
    staleTime: HOUR,
  });
  const value = settings.data?.value;
  return {
    home: settings.data?.home_currency ?? null,
    rates: toFxRates(rates.data),
    per: value?.period,
    hoursPerYear: value?.hours_per_year,
    showPosted: value?.show_posted ?? true,
    // Settled either way: only then does "no rate" mean the ECB has none, not "still loading".
    ratesReady: rates.isSuccess,
  };
}

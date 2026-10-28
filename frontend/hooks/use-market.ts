"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { MarketSettingResponse } from "@/lib/types";

/** Where the user lives and applies (`GET /api/settings/market`), with the markets the app knows. */
export function useMarketQuery() {
  return useQuery({
    queryKey: ["settings", "market"],
    queryFn: () => apiFetch<MarketSettingResponse>("/api/settings/market"),
  });
}

/** The home market's ISO country code: null for a market with no country, undefined until the setting loads. */
export function useHomeCountry(): string | null | undefined {
  const { data } = useMarketQuery();
  if (!data) return undefined;
  return data.markets?.find((market) => market.key === data.home)?.country_code ?? null;
}

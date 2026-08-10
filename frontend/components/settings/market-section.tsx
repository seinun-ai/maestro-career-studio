"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import type { MarketSettingResponse } from "@/lib/types";

/**
 * Which market the user applies in. Drives the default currency on captured
 * jobs and whether a voluntary-disclosure (EEO) section is offered at all.
 *
 * The supported list, each market's currency, and whether it offers an EEO
 * module all come from the API — this component hardcodes none of it, because
 * deciding client-side whether to show demographic questions is exactly the
 * mistake that files a US answer into a UK form.
 */
export function MarketSection() {
  const qc = useQueryClient();

  const market = useQuery({
    queryKey: ["settings", "market"],
    queryFn: () => apiFetch<MarketSettingResponse>("/api/settings/market"),
  });

  const save = useMutation({
    mutationFn: (next: string) =>
      apiFetch<MarketSettingResponse>("/api/settings/market", {
        method: "PUT",
        body: JSON.stringify({ value: { market: next } }),
      }),
    onSuccess: (result) => {
      qc.setQueryData(["settings", "market"], (prev: MarketSettingResponse | undefined) =>
        prev ? { ...prev, ...result } : prev,
      );
      // Readiness counts a different number of questions per market, and the
      // capture currency changes — both surfaces must refetch, not go stale.
      qc.invalidateQueries({ queryKey: ["setup-status"] });
      qc.invalidateQueries({ queryKey: ["settings", "market"] });
    },
    // Errors still toast: a FAILED save is exactly the thing you must notice.
    onError: () => toast.error("Could not save your market"),
  });

  const selected = market.data?.value.market;
  const current = market.data?.supported.find((m) => m.key === selected);

  return (
    <Card id="market">
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <CardTitle>Market</CardTitle>
        <AutosaveStatus pending={save.isPending} />
      </CardHeader>
      <CardContent className="grid gap-4">
        {market.isLoading ? (
          <Skeleton className="h-9 w-full max-w-sm" />
        ) : market.isError ? (
          <p className="text-sm text-muted-foreground">Could not load your market.</p>
        ) : (
          <div className="grid gap-1.5 max-w-sm">
            <Label htmlFor="market-select" id="market-select-label">
              Where you apply
            </Label>
            <p id="market-select-hint" className="text-xs text-muted-foreground">
              Sets the default currency for captured jobs and which voluntary
              disclosures apply.
            </p>
            <Select
              value={selected}
              onValueChange={(next) => save.mutate(String(next))}
            >
              <SelectTrigger
                id="market-select"
                aria-labelledby="market-select-label"
                aria-describedby="market-select-hint"
                data-pending={save.isPending ? "" : undefined}
              >
                <SelectValue>{current ? current.label : selected}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {(market.data?.supported ?? []).map((m) => (
                  <SelectItem key={m.key} value={m.key}>
                    {m.label} · {m.currency}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {current && !current.offers_eeo && (
          <p className="text-xs text-muted-foreground border-l-2 border-muted pl-3">
            Maestro CS has no verified voluntary-disclosure question set for{" "}
            {current.label}, so it does not ask for one. Those categories are not
            interchangeable between countries, and answering the wrong country&apos;s
            form would put inaccurate information under your name.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

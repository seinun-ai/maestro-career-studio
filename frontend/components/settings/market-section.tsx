"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { SettingCard, SettingCardAction } from "@/components/settings/setting-card";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
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
    onError: (err: Error) => toast.error(couldnt("save your country", err)),
  });

  return (
    <SettingCard
      id="market"
      title="Where you apply"
      // No description: this card has one control, and its label plus the
      // aria-describedby hint below already say what a subtitle would repeat.
      errorTitle="Couldn't load your country."
      skeleton="h-9 w-full max-w-sm"
      query={market}
    >
      {(data) => {
        const selected = data.value.market;
        const current = data.supported.find((m) => m.key === selected);
        return (
          <div className="grid gap-4">
            <SettingCardAction>
              <AutosaveStatus pending={save.isPending} failed={save.isError} />
            </SettingCardAction>
            <div className="grid max-w-sm gap-1.5">
              <Label htmlFor="market-select" id="market-select-label">
                Country
              </Label>
              <p id="market-select-hint" className="text-muted-foreground text-xs">
                Sets the default currency for jobs you save and which diversity questions apply.
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
                  {data.supported.map((m) => (
                    <SelectItem key={m.key} value={m.key}>
                      {m.label} ({m.currency})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {current && !current.offers_eeo && (
              <p className="text-muted-foreground max-w-prose text-xs">
                Maestro CS has no verified diversity questions for {current.label},
                so it won&apos;t ask them. Another country&apos;s questions could
                put wrong information under your name.
              </p>
            )}
          </div>
        );
      }}
    </SettingCard>
  );
}

"use client";

import { useId, useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { toast } from "sonner";

import { formQuestionsQuery } from "@/components/profile/use-form-questions";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import type { MarketOption, MarketSettingResponse } from "@/lib/types";
import { useAutosave } from "@/lib/use-autosave";
import { cn } from "@/lib/utils";

type Place = { home: string; apply_in: string[] };

/** Whether the user chose where they apply (`value.chosen`); a server that predates the mark sends none, and its
 *  countries were always a choice. */
export function countriesChosen(market: MarketSettingResponse): boolean {
  return market.value?.chosen !== false;
}

/**
 * You live in and You apply in, saving as you go (`PUT /api/settings/market`, one write in flight and the
 * newest queued). Profile's Where you apply and Setup's Where and what both save through it. While you apply
 * only where you live, the list follows you; a longer list is left as it is, and at least one country stays.
 *
 * Until you choose (`countriesChosen`), the stored countries are the defaults, never a choice, so `value`
 * applies in none: nothing shows as picked, and the first country you press is where you apply.
 */
export function useCountriesAutosave(market: MarketSettingResponse) {
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: (next: Place) =>
      apiFetch<MarketSettingResponse>("/api/settings/market", {
        method: "PUT",
        body: JSON.stringify({ value: next }),
      }),
    onSuccess: async (result) => {
      // The form questions follow where you live and apply (the state line, each country's work permit): read
      // first, so a country never shows on screen without its questions.
      await qc.invalidateQueries({ queryKey: formQuestionsQuery.queryKey });
      qc.setQueryData(["settings", "market"], (prev: MarketSettingResponse | undefined) =>
        prev ? { ...prev, ...result } : prev,
      );
      // Readiness counts each country's questions, the capture currency changes, and the profile's one-set
      // work-permit view follows where you live: each must refetch, not go stale.
      for (const key of [["setup-status"], ["settings", "market"], ["settings", "money"], ["settings", "autofill"]]) {
        void qc.invalidateQueries({ queryKey: key });
      }
    },
    // Errors still toast: a FAILED save is exactly the thing you must notice.
    onError: (err: Error) => toast.error(couldnt("save your countries", err)),
  });
  const place = useAutosave<Place>({ home: market.home, apply_in: market.apply_in }, (next) =>
    save.mutateAsync(next),
  );
  // Chosen from the first edit: the market read says so only once that save lands.
  const [picked, setPicked] = useState(false);
  const chosen = picked || countriesChosen(market);
  const setHome = (next: string) => {
    setPicked(true);
    place.update((current) => ({
      home: next,
      apply_in:
        !chosen || (current.apply_in.length === 1 && current.apply_in[0] === current.home) ? [next] : current.apply_in,
    }));
  };
  const toggleCountry = (key: string) => {
    setPicked(true);
    place.update((current) =>
      !chosen
        ? { ...current, apply_in: [key] }
        : current.apply_in.includes(key)
          ? current.apply_in.length === 1
            ? current // At least one: an empty list reads as where you live anyway.
            : { ...current, apply_in: current.apply_in.filter((k) => k !== key) }
          : { ...current, apply_in: [...current.apply_in, key] },
    );
  };
  const value = chosen ? place.value : { ...place.value, apply_in: [] };
  return { ...place, value, chosen, setHome, toggleCountry };
}

/** You live in: one country, listed with its currency. The supported list comes from the API. */
export function LiveInField({
  markets,
  home,
  setHome,
  hint,
  pending,
  className,
}: {
  markets: MarketOption[];
  home: string;
  setHome: (next: string) => void;
  hint: ReactNode;
  /** Dims the select while a write is in flight. */
  pending?: boolean;
  className?: string;
}) {
  const homeId = useId();
  const homeHintId = useId();
  const chosen = markets.find((m) => m.key === home);
  return (
    <div className={cn("grid gap-1.5", className)}>
      <Label htmlFor={homeId}>You live in</Label>
      <p id={homeHintId} className="text-body-small text-muted-foreground">
        {hint}
      </p>
      <Select value={home} onValueChange={(next) => next && setHome(String(next))}>
        <SelectTrigger
          id={homeId}
          aria-describedby={homeHintId}
          className="w-full"
          data-pending={pending ? "true" : undefined}
        >
          <SelectValue>{chosen ? chosen.label : home}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {markets.map((m) => (
            <SelectItem key={m.key} value={m.key}>
              {m.label} ({m.currency})
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

/** You apply in: a pressed chip per country; `chip` renders a country's label (its name by default). */
export function ApplyInField({
  markets,
  applyIn,
  toggleCountry,
  hint,
  chip = (m) => m.label,
  className,
}: {
  markets: MarketOption[];
  applyIn: string[];
  toggleCountry: (key: string) => void;
  hint: ReactNode;
  chip?: (market: MarketOption) => ReactNode;
  className?: string;
}) {
  const applyLabelId = useId();
  const applyHintId = useId();
  return (
    <div className={cn("grid gap-1.5", className)}>
      <span id={applyLabelId} className="text-label-large">
        You apply in
      </span>
      <p id={applyHintId} className="text-body-small text-muted-foreground">
        {hint}
      </p>
      <div role="group" aria-labelledby={applyLabelId} aria-describedby={applyHintId} className="flex flex-wrap gap-2">
        {markets.map((m) => {
          const on = applyIn.includes(m.key);
          return (
            <Button
              key={m.key}
              type="button"
              size="sm"
              variant={on ? "tonal" : "outline"}
              aria-pressed={on}
              onClick={() => toggleCountry(m.key)}
            >
              {on ? <Check aria-hidden="true" /> : null}
              {chip(m)}
            </Button>
          );
        })}
      </div>
    </div>
  );
}

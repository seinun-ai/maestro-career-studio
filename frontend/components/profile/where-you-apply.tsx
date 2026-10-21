"use client";

import { useId } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { toast } from "sonner";

import { TileCard, type TileView } from "@/components/profile/tile";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { SettingCardAction } from "@/components/settings/setting-card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ResumeSwatch } from "@/components/visual";
import { useBaseResumes } from "@/hooks/use-base-resume-label";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import {
  baseResumeLabel,
  type BaseResumeSummary,
  type MarketOption,
  type MarketSettingResponse,
} from "@/lib/types";
import { useAutosave } from "@/lib/use-autosave";

type Place = { home: string; apply_in: string[] };

export function useMarketQuery() {
  return useQuery({
    queryKey: ["settings", "market"],
    queryFn: () => apiFetch<MarketSettingResponse>("/api/settings/market"),
  });
}

/** The base resumes that store a market's country (`countries` holds ISO codes; the market's `country_code`). */
function resumesFor(market: MarketOption | undefined, resumes: readonly BaseResumeSummary[]): BaseResumeSummary[] {
  const code = market?.country_code;
  return code ? resumes.filter((resume) => resume.countries.includes(code)) : [];
}

/** A country, with the square of each base resume that stores it: the resume's name is read with it. */
function CountryName({ market, label, resumes }: { market?: MarketOption; label: string; resumes: BaseResumeSummary[] }) {
  const mine = resumesFor(market, resumes);
  return (
    <>
      {mine.map((resume) => (
        <ResumeSwatch key={resume.slug} hue={resume.color_hue} />
      ))}
      {label}
      {mine.length ? (
        <span className="sr-only">
          , {mine.map((resume) => baseResumeLabel(resume.slug, resumes)).join(", ")}
          {mine.length === 1 ? " resume" : " resumes"}
        </span>
      ) : null}
    </>
  );
}

/** Where you apply: You live in (home currency, date format) and You apply in (each country with its own
 *  work-permit answers), from the market setting. */
export function useWhereTile(market: MarketSettingResponse): TileView {
  const resumes = useBaseResumes();
  const options = market.markets ?? [];
  const byKey = new Map(options.map((m) => [m.key, m]));
  const home = byKey.get(market.home);
  const count = market.apply_in.length;
  return {
    state: { kind: "count", text: count === 1 ? "1 country" : `${count} countries` },
    summary: (
      <>
        <span>Lives in {home?.label ?? market.home}</span>
        <span className="flex flex-wrap gap-1.5">
          {market.apply_in.map((key) => (
            <span
              key={key}
              className="inline-flex items-baseline gap-1.5 rounded-full bg-surface-container px-2 py-0.5 text-label-medium text-foreground"
            >
              <CountryName market={byKey.get(key)} label={byKey.get(key)?.label ?? key} resumes={resumes.data ?? []} />
            </span>
          ))}
        </span>
      </>
    ),
    note: "Each country has its own work-permit answers",
    panel: <WhereCard />,
  };
}

function WhereCard() {
  const market = useMarketQuery();
  return (
    <TileCard
      tile="where"
      description="Where you live sets your home currency. Each country you apply in has its own form answers."
      errorTitle="Couldn't load your countries."
      skeleton="h-24 w-full"
      query={market}
    >
      {(data) => <WhereEditor market={data} />}
    </TileCard>
  );
}

/**
 * You live in and You apply in, saving as you go (`PUT /api/settings/market`, one write in flight and the
 * newest queued). While you apply only where you live, the list follows you (Setup's Where and what does
 * the same); a longer list is left as it is, and at least one country stays. The supported list, each
 * market's currency and whether it has a checked diversity set all come from the API: deciding that here is
 * exactly the mistake that files a US answer into a UK form.
 */
function WhereEditor({ market }: { market: MarketSettingResponse }) {
  const qc = useQueryClient();
  const resumes = useBaseResumes();
  const homeId = useId();
  const homeHintId = useId();
  const applyLabelId = useId();
  const applyHintId = useId();
  const options = market.markets ?? [];

  const save = useMutation({
    mutationFn: (next: Place) =>
      apiFetch<MarketSettingResponse>("/api/settings/market", {
        method: "PUT",
        body: JSON.stringify({ value: next }),
      }),
    onSuccess: (result) => {
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
  const {
    value: place,
    update,
    pending,
    failed,
    retry,
  } = useAutosave<Place>({ home: market.home, apply_in: market.apply_in }, (next) => save.mutateAsync(next));
  useLeaveGuard(failed);

  const home = options.find((m) => m.key === place.home);
  const withoutSet = place.apply_in.flatMap((key) => {
    const m = options.find((o) => o.key === key);
    return m && !m.offers_eeo ? [m.label] : [];
  });
  const setHome = (next: string) =>
    update((current) => ({
      home: next,
      apply_in: current.apply_in.length === 1 && current.apply_in[0] === current.home ? [next] : current.apply_in,
    }));
  const toggleCountry = (key: string) =>
    update((current) =>
      current.apply_in.includes(key)
        ? current.apply_in.length === 1
          ? current // At least one: an empty list reads as where you live anyway.
          : { ...current, apply_in: current.apply_in.filter((k) => k !== key) }
        : { ...current, apply_in: [...current.apply_in, key] },
    );

  return (
    <div className="grid gap-6">
      <SettingCardAction>
        <AutosaveStatus pending={pending} failed={failed} onRetry={retry} />
      </SettingCardAction>
      <div className="grid max-w-sm gap-1.5">
        <Label htmlFor={homeId}>You live in</Label>
        <p id={homeHintId} className="text-muted-foreground text-body-small">
          Sets your home currency and date format.
        </p>
        <Select value={place.home} onValueChange={(next) => next && setHome(String(next))}>
          <SelectTrigger
            id={homeId}
            aria-describedby={homeHintId}
            className="w-full"
            data-pending={pending ? "true" : undefined}
          >
            <SelectValue>{home ? home.label : place.home}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {options.map((m) => (
              <SelectItem key={m.key} value={m.key}>
                {m.label} ({m.currency})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="grid gap-1.5">
        <span id={applyLabelId} className="text-label-large">
          You apply in
        </span>
        <p id={applyHintId} className="text-muted-foreground text-body-small">
          Each country has its own work-permit answers and its own diversity questions, if it has a checked set.
          A square is a base resume made for that country. Keep at least one.
        </p>
        <div role="group" aria-labelledby={applyLabelId} aria-describedby={applyHintId} className="flex flex-wrap gap-2">
          {options.map((m) => {
            const on = place.apply_in.includes(m.key);
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
                <CountryName market={m} label={m.label} resumes={resumes.data ?? []} />
              </Button>
            );
          })}
        </div>
      </div>
      {withoutSet.length ? (
        <p className="text-muted-foreground max-w-prose text-body-small">
          Maestro CS has no checked diversity questions for{" "}
          {new Intl.ListFormat("en", { type: "conjunction" }).format(withoutSet)}, so it won&apos;t ask them there.
          Another country&apos;s questions could put wrong information under your name.
        </p>
      ) : null}
    </div>
  );
}

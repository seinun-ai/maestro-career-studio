"use client";

import { ApplyInField, LiveInField, useCountriesAutosave } from "@/components/profile/country-fields";
import { TileCard, type TileView } from "@/components/profile/tile";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { SettingCardAction } from "@/components/settings/setting-card";
import { ResumeSwatch } from "@/components/visual";
import { useBaseResumes } from "@/hooks/use-base-resume-label";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { useMarketQuery } from "@/hooks/use-market";
import {
  baseResumeLabel,
  type BaseResumeSummary,
  type MarketOption,
  type MarketSettingResponse,
} from "@/lib/types";

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
 * You live in and You apply in, saving as you go (`useCountriesAutosave`; Setup's Where and what saves the
 * same way). The supported list, each market's currency and whether it has a checked diversity set all come
 * from the API: deciding that here is exactly the mistake that files a US answer into a UK form.
 */
function WhereEditor({ market }: { market: MarketSettingResponse }) {
  const resumes = useBaseResumes();
  const options = market.markets ?? [];
  const { value: place, pending, failed, retry, setHome, toggleCountry } = useCountriesAutosave(market);
  useLeaveGuard(failed);

  const withoutSet = place.apply_in.flatMap((key) => {
    const m = options.find((o) => o.key === key);
    return m && !m.offers_eeo ? [m.label] : [];
  });

  return (
    <div className="grid gap-6">
      <SettingCardAction>
        <AutosaveStatus pending={pending} failed={failed} onRetry={retry} />
      </SettingCardAction>
      <LiveInField
        markets={options}
        home={place.home}
        setHome={setHome}
        hint="Sets your home currency and date format."
        pending={pending}
        className="max-w-sm"
      />
      <ApplyInField
        markets={options}
        applyIn={place.apply_in}
        toggleCountry={toggleCountry}
        hint={
          <>
            Each country has its own work-permit answers and its own diversity questions, if it has a checked set.
            A square is a base resume made for that country. Keep at least one.
          </>
        }
        chip={(m) => <CountryName market={m} label={m.label} resumes={resumes.data ?? []} />}
      />
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

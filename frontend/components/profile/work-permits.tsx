"use client";

import { useEffect, useId, useRef, useState } from "react";

import { CountryPicker, useCountries } from "@/components/country-picker";
import { useAutofillProfile } from "@/components/profile/autofill-profile";
import { FieldGrid } from "@/components/profile/field-control";
import { TileCard, type TileView } from "@/components/profile/tile";
import { useAutofillQuery } from "@/components/profile/use-autofill-query";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { SettingCardAction } from "@/components/settings/setting-card";
import { GROUP_HEADING } from "@/components/settings/setting-layout";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  answered,
  answerWords,
  citizenshipAnswered,
  citizenshipEntries,
  citizenshipField,
  countryAnswerEntry,
  derivedPermits,
  fieldShown,
  permitAnswered,
  permitAnswers,
  permitCount,
  permitEntry,
  withCitizenships,
  withCountryAnswer,
  withPermit,
  type Count,
  type CountryQuestions,
  type FieldDef,
} from "@/lib/autofill-options";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import type { MarketSettingResponse, QuestionSet } from "@/lib/types";
import { cn } from "@/lib/utils";

const SURFACE = "permits";

/** Citizen of names the United Kingdom by the citizenship its forms mean (British citizen, not every British
 *  nationality). */
const CITIZEN_NAMES: Readonly<Record<string, string>> = { GB: "United Kingdom (British citizen)" };

/** What a citizenship does, said under "Citizen of" here and in Next up. */
export const CITIZEN_HINT = "Where your citizenship lets you work in a country without a permit, its work-permit answers follow from it.";

/** A country's name by its ISO code: the country list's, else a market's, else the code. */
function useCountryName(market: MarketSettingResponse): (code: string) => string {
  const { data } = useCountries();
  const names = new Map((market.markets ?? []).flatMap((m) => (m.country_code ? [[m.country_code, m.label]] : [])));
  for (const country of data ?? []) names.set(country.code, country.name);
  return (code) => names.get(code.toUpperCase()) ?? code;
}

/** One country's line on the tile: its answers in words, given or settled by your citizenship, never a guess. */
function permitWords(answers: Record<string, unknown>, count: Count): string {
  if (count.answered === 0) return "not answered";
  if (count.answered < count.answerable) return `${count.answered} of ${count.answerable} answered`;
  const now = answers.authorized_now;
  return now === true ? "can work now" : now === false ? "can't work there now" : "answered";
}

function SummaryRow({ done, label, words }: { done: boolean; label: string; words: string }) {
  return (
    <span className="flex items-center gap-1.5 text-foreground">
      {done ? (
        <CONCEPT_ICONS.done aria-hidden="true" className="size-3.5 shrink-0 text-success" />
      ) : (
        <span aria-hidden="true" className="size-3.5 shrink-0 rounded-full border-[1.5px] border-attention" />
      )}
      <span className="min-w-0 flex-1 truncate">{label}</span>
      <span className="min-w-0 truncate text-muted-foreground">{words}</span>
    </span>
  );
}

/**
 * Country answers: your citizenship, then one set per country you apply in, as the served set lists them, each
 * in that country's own words: its work permits (some settled by your citizenship), then its own answers.
 * Citizenship counts here, beside the permits it settles, as setup readiness counts it.
 */
export function useWorkPermitsTile(
  market: MarketSettingResponse,
  questionSet: QuestionSet,
  onChooseCountries: () => void,
): TileView {
  const { profile } = useAutofillProfile();
  const nameOf = useCountryName(market);
  const asksCitizenship = citizenshipField(questionSet) !== undefined;
  const citizenDone = citizenshipAnswered(profile, questionSet);
  const citizens = citizenshipEntries(profile).map(nameOf);
  const rows = questionSet.countries.map((country) => ({
    key: country.market,
    label: country.label,
    done: permitAnswered(profile, questionSet, country.market),
    words: permitWords(
      permitAnswers(profile, questionSet, country.market),
      permitCount(profile, questionSet, country.market),
    ),
  }));
  const open = !citizenDone || rows.some((row) => !row.done);
  return {
    state: open ? { kind: "needs" } : { kind: "ready" },
    summary: (
      <span className="flex flex-col gap-1">
        {asksCitizenship ? (
          <SummaryRow done={citizenDone} label="Citizen of" words={citizens.length ? citizens.join(", ") : "not answered"} />
        ) : null}
        {rows.map((row) => (
          <SummaryRow key={row.key} done={row.done} label={row.label} words={row.words} />
        ))}
        {questionSet.countries.length ? null : <span>No country chosen yet</span>}
      </span>
    ),
    note: "Never guessed for you",
    panel: <CountryAnswersCard market={market} questionSet={questionSet} onChooseCountries={onChooseCountries} />,
  };
}

function CountryAnswersCard({
  market,
  questionSet,
  onChooseCountries,
}: {
  market: MarketSettingResponse;
  questionSet: QuestionSet;
  onChooseCountries: () => void;
}) {
  const query = useAutofillQuery();
  return (
    <TileCard
      tile="permits"
      description="Each country asks these its own way. A form gets the answers of the country its question names, else the job's country, else the Companion asks you on that job."
      errorTitle="Couldn't load your form answers."
      query={query}
    >
      {() => <CountryAnswersEditor market={market} questionSet={questionSet} onChooseCountries={onChooseCountries} />}
    </TileCard>
  );
}

/** Citizen of: a country picker valued as ISO codes, the United Kingdom read as British citizen. Profile's
 *  Country answers and Next up both ask it. */
export function CitizenshipPicker({
  id,
  label,
  value,
  onChange,
  describedBy,
}: {
  id: string;
  label: string;
  value: readonly string[];
  onChange: (codes: string[]) => void;
  describedBy?: string;
}) {
  return (
    <CountryPicker
      id={id}
      aria-label={label}
      aria-describedby={describedBy}
      names={CITIZEN_NAMES}
      value={value}
      onChange={onChange}
    />
  );
}

/** Citizen of, then one fieldset per served country, named by the country; each answer is that country's own
 *  entry in `work_auth_by_country` or `answers_by_country`, keyed by market ("UK", not the ISO "GB"). */
function CountryAnswersEditor({
  market,
  questionSet,
  onChooseCountries,
}: {
  market: MarketSettingResponse;
  questionSet: QuestionSet;
  onChooseCountries: () => void;
}) {
  const { profile, update, saveState } = useAutofillProfile();
  const citizenship = citizenshipField(questionSet);
  const hintId = useId();
  const nameOf = useCountryName(market);
  return (
    // Groups are divided by their headings and a wide gap, never by rules. Each fieldset stays in block
    // flow: a rendered <legend> is not a grid item, so a grid gap would never separate it from the first field.
    <div className="grid gap-8">
      <SettingCardAction>
        <AutosaveStatus {...saveState(SURFACE)} />
      </SettingCardAction>
      {citizenship ? (
        <div className="grid max-w-xl gap-1.5">
          <Label htmlFor="af-citizenships" optional={citizenship.optional}>
            {citizenship.label}
          </Label>
          <p id={hintId} className="text-body-small text-muted-foreground">
            {CITIZEN_HINT}
          </p>
          <CitizenshipPicker
            id="af-citizenships"
            label={citizenship.label}
            describedBy={hintId}
            value={citizenshipEntries(profile)}
            onChange={(codes) => update(SURFACE, (current) => withCitizenships(current, codes))}
          />
        </div>
      ) : null}
      {questionSet.countries.length ? (
        questionSet.countries.map((country) => (
          <CountrySet key={country.market} country={country} questionSet={questionSet} nameOf={nameOf} />
        ))
      ) : (
        <div className="grid gap-1.5">
          <p className="max-w-[65ch] text-body-medium text-muted-foreground">
            No country chosen yet. Choose where you apply, and each country&apos;s own questions are asked here.
          </p>
          <Button type="button" variant="link" size="sm" className="h-auto justify-self-start p-0" onClick={onChooseCountries}>
            Where you apply
          </Button>
        </div>
      )}
    </div>
  );
}

/**
 * One country: its work permits, then its own answers. A permit answer your citizenship settles shows as words,
 * "From your citizenship (India)", with Answer differently, which brings its control back; an answer you give
 * wins over it, and one that differs settles nothing else there (`derivedPermits`).
 */
function CountrySet({
  country,
  questionSet,
  nameOf,
}: {
  country: CountryQuestions;
  questionSet: QuestionSet;
  nameOf: (code: string) => string;
}) {
  const { profile, update } = useAutofillProfile();
  // The settled answers you chose to answer differently, and the one whose control takes focus once it shows.
  const [answering, setAnswering] = useState<readonly string[]>([]);
  const focusNext = useRef<string | null>(null);
  const idPrefix = `af-permit-${country.market}`;
  useEffect(() => {
    const key = focusNext.current;
    if (!key) return;
    focusNext.current = null;
    document.getElementById(`${idPrefix}-${key}`)?.focus();
  }, [answering, idPrefix]);

  const entry = permitEntry(profile, country.market);
  const derived = derivedPermits(profile, questionSet, country.market);
  // Shown by the answers as the fill reads them: a status your citizenship settles hides its expiry too.
  const answers = permitAnswers(profile, questionSet, country.market);
  const fields = country.permits.filter((field) => fieldShown(field, answers));
  const settled = (field: FieldDef) => {
    const by = derived[field.key];
    if (!by || answered(field, entry[field.key]) || answering.includes(field.key)) return [];
    const node = (
      <>
        <p className="text-body-medium">{answerWords(field, by.value)}</p>
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="text-body-small text-muted-foreground">From your citizenship ({nameOf(by.via)})</span>
          <Button
            type="button"
            variant="link"
            size="sm"
            className="h-auto p-0"
            aria-describedby={`${idPrefix}-${field.key}-label`}
            onClick={() => {
              focusNext.current = field.key;
              setAnswering((keys) => [...keys, field.key]);
            }}
          >
            Answer differently
          </Button>
        </span>
      </>
    );
    return [[field.key, node] as const];
  };
  return (
    <fieldset className="space-y-4">
      <legend className={cn(GROUP_HEADING, "flex items-center gap-1.5")}>
        <CONCEPT_ICONS.workAuthorization aria-hidden="true" className="size-4" />
        {country.label}
      </legend>
      <FieldGrid
        idPrefix={idPrefix}
        group={`permit-${country.market}`}
        fields={fields}
        values={entry}
        settled={Object.fromEntries(fields.flatMap(settled))}
        onChange={(key, next) => update(SURFACE, (current) => withPermit(current, questionSet, country.market, key, next))}
      />
      {country.answers.length ? (
        <FieldGrid
          idPrefix={`af-answer-${country.market}`}
          group={`answer-${country.market}`}
          fields={country.answers}
          values={countryAnswerEntry(profile, country.market)}
          onChange={(key, next) => update(SURFACE, (current) => withCountryAnswer(current, country.market, key, next))}
        />
      ) : null}
    </fieldset>
  );
}

"use client";

import { useId, useState, type ReactNode } from "react";

import { useCountries, useCountryCodes } from "@/components/country-picker";
import { useAutofillProfile } from "@/components/profile/autofill-profile";
import { CITIZEN_HINT, CitizenshipPicker } from "@/components/profile/citizenship-picker";
import { FieldGrid } from "@/components/profile/field-control";
import { TileCard, type TileView } from "@/components/profile/tile";
import { useAutofillQuery } from "@/components/profile/use-autofill-query";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { SettingCardAction } from "@/components/settings/setting-card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { useFocusOnNextCommit } from "@/hooks/use-focus-return";
import {
  answered,
  answerWords,
  citizenshipAnswered,
  citizenshipEntries,
  citizenshipField,
  countryAnswerEntry,
  countryAnswersOpen,
  countryDone,
  countrySetCount,
  derivedPermits,
  differsFromSettled,
  openAnswersWords,
  permitAnswered,
  permitAnswers,
  permitEntry,
  shownPermitFields,
  withCitizenships,
  withCountryAnswer,
  withPermit,
  type Count,
  type CountryQuestions,
  type DerivedAnswer,
  type Profile,
} from "@/lib/autofill-options";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import type { MarketSettingResponse, QuestionSet } from "@/lib/types";

const SURFACE = "permits";

/** A country's name by its ISO code: the country list's, else a market's, else the code. */
function useCountryName(market: MarketSettingResponse): (code: string) => string {
  const { data } = useCountries();
  const names = new Map((market.markets ?? []).flatMap((m) => (m.country_code ? [[m.country_code, m.label]] : [])));
  for (const country of data ?? []) names.set(country.code, country.name);
  return (code) => names.get(code.toUpperCase()) ?? code;
}

/** One country's answers in words, given or settled by your citizenship, never a guess: how many of its set
 *  (`countrySetCount`, as Next up counts them) until all are, then whether you can work there now. */
function permitWords(answers: Record<string, unknown>, count: Count): string {
  if (count.answered === 0) return "not answered";
  if (count.answered < count.answerable) return `${count.answered} of ${count.answerable} answered`;
  const now = answers.authorized_now;
  return now === true ? "can work now" : now === false ? "can't work there now" : "answered";
}

/** One country's line, on the tile and at its heading: done once its permits and its own required answers are
 *  (`countryDone`), and worded by its whole set, or by its own open answers once those are all that is open
 *  (where you live, its pay: `openAnswersWords`). */
function countryLine(profile: Profile, questionSet: QuestionSet, market: string): { done: boolean; words: string } {
  const open = permitAnswered(profile, questionSet, market) ? countryAnswersOpen(profile, questionSet, market) : [];
  const words = open.length
    ? openAnswersWords(open)
    : permitWords(permitAnswers(profile, questionSet, market), countrySetCount(profile, questionSet, market));
  return { done: countryDone(profile, questionSet, market), words };
}

/** Done or still open: a check, or an empty ring. */
function DoneMark({ done }: { done: boolean }) {
  return done ? (
    <CONCEPT_ICONS.done aria-hidden="true" className="size-3.5 shrink-0 text-success" />
  ) : (
    <span aria-hidden="true" className="size-3.5 shrink-0 rounded-full border-[1.5px] border-attention" />
  );
}

/** A country set's heading: every set asks much what the last one did, so a muted group heading and a gap alone run
 *  them together. The name is a title over a rule, the one ruled heading in a long form (frontend-conventions,
 *  "divided by group headings"), with the tile's line for that country at its end. */
const COUNTRY_HEADING = "flex w-full items-center gap-3 border-t border-border pt-6 text-title-medium text-foreground";

function SummaryRow({ done, label, words }: { done: boolean; label: string; words: string }) {
  return (
    <span className="flex items-center gap-1.5 text-foreground">
      <DoneMark done={done} />
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
  const codes = useCountryCodes();
  const asksCitizenship = citizenshipField(questionSet) !== undefined;
  // A citizenship held by name (a hand edit) settles nothing until it is stored as codes, so it is not done.
  const citizenDone = citizenshipAnswered(profile, questionSet, codes);
  const citizens = citizenshipEntries(profile).map(nameOf);
  const rows = questionSet.countries.map((country) => ({
    key: country.market,
    label: country.label,
    ...countryLine(profile, questionSet, country.market),
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
 * "From your citizenship (India)", with Answer differently, which brings its control back, and the expiry is not
 * asked (that right does not run out). An answer you give wins over it; one that differs settles nothing else
 * there (`derivedPermits`), and a note says why those are asked.
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
  const market = country.market;
  // What a citizenship settled here while this was open, kept across the questions read again: a later answer
  // that differs from it says so.
  const served = country.derived ?? {};
  const [settledBefore, setSettledBefore] = useState<Record<string, DerivedAnswer>>(served);
  if (Object.entries(served).some(([key, d]) => settledBefore[key]?.via !== d.via || settledBefore[key]?.value !== d.value)) {
    setSettledBefore({ ...settledBefore, ...served });
  }
  // The settled questions you answer yourself: from Answer differently, and from any change to one, so a control
  // in use never turns back into words under you (an answer set to Not set, the questions read again).
  const [answering, setAnswering] = useState<readonly string[]>([]);
  const answerYourself = (key: string) => {
    if (key in served || key in settledBefore) setAnswering((keys) => (keys.includes(key) ? keys : [...keys, key]));
  };
  const focusNext = useFocusOnNextCommit();
  const idPrefix = `af-permit-${market}`;

  const entry = permitEntry(profile, market);
  const line = countryLine(profile, questionSet, market);
  const derived = derivedPermits(profile, questionSet, market);
  const answers = permitAnswers(profile, questionSet, market);
  const fields = shownPermitFields(profile, questionSet, market, answering);
  const differs = Object.keys(derived).length === 0 && differsFromSettled(profile, questionSet, market, settledBefore);
  const settled: Record<string, ReactNode> = {};
  const hints: Record<string, string> = {};
  for (const field of fields) {
    const by = derived[field.key];
    if (!by || answered(field, entry[field.key])) continue;
    if (answering.includes(field.key)) {
      hints[field.key] = `Left unset, your citizenship answers ${answerWords(field, by.value)}.`;
      continue;
    }
    const controlId = `${idPrefix}-${field.key}`;
    settled[field.key] = (
      <>
        <p className="text-body-medium">{answerWords(field, by.value)}</p>
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="text-body-small text-muted-foreground">From your citizenship ({nameOf(by.via)})</span>
          <Button
            type="button"
            variant="link"
            size="sm"
            className="h-auto p-0"
            onClick={() => {
              answerYourself(field.key);
              // The button goes with its row: its control takes focus once it shows.
              focusNext({
                get current() {
                  return document.getElementById(controlId);
                },
              });
            }}
          >
            Answer differently
          </Button>
        </span>
      </>
    );
  }
  return (
    <fieldset className="space-y-4">
      <legend className={COUNTRY_HEADING}>
        <span className="min-w-0 flex-1 truncate">{country.label}</span>
        <span className="flex shrink-0 items-center gap-1.5 text-body-small text-muted-foreground">
          {/* The group's name reads "India, can work now", never the two run together. */}
          <span className="sr-only">, </span>
          <DoneMark done={line.done} />
          {line.words}
        </span>
      </legend>
      {differs ? (
        <p className="text-body-small text-muted-foreground">
          Your answer differs from what your citizenship settles, so these are asked.
        </p>
      ) : null}
      <FieldGrid
        idPrefix={idPrefix}
        group={`permit-${market}`}
        fields={fields}
        values={entry}
        shownBy={answers}
        settled={settled}
        hints={hints}
        onChange={(key, next) => {
          answerYourself(key);
          update(SURFACE, (current) => withPermit(current, questionSet, market, key, next));
        }}
      />
      {country.answers.length ? (
        <FieldGrid
          idPrefix={`af-answer-${market}`}
          group={`answer-${market}`}
          fields={country.answers}
          values={countryAnswerEntry(profile, country)}
          onChange={(key, next) => update(SURFACE, (current) => withCountryAnswer(current, country, key, next))}
        />
      ) : null}
    </fieldset>
  );
}

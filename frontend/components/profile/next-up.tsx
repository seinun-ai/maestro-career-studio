"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Check } from "lucide-react";

import { useAutofillProfile } from "@/components/profile/autofill-profile";
import { FieldControl } from "@/components/profile/field-control";
import { diversityCountries } from "@/components/profile/diversity";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { Button } from "@/components/ui/button";
import { LeadCard } from "@/components/ui/lead-card";
import { ProgressCount } from "@/components/visual";
import {
  answered,
  booleanAnswer,
  fieldValue,
  groupCount,
  groupValues,
  homeMarket,
  missingAnswers,
  missingKey,
  permitCount,
  permitEntry,
  withField,
  withPermit,
  type MissingAnswer,
} from "@/lib/autofill-options";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import type { MarketSettingResponse } from "@/lib/types";

const SURFACE = "next-up";

/** The tile each missing answer belongs to, named as the tile is. */
const SECTION = { permit: "Work permits", personal: "Contact", preferences: "Start and pay" } as const;

const YES_NO = [
  { value: true, label: "Yes" },
  { value: false, label: "No" },
] as const;

/**
 * Next up, the Lead: the first required answer still missing (lib/autofill-options.ts `missingAnswers`: each
 * country's work permit first), answered in place and saved as you go, beside the promise that these answers
 * only ever come from you. A Yes or No moves on by itself; a typed answer stays until Next, so it never
 * jumps away mid-word. Skip leaves one for later in this visit. Diversity is answered in its fold, beside its
 * consent (D10), so Next up only opens it. Nothing missing, nothing shown: the ring says so.
 */
export function NextUp({
  market,
  onOpenDiversity,
}: {
  market: MarketSettingResponse;
  onOpenDiversity: () => void;
}) {
  const { profile, update, saveState } = useAutofillProfile();
  const [skipped, setSkipped] = useState<readonly string[]>([]);
  // The question being typed into: it stays up until Next, though it is answered from the first letter.
  const [held, setHeld] = useState<MissingAnswer | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const questionId = useId();
  const controlId = useId();

  const markets = market.markets ?? [];
  const missing = missingAnswers(profile, market.apply_in, markets, market.home);
  const open = missing.filter((item) => !skipped.includes(missingKey(item)));
  const current = held ?? open[0] ?? null;
  const currentKey = current ? missingKey(current) : null;

  // The next question takes focus at its heading once you answer or skip one; never on load.
  const shown = useRef(currentKey);
  const moved = useRef(false);
  useEffect(() => {
    if (moved.current && shown.current !== currentKey) headingRef.current?.focus();
    shown.current = currentKey;
  }, [currentKey]);

  if (!current) {
    if (!missing.length) return null;
    return (
      <div className="group/row flex flex-wrap items-center gap-x-3 gap-y-1 text-body-medium">
        <span>
          {missing.length === 1 ? "1 answer" : `${missing.length} answers`} skipped for now.
        </span>
        <Button type="button" variant="link" size="sm" className="h-auto p-0" onClick={() => setSkipped([])}>
          Ask again
        </Button>
      </div>
    );
  }

  const next = () => {
    moved.current = true;
    setHeld(null);
  };
  const skip = () => {
    moved.current = true;
    setHeld(null);
    setSkipped((list) => [...list, missingKey(current)]);
  };
  const aside = (
    <>
      <span className="inline-flex items-center gap-2 text-title-small">
        <CONCEPT_ICONS.locked aria-hidden="true" className="size-4" />
        Never guessed for you
      </span>
      <span className="text-body-small text-muted-foreground">
        Work-permit and diversity answers only ever come from you.
      </span>
    </>
  );

  if (current.kind === "diversity") {
    const countries = diversityCountries(market);
    return (
      <LeadCard
        eyebrow="Next up · Diversity questions"
        aside={aside}
        action={{ label: "Answer or decline", onClick: onOpenDiversity }}
        secondary={
          <Button type="button" variant="ghost" className="text-muted-foreground" onClick={skip}>
            Skip
          </Button>
        }
      >
        <h2 ref={headingRef} tabIndex={-1} className="text-headline-small outline-none">
          The voluntary diversity questions
        </h2>
        <p className="max-w-[65ch] text-body-medium text-muted-foreground">
          Asked where a set is checked against official forms: {countries.join(", ")}. Answer them or decline,
          beside the permission that lets the Companion use them.
        </p>
      </LeadCard>
    );
  }

  const field = current.field;
  const country = current.kind === "permit" ? markets.find((m) => m.key === current.market) : undefined;
  const section = current.kind === "permit" ? SECTION.permit : SECTION[current.group];
  const count =
    current.kind === "permit"
      ? permitCount(profile, current.market, country?.work_auth_vocab)
      : groupCount(profile, current.group, homeMarket(market));
  const raw =
    current.kind === "permit" ? permitEntry(profile, current.market)[field.key] : groupValues(profile, current.group)[field.key];
  const answer = (value: string | boolean | undefined) =>
    update(SURFACE, (profileNow) =>
      current.kind === "permit"
        ? withPermit(profileNow, current.market, field.key, value)
        : withField(profileNow, current.group, field.key, value),
    );

  return (
    <LeadCard
      eyebrow={`Next up · ${section}${country ? ` · ${country.label}` : ""}`}
      aside={aside}
      action={field.boolean ? undefined : { label: "Next", onClick: next, disabled: !answered(field, raw) }}
      secondary={
        <>
          <Button type="button" variant="ghost" className="text-muted-foreground" onClick={skip}>
            Skip
          </Button>
          <AutosaveStatus {...saveState(SURFACE)} />
        </>
      }
    >
      <ProgressCount done={count.answered} total={count.answerable} noun="answered" />
      <h2 id={questionId} ref={headingRef} tabIndex={-1} className="text-headline-small outline-none">
        {field.boolean ? field.label : <label htmlFor={controlId}>{field.label}</label>}
      </h2>
      {field.boolean ? (
        <div role="group" aria-labelledby={questionId} className="flex flex-wrap gap-2">
          {YES_NO.map((option) => {
            const on = booleanAnswer(raw) === option.value;
            return (
              <Button
                key={option.label}
                type="button"
                size="lg"
                variant={on ? "tonal" : "outline"}
                aria-pressed={on}
                onClick={() => {
                  answer(option.value);
                  next();
                }}
              >
                {on ? <Check aria-hidden="true" /> : null}
                {option.label}
              </Button>
            );
          })}
        </div>
      ) : (
        <div className="max-w-sm">
          <FieldControl
            id={controlId}
            group={current.kind === "permit" ? `permit-${current.market}` : current.group}
            field={field}
            value={fieldValue(field, raw)}
            onChange={(value) => {
              setHeld(current);
              answer(value);
            }}
          />
        </div>
      )}
    </LeadCard>
  );
}

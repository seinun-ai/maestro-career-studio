"use client";

import { useId } from "react";

import { useAutofillProfile } from "@/components/profile/autofill-profile";
import { DiversityConsentSwitch, useDiversityConsent } from "@/components/profile/diversity-consent";
import { FieldGrid } from "@/components/profile/field-control";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { Button } from "@/components/ui/button";
import { Fold } from "@/components/ui/fold";
import {
  RACE_STAYS_YOURS,
  declinedEeo,
  diversityCountries,
  groupCount,
  groupFields,
  groupValues,
  isBlank,
  staleAnswers,
  withField,
} from "@/lib/autofill-options";
import type { EeoConsent, MarketSettingResponse, QuestionSet } from "@/lib/types";

const SURFACE = "diversity";

/**
 * Diversity questions, folded: voluntary, asked only where a country you apply in has a checked set, with
 * the permission that lets the Companion use them beside them (owner decision D10) and the date it was
 * given. The answers are one set, the one the Companion maps to each checked form's own words
 * (`content/eeo.js`); the fold names the countries it serves, from the served set (`diversityCountries`), so
 * with no country chosen it names none. Saves as you go.
 */
export function DiversityFold({
  market,
  questionSet,
  consent,
  open,
  onOpenChange,
}: {
  market: MarketSettingResponse;
  questionSet: QuestionSet;
  consent: EeoConsent;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { profile, update, saveState } = useAutofillProfile();
  const { pending, setEeoConsentEnabled } = useDiversityConsent(consent);
  const declineHintId = useId();
  const countries = diversityCountries(questionSet, market.markets ?? []);
  const eeo = groupValues(profile, "eeo");
  const count = groupCount(profile, questionSet, "eeo");
  const hasAnswers = groupFields(questionSet, "eeo").some((field) => !isBlank(eeo[field.key]));
  const allDeclined =
    count.answered > 0 && groupFields(questionSet, "eeo").every((f) => f.type !== "select" || eeo[f.key] === "decline");
  // Answers count as given (setup readiness counts them) whether or not the Companion may use them; while
  // it may not, it fills none (`withhold_unconsented`), and the summary says so.
  const summary = countries.length
    ? [
        "Voluntary",
        countries.join(", "),
        allDeclined ? "set to decline" : `${count.answered} of ${count.answerable} answered`,
        ...(consent.enabled ? [] : ["the Companion won't fill these until you let it"]),
      ].join(" · ")
    : questionSet.chosen
      ? "Not asked where you apply"
      : "No country chosen yet";
  const stale = staleAnswers(profile).flatMap((item) => (item.startsWith("eeo.") ? [item.slice(4)] : []));

  const declineAllEeo = () => {
    const declines = declinedEeo(profile, questionSet);
    if (!Object.keys(declines).length) return;
    update(SURFACE, (current) => ({ ...current, eeo: { ...groupValues(current, "eeo"), ...declines } }));
  };

  return (
    // A Fold takes no id: the card id its deep links name sits on the div around it.
    <div id="autofill-eeo">
      <Fold title="Diversity questions" summary={summary} open={open} onOpenChange={onOpenChange}>
        <div className="@container/setting grid gap-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <p className="max-w-[65ch] text-body-small text-muted-foreground">
              {countries.length
                ? `Asked only where a set is checked against official forms: ${countries.join(", ")}.`
                : questionSet.chosen
                  ? "None of the countries you apply in has a checked set of these questions, so the Companion won't ask them."
                  : "No country chosen yet. These are asked only where a country you apply in has a checked set."}
            </p>
            <AutosaveStatus {...saveState(SURFACE)} />
          </div>
          {countries.length || hasAnswers ? (
            <>
              <DiversityConsentSwitch
                consent={consent}
                pending={pending}
                onChange={(next) => void setEeoConsentEnabled(next)}
              />
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  aria-describedby={declineHintId}
                  onClick={declineAllEeo}
                >
                  Decline the rest
                </Button>
                <p id={declineHintId} className="text-muted-foreground text-body-small">
                  Fills each blank diversity question with its decline choice. {RACE_STAYS_YOURS}
                </p>
              </div>
              <FieldGrid
                idPrefix="af-eeo"
                group="eeo"
                fields={groupFields(questionSet, "eeo")}
                values={eeo}
                stale={stale}
                voluntary
                onChange={(key, next) => update(SURFACE, (current) => withField(current, questionSet, "eeo", key, next))}
              />
            </>
          ) : null}
        </div>
      </Fold>
    </div>
  );
}

"use client";

import { useAutofillProfile } from "@/components/profile/autofill-profile";
import { FieldGrid } from "@/components/profile/field-control";
import { TileCard, type TileView } from "@/components/profile/tile";
import { useAutofillQuery } from "@/components/profile/use-autofill-query";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { SettingCardAction } from "@/components/settings/setting-card";
import { GROUP_HEADING } from "@/components/settings/setting-layout";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import {
  booleanAnswer,
  permitCount,
  permitEntry,
  permitFields,
  withPermit,
} from "@/lib/autofill-options";
import type { MarketOption, MarketSettingResponse, QuestionSet } from "@/lib/types";
import { cn } from "@/lib/utils";

const SURFACE = "permits";

/** One country's line on the tile: its answers in words, from what is stored, never a guess. */
function permitWords(entry: Record<string, unknown>, answered: number, answerable: number): string {
  if (answered === 0) return "not answered";
  if (answered < answerable) return `${answered} of ${answerable} answered`;
  const now = booleanAnswer(entry.authorized_now);
  return now === true ? "can work now" : now === false ? "can't work there now" : "answered";
}

/** Work permits: one set per country you apply in, each in that country's own words (as served). */
export function useWorkPermitsTile(market: MarketSettingResponse, questionSet: QuestionSet): TileView {
  const { profile } = useAutofillProfile();
  const byKey = new Map((market.markets ?? []).map((m) => [m.key, m]));
  const rows = market.apply_in.map((key) => {
    const count = permitCount(profile, questionSet, key);
    return { key, label: byKey.get(key)?.label ?? key, count, entry: permitEntry(profile, key) };
  });
  const open = rows.some((row) => row.count.answered < row.count.answerable);
  return {
    state: open ? { kind: "needs" } : { kind: "ready" },
    summary: (
      <span className="flex flex-col gap-1">
        {rows.map((row) => {
          const done = row.count.answered === row.count.answerable;
          return (
            <span key={row.key} className="flex items-center gap-1.5 text-foreground">
              {done ? (
                <CONCEPT_ICONS.done aria-hidden="true" className="size-3.5 shrink-0 text-success" />
              ) : (
                <span aria-hidden="true" className="size-3.5 shrink-0 rounded-full border-[1.5px] border-attention" />
              )}
              <span className="min-w-0 flex-1 truncate">{row.label}</span>
              <span className="text-muted-foreground">{permitWords(row.entry, row.count.answered, row.count.answerable)}</span>
            </span>
          );
        })}
      </span>
    ),
    note: "Never guessed for you",
    panel: <WorkPermitsCard market={market} questionSet={questionSet} />,
  };
}

function WorkPermitsCard({ market, questionSet }: { market: MarketSettingResponse; questionSet: QuestionSet }) {
  const query = useAutofillQuery();
  return (
    <TileCard
      tile="permits"
      description="Each country asks this its own way. A form gets the answers of the country its question names, else the job's country, else the Companion asks you on that job."
      errorTitle="Couldn't load your form answers."
      query={query}
    >
      {() => <WorkPermitsEditor applyIn={market.apply_in} markets={market.markets ?? []} questionSet={questionSet} />}
    </TileCard>
  );
}

/** One fieldset per country you apply in, named by the country; each answer is that country's own entry
 *  in `work_auth_by_country`, keyed by market ("UK", not the ISO "GB"). */
function WorkPermitsEditor({
  applyIn,
  markets,
  questionSet,
}: {
  applyIn: string[];
  markets: MarketOption[];
  questionSet: QuestionSet;
}) {
  const { profile, update, saveState } = useAutofillProfile();
  return (
    // Groups are divided by their headings and a wide gap, never by rules. Each fieldset stays in block
    // flow: a rendered <legend> is not a grid item, so a grid gap would never separate it from the first field.
    <div className="grid gap-8">
      <SettingCardAction>
        <AutosaveStatus {...saveState(SURFACE)} />
      </SettingCardAction>
      {applyIn.map((key) => {
        const label = markets.find((m) => m.key === key)?.label ?? key;
        return (
          <fieldset key={key} className="space-y-4">
            <legend className={cn(GROUP_HEADING, "flex items-center gap-1.5")}>
              <CONCEPT_ICONS.workAuthorization aria-hidden="true" className="size-4" />
              {label}
            </legend>
            <FieldGrid
              idPrefix={`af-permit-${key}`}
              group={`permit-${key}`}
              fields={permitFields(questionSet, key)}
              values={permitEntry(profile, key)}
              onChange={(fieldKey, next) => update(SURFACE, (current) => withPermit(current, key, fieldKey, next))}
            />
          </fieldset>
        );
      })}
    </div>
  );
}

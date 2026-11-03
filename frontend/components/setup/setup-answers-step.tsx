"use client";

import { useEffect, useId, useRef, type RefObject } from "react";
import { Check } from "lucide-react";

import { useAdoptServed, useSaveAnswers } from "@/components/profile/autofill-profile";
import { FillFromResumeButton, useFillFromResume } from "@/components/profile/contact";
import { useCountryCodes } from "@/components/country-picker";
import { CITIZEN_HINT, CitizenshipPicker } from "@/components/profile/citizenship-picker";
import { DiversityConsentSwitch, useDiversityConsent } from "@/components/profile/diversity-consent";
import { FieldControl, FieldGrid } from "@/components/profile/field-control";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import type { DiversityChoice } from "@/components/setup/setup-flow";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  RACE_STAYS_YOURS,
  booleanAnswer,
  citizenshipEntries,
  citizenshipField,
  fieldHint,
  fieldValue,
  groupFields,
  groupValues,
  isBlank,
  noticeLegacyNote,
  permitEntry,
  profileForEditing,
  staleAnswers,
} from "@/lib/autofill-options";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import {
  noticeDays,
  noticeField,
  permitAsks,
  questionAnswered,
  willingToRelocate,
  withCitizenshipAnswer,
  withDiversityAnswer,
  withDiversityDeclined,
  withPermitAnswer,
  withPreference,
} from "@/lib/setup-answers";
import { questionKey, type AutofillProfile, type FormQuestion } from "@/lib/setup-flow";
import type { EeoConsent, QuestionSet } from "@/lib/types";
import { useAutosave } from "@/lib/use-autosave";
import { cn } from "@/lib/utils";

/** The quick notice choices and the days each stores; the box takes any other number. */
const NOTICE_CHOICES: readonly { value: number; label: string }[] = [
  { value: 0, label: "Now" },
  { value: 14, label: "2 weeks" },
  { value: 30, label: "1 month" },
  { value: 90, label: "3 months" },
];

type Update = (next: (current: AutofillProfile) => AutofillProfile) => void;

/** The form answers Setup edits, and their save: what `useSetupAnswers` returns. */
export type SetupAnswers = {
  value: AutofillProfile;
  update: Update;
  pending: boolean;
  failed: boolean;
  retry: () => void;
};

/**
 * The form answers, held by the flow (components/setup/setup-flow.tsx) so Continue can wait for a save, and
 * saved as Profile saves them (`useSaveAnswers`: a save that changes a citizenship reads the questions again
 * before it lands). Each country's legacy pair is read as typed answers, and a newer copy (the Companion learned
 * an answer while this tab was away) is taken only while every edit is on the server, as is what the server made
 * of a save (citizenships as codes) once it lands. A failed write leaves answers on screen the server lacks, so
 * leaving asks first, as in Profile.
 */
export function useSetupAnswers(served: AutofillProfile): SetupAnswers {
  const save = useSaveAnswers();
  const answers = useAutosave<AutofillProfile>(profileForEditing(served), (next) => save.mutateAsync(next));
  useLeaveGuard(answers.failed);
  useAdoptServed(served, answers.adopt, answers.pending);
  return answers;
}

/** A one-of-a-few answer: buttons that say which is chosen (`aria-pressed` and a Check), in a named group. */
function Choices<T extends string | number | boolean>({
  labelledBy,
  options,
  value,
  onPick,
}: {
  labelledBy: string;
  options: readonly { value: T; label: string }[];
  value: T | undefined;
  onPick: (value: T) => void;
}) {
  return (
    <div role="group" aria-labelledby={labelledBy} className="flex flex-wrap gap-2">
      {options.map((option) => {
        const on = value === option.value;
        return (
          <Button
            key={String(option.value)}
            type="button"
            variant={on ? "tonal" : "outline"}
            aria-pressed={on}
            onClick={() => onPick(option.value)}
          >
            {on ? <Check aria-hidden="true" /> : null}
            {option.label}
          </Button>
        );
      })}
    </div>
  );
}

const YES_NO = [
  { value: true, label: "Yes" },
  { value: false, label: "No" },
] as const;

/**
 * Step 4, the answers job forms ask, one question at a time. Citizenship comes first, with its country picker,
 * since it settles some work permits. Then one card per country you apply in that is left to ask, named by its
 * heading and asked in that country's words (as served for it: the visa status only where that country asks
 * it; each answer's group is labelled by the country and the question, so a country's answer is never asked or
 * heard without it), and only what your citizenship does not settle (`permitAsks`); then notice period and
 * relocation; then diversity, only for a country with a checked set. Each answer saves to the autofill
 * profile as you go (`PUT /api/settings/autofill`, the country's own entry in `work_auth_by_country`, never
 * the one-set `work_auth`). Contact fields fill from career history in place. Diversity is answered or
 * declined in place, and only once the diversity consent is on record (the same confirm and server stamp as
 * Profile's switch, which sits beside the answers here too, D10).
 */
export function SetupAnswersStep({
  answers,
  opened,
  questionSet,
  consent,
  questions,
  question,
  onQuestion,
  onDone,
  diversity,
  onDiversity,
  headingRef,
}: {
  answers: SetupAnswers;
  /** The answers when Setup opened: a permit answered then is not asked again (`permitAsks`). */
  opened: AutofillProfile;
  questionSet: QuestionSet;
  consent: EeoConsent;
  questions: FormQuestion[];
  question: number;
  onQuestion: (index: number) => void;
  onDone: () => void;
  diversity: DiversityChoice;
  onDiversity: (choice: DiversityChoice) => void;
  headingRef: RefObject<HTMLHeadingElement | null>;
}) {
  const codes = useCountryCodes();
  const current = questions[question];
  const currentKey = current ? questionKey(current) : null;
  const questionRef = useRef<HTMLHeadingElement>(null);
  const shown = useRef(currentKey);
  // The next question takes focus at its heading; the step's own heading has it on arrival. A card added or
  // dropped before this one moves its number, never the focus.
  useEffect(() => {
    if (shown.current !== currentKey) questionRef.current?.focus();
    shown.current = currentKey;
  }, [currentKey]);

  const advance = () => (question < questions.length - 1 ? onQuestion(question + 1) : onDone());

  return (
    <section aria-labelledby="setup-answers-title" className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1.5">
          <h2 id="setup-answers-title" ref={headingRef} tabIndex={-1} className="text-headline-small outline-none">
            Answers every job form asks
          </h2>
          <p className="max-w-[65ch] text-body-medium text-muted-foreground">
            Give them once. The Companion fills them in for you.
          </p>
        </div>
        <AutosaveStatus className="ml-auto" pending={answers.pending} failed={answers.failed} onRetry={answers.retry} />
      </div>

      <ContactFromHistory profile={answers.value} update={answers.update} />

      {current ? (
        <div className="flex flex-col gap-5 rounded-corner-lg bg-card p-6">
          <div className="flex items-center justify-between gap-3">
            <span className="text-label-medium text-muted-foreground tabular-nums">
              {question + 1} of {questions.length}
            </span>
            {/* Round means a state: green only for a question that holds its answer, never one passed by. */}
            <span aria-hidden="true" className="flex gap-1">
              {questions.map((q, i) => (
                <span
                  key={i}
                  className={cn(
                    "size-1.5 rounded-full",
                    i === question
                      ? "bg-primary"
                      : questionAnswered(q, answers.value, questionSet, codes)
                        ? "bg-success"
                        : "bg-surface-container-high",
                  )}
                />
              ))}
            </span>
          </div>
          <Question
            question={current}
            headingRef={questionRef}
            profile={answers.value}
            opened={opened}
            questionSet={questionSet}
            consent={consent}
            update={answers.update}
            advance={advance}
            diversity={diversity}
            onDiversity={onDiversity}
          />
        </div>
      ) : null}
    </section>
  );
}

/** Your name, email and phone for forms, filled in place from your career history (Profile's Fill from
 *  career history: blank fields only, never over an answer you gave). Shown while the email is still blank. */
function ContactFromHistory({ profile, update }: { profile: AutofillProfile; update: Update }) {
  const fill = useFillFromResume(profile, update);
  if (!isBlank(groupValues(profile, "personal").email)) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-body-medium">
      <span>Your name, email and phone for forms come from your resume.</span>
      <FillFromResumeButton fill={fill} />
      {!fill.contactReady ? (
        <p id={fill.fillHintId} className="w-full text-body-small text-muted-foreground">
          {fill.resumeDisabledReason}
        </p>
      ) : null}
    </div>
  );
}

/** What every question card is handed: the heading that takes focus, the answers, the questions they answer
 *  and how to change them, how to move on, and the diversity consent and choice. */
type QuestionProps = {
  headingRef: RefObject<HTMLHeadingElement | null>;
  profile: AutofillProfile;
  opened: AutofillProfile;
  questionSet: QuestionSet;
  consent: EeoConsent;
  update: Update;
  advance: () => void;
  diversity: DiversityChoice;
  onDiversity: (choice: DiversityChoice) => void;
};

function Question({ question, ...props }: QuestionProps & { question: FormQuestion }) {
  const { headingRef, profile, opened, questionSet, update, advance } = props;
  const titleId = useId();
  const noticeId = useId();
  if (question.kind === "citizenship") {
    return <CitizenshipQuestion headingRef={headingRef} profile={profile} questionSet={questionSet} update={update} />;
  }
  if (question.kind === "permit") {
    return (
      <PermitQuestion
        question={question}
        headingRef={headingRef}
        profile={profile}
        opened={opened}
        questionSet={questionSet}
        update={update}
      />
    );
  }
  if (question.kind === "notice") {
    // Notice in days, as Profile asks it: a choice stores its days, the box any other number. A choice reads as
    // picked from the days held, compared as numbers (the server sends 14; the box holds "14" until it lands).
    const field = noticeField(questionSet);
    const values = groupValues(profile, "preferences");
    const days = noticeDays(profile);
    const hint = field ? fieldHint(field, noticeLegacyNote(field, values)) : "";
    const hintId = hint ? `${noticeId}-hint` : undefined;
    return (
      <div className="flex flex-col gap-4">
        <h3 id={titleId} ref={headingRef} tabIndex={-1} className="text-title-large outline-none">
          How soon could you start?
        </h3>
        <Choices
          labelledBy={titleId}
          options={NOTICE_CHOICES}
          value={days}
          onPick={(choice) => {
            update((current) => withPreference(current, questionSet, "notice_days", choice));
            advance();
          }}
        />
        {field ? (
          <div className="grid max-w-sm gap-1.5">
            <Label htmlFor={noticeId}>{field.label}</Label>
            {hint ? (
              <p id={hintId} className="text-muted-foreground text-body-small">
                {hint}
              </p>
            ) : null}
            <FieldControl
              id={noticeId}
              group="preferences"
              field={field}
              value={fieldValue(field, values[field.key])}
              hintId={hintId}
              onChange={(next) => update((current) => withPreference(current, questionSet, "notice_days", next))}
            />
          </div>
        ) : null}
      </div>
    );
  }
  if (question.kind === "relocate") {
    const value = willingToRelocate(profile);
    return (
      <div className="flex flex-col gap-4">
        <h3 id={titleId} ref={headingRef} tabIndex={-1} className="text-title-large outline-none">
          Open to moving for a job?
        </h3>
        <Choices
          labelledBy={titleId}
          options={YES_NO}
          value={value}
          onPick={(answer) => {
            update((current) => withPreference(current, questionSet, "willing_to_relocate", answer));
            advance();
          }}
        />
        <p className="text-body-small text-muted-foreground">Used when a form asks about relocation.</p>
      </div>
    );
  }
  return <DiversityQuestion countries={question.countries} {...props} />;
}

/**
 * Diversity, answer or decline, in place. Either needs the diversity consent first: a pick asks for it in the
 * same words as Profile's switch (`DIVERSITY_CONSENT_CONFIRM`) and the server stamps when it was given, and
 * nothing is stored until that yes is on record. Cancel stores nothing and picks nothing. Decline the rest,
 * as in Profile, sets each blank question that has a decline choice to it and moves on (race or ethnicity is
 * typed, so it stays blank, and the step says so); answering shows the questions here, beside the switch
 * that covers them.
 */
function DiversityQuestion({
  countries,
  headingRef,
  profile,
  questionSet,
  consent,
  update,
  advance,
  diversity,
  onDiversity,
}: QuestionProps & { countries: string[] }) {
  const titleId = useId();
  const { pending, setEeoConsentEnabled } = useDiversityConsent(consent);
  const pick = async (choice: "answer" | "decline") => {
    const allowed = consent.enabled || (await setEeoConsentEnabled(true));
    if (!allowed) return;
    onDiversity(choice);
    if (choice === "decline") {
      update((current) => withDiversityDeclined(current, questionSet));
      advance();
    }
  };
  const stale = staleAnswers(profile).flatMap((item) => (item.startsWith("eeo.") ? [item.slice(4)] : []));
  return (
    <div className="flex flex-col gap-4">
      <span className="text-label-medium text-primary">{countries.join(", ")}</span>
      <h3 id={titleId} ref={headingRef} tabIndex={-1} className="text-title-large outline-none">
        Diversity questions on forms
      </h3>
      <Choices
        labelledBy={titleId}
        options={[
          { value: "answer", label: "Answer them" },
          { value: "decline", label: "Decline the rest" },
        ]}
        value={consent.enabled ? (diversity ?? undefined) : undefined}
        onPick={(choice) => void pick(choice as "answer" | "decline")}
      />
      <p className="max-w-[65ch] text-body-small text-muted-foreground">
        Voluntary, and asked only where a set is checked against official forms. {RACE_STAYS_YOURS}{" "}
        {consent.enabled
          ? "The Companion may use these answers. You can turn that off here or in Profile."
          : "Either choice first asks whether the Companion may use these answers. Nothing is saved until you allow it."}
      </p>
      {diversity === "answer" && consent.enabled ? (
        <div className="@container/setting grid gap-4">
          <DiversityConsentSwitch
            consent={consent}
            pending={pending}
            onChange={(next) => void setEeoConsentEnabled(next)}
          />
          <FieldGrid
            idPrefix="setup-eeo"
            group="eeo"
            fields={groupFields(questionSet, "eeo")}
            values={groupValues(profile, "eeo")}
            stale={stale}
            voluntary
            onChange={(key, next) => update((current) => withDiversityAnswer(current, questionSet, key, next))}
          />
        </div>
      ) : null}
    </div>
  );
}

/** Citizen of, with its country picker (ISO codes; the United Kingdom read as British citizen), worded as served.
 *  Saving it reads the questions again, so what it settles is known before Continue moves on (the flow waits). */
function CitizenshipQuestion({
  headingRef,
  profile,
  questionSet,
  update,
}: Pick<QuestionProps, "headingRef" | "profile" | "questionSet" | "update">) {
  const pickerId = useId();
  const hintId = useId();
  const field = citizenshipField(questionSet);
  if (!field) return null;
  return (
    <div className="flex flex-col gap-4">
      <h3 ref={headingRef} tabIndex={-1} className="text-title-large outline-none">
        <label htmlFor={pickerId}>{field.label}</label>
      </h3>
      <p id={hintId} className="max-w-[65ch] text-body-small text-muted-foreground">
        {CITIZEN_HINT}
      </p>
      <div className="max-w-md">
        <CitizenshipPicker
          id={pickerId}
          label={field.label}
          describedBy={hintId}
          value={citizenshipEntries(profile)}
          onChange={(codes) => update((current) => withCitizenshipAnswer(current, codes))}
        />
      </div>
    </div>
  );
}

/** One country's work permit: its name as the heading, then the required questions left to ask in its own
 *  words (as served: the visa status first where that country asks it; none your citizenship settles, none
 *  answered before Setup opened: `permitAsks`), each a group named by the country and the question. Every
 *  answer is that country's own entry. Never guessed for you. */
function PermitQuestion({
  question,
  headingRef,
  profile,
  opened,
  questionSet,
  update,
}: {
  question: Extract<FormQuestion, { kind: "permit" }>;
  headingRef: RefObject<HTMLHeadingElement | null>;
  profile: AutofillProfile;
  opened: AutofillProfile;
  questionSet: QuestionSet;
  update: Update;
}) {
  const countryId = useId();
  const baseId = useId();
  const entry = permitEntry(profile, question.market);
  return (
    <div className="flex flex-col gap-4">
      <span className="flex items-center gap-1.5 text-label-medium text-primary">
        <CONCEPT_ICONS.workAuthorization aria-hidden="true" className="size-4" />
        Work permit
      </span>
      <h3 id={countryId} ref={headingRef} tabIndex={-1} className="text-title-large outline-none">
        {question.label}
      </h3>
      <ul className="flex flex-col gap-4">
        {permitAsks(profile, questionSet, question.market, opened).map((q) => {
          const questionId = `${baseId}-${q.key}`;
          return (
            <li key={q.key} className="flex flex-wrap items-center justify-between gap-3">
              <span id={questionId} className="text-body-large">
                {q.label}
              </span>
              {q.boolean ? (
                <div role="group" aria-labelledby={`${countryId} ${questionId}`} className="flex gap-2">
                  {YES_NO.map((option) => {
                    const on = booleanAnswer(entry[q.key]) === option.value;
                    return (
                      <Button
                        key={option.label}
                        type="button"
                        variant={on ? "tonal" : "outline"}
                        aria-pressed={on}
                        onClick={() =>
                          update((current) => withPermitAnswer(current, questionSet, question.market, q.key, option.value))
                        }
                      >
                        {on ? <Check aria-hidden="true" /> : null}
                        {option.label}
                      </Button>
                    );
                  })}
                </div>
              ) : (
                <Select
                  value={typeof entry[q.key] === "string" ? (entry[q.key] as string) : ""}
                  onValueChange={(next) =>
                    update((current) => withPermitAnswer(current, questionSet, question.market, q.key, next ? String(next) : undefined))
                  }
                >
                  <SelectTrigger aria-labelledby={`${countryId} ${questionId}`} className="w-64">
                    <SelectValue placeholder="Choose">
                      {q.options?.find((o) => o.value === entry[q.key])?.label}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {q.options?.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </li>
          );
        })}
      </ul>
      <p className="text-body-small text-muted-foreground">Each country asks this its own way. Never guessed for you.</p>
    </div>
  );
}

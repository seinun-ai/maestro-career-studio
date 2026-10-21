"use client";

import { useEffect, useId, useRef, type RefObject } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { toast } from "sonner";

import { AutosaveStatus } from "@/components/settings/autosave-status";
import type { DiversityChoice } from "@/components/setup/setup-flow";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NextStep } from "@/components/visual";
import { apiFetch } from "@/lib/api";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { couldnt } from "@/lib/error-text";
import {
  PERMIT_QUESTIONS,
  permitAnswers,
  preference,
  withPermitAnswer,
  withPreference,
  type AutofillProfile,
  type FormQuestion,
} from "@/lib/setup-flow";
import { anchorHref } from "@/lib/settings-tabs";
import type { SettingEnvelope, SetupStatus } from "@/lib/types";
import { useAutosave } from "@/lib/use-autosave";
import { cn } from "@/lib/utils";

const NOTICE_CHOICES = ["Now", "2 weeks", "1 month", "3 months"] as const;

function listWords(items: string[]): string {
  return new Intl.ListFormat("en", { type: "conjunction" }).format(items);
}

function isBlank(value: unknown): boolean {
  return typeof value !== "string" || !value.trim();
}

/** A one-of-a-few answer: buttons that say which is chosen (`aria-pressed` and a Check), in a named group. */
function Choices<T extends string | boolean>({
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
 * Step 4, the answers job forms ask, one question at a time. Work permits come first, one card per
 * country you apply in, named by its heading (each question's group is labelled by the country and the
 * question, so a country's answer is never asked or heard without it); then notice period and relocation.
 * Each answer saves to the autofill profile as you go (`PUT /api/settings/autofill`, the country's own
 * entry in `work_auth_by_country`). Diversity comes last and only for a country with a checked set; Setup
 * saves nothing for it: answering opens Profile, where the consent sits beside the answers (D10).
 */
export function SetupAnswersStep({
  profile,
  status,
  questions,
  question,
  onQuestion,
  onDone,
  diversity,
  onDiversity,
  headingRef,
}: {
  profile: AutofillProfile;
  status: SetupStatus;
  questions: FormQuestion[];
  question: number;
  onQuestion: (index: number) => void;
  onDone: () => void;
  diversity: DiversityChoice;
  onDiversity: (choice: DiversityChoice) => void;
  headingRef: RefObject<HTMLHeadingElement | null>;
}) {
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: (next: AutofillProfile) =>
      apiFetch<SettingEnvelope<AutofillProfile>>("/api/settings/autofill", {
        method: "PUT",
        body: JSON.stringify({ value: next }),
      }),
    onSuccess: (result) => {
      qc.setQueryData(["settings", "autofill"], result);
      void qc.invalidateQueries({ queryKey: ["setup-status"] });
    },
    onError: (err: Error) => toast.error(couldnt("save your answers", err)),
  });
  const answers = useAutosave<AutofillProfile>(profile, (next) => save.mutateAsync(next));
  const current = questions[question];
  const questionRef = useRef<HTMLHeadingElement>(null);
  const shown = useRef(question);
  // The next question takes focus at its heading; the step's own heading has it on arrival.
  useEffect(() => {
    if (shown.current !== question) questionRef.current?.focus();
    shown.current = question;
  }, [question]);

  const advance = () => (question < questions.length - 1 ? onQuestion(question + 1) : onDone());
  const personal = answers.value.personal;
  const contactMissing =
    !personal || typeof personal !== "object" || isBlank((personal as Record<string, unknown>).email);

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
        <AutosaveStatus pending={answers.pending} failed={answers.failed} onRetry={answers.retry} />
      </div>

      {contactMissing ? (
        <div className="group/row flex flex-wrap items-center gap-x-3 gap-y-1 text-body-medium">
          <span>Profile fills your name, email and phone from your resume.</span>
          <NextStep label="Fill from career history" href={anchorHref("/profile", "autofill-personal")} />
        </div>
      ) : null}

      {current ? (
        <div className="flex flex-col gap-5 rounded-corner-lg bg-card p-6">
          <div className="flex items-center justify-between gap-3">
            <span className="text-label-medium text-muted-foreground tabular-nums">
              {question + 1} of {questions.length}
            </span>
            <span aria-hidden="true" className="flex gap-1">
              {questions.map((q, i) => (
                <span
                  key={i}
                  className={cn(
                    "size-1.5 rounded-full",
                    i < question ? "bg-success" : i === question ? "bg-primary" : "bg-surface-container-high",
                  )}
                />
              ))}
            </span>
          </div>
          <Question
            question={current}
            headingRef={questionRef}
            profile={answers.value}
            status={status}
            update={answers.update}
            advance={advance}
            diversity={diversity}
            onDiversity={(choice) => {
              onDiversity(choice);
              advance();
            }}
          />
        </div>
      ) : null}
    </section>
  );
}

function Question({
  question,
  headingRef,
  profile,
  status,
  update,
  advance,
  diversity,
  onDiversity,
}: {
  question: FormQuestion;
  headingRef: RefObject<HTMLHeadingElement | null>;
  profile: AutofillProfile;
  status: SetupStatus;
  update: (next: (current: AutofillProfile) => AutofillProfile) => void;
  advance: () => void;
  diversity: DiversityChoice;
  onDiversity: (choice: DiversityChoice) => void;
}) {
  const titleId = useId();
  const noticeId = useId();
  if (question.kind === "permit") {
    return <PermitQuestion question={question} headingRef={headingRef} profile={profile} status={status} update={update} />;
  }
  if (question.kind === "notice") {
    const value = preference(profile, "notice_period");
    const text = typeof value === "string" ? value : "";
    return (
      <div className="flex flex-col gap-4">
        <h3 id={titleId} ref={headingRef} tabIndex={-1} className="text-title-large outline-none">
          How soon could you start?
        </h3>
        <Choices
          labelledBy={titleId}
          options={NOTICE_CHOICES.map((choice) => ({ value: choice, label: choice }))}
          value={NOTICE_CHOICES.find((choice) => choice === text)}
          onPick={(choice) => {
            update((current) => withPreference(current, "notice_period", choice));
            advance();
          }}
        />
        <div className="grid max-w-sm gap-1.5">
          <Label htmlFor={noticeId}>Notice period</Label>
          <Input
            id={noticeId}
            value={text}
            onChange={(e) => {
              const next = e.target.value;
              update((current) => withPreference(current, "notice_period", next));
            }}
          />
        </div>
        <p className="text-body-small text-muted-foreground">Your notice period, in your own words if none fits.</p>
      </div>
    );
  }
  if (question.kind === "relocate") {
    const value = preference(profile, "willing_to_relocate");
    return (
      <div className="flex flex-col gap-4">
        <h3 id={titleId} ref={headingRef} tabIndex={-1} className="text-title-large outline-none">
          Open to moving for a job?
        </h3>
        <Choices
          labelledBy={titleId}
          options={YES_NO}
          value={typeof value === "boolean" ? value : undefined}
          onPick={(answer) => {
            update((current) => withPreference(current, "willing_to_relocate", answer));
            advance();
          }}
        />
        <p className="text-body-small text-muted-foreground">Used when a form asks about relocation.</p>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <span className="text-label-medium text-primary">{listWords(question.countries)}</span>
      <h3 id={titleId} ref={headingRef} tabIndex={-1} className="text-title-large outline-none">
        Diversity questions on forms
      </h3>
      <Choices
        labelledBy={titleId}
        options={[
          { value: "answer", label: "Answer them" },
          { value: "decline", label: "Decline to answer" },
        ]}
        value={diversity ?? undefined}
        onPick={(choice) => onDiversity(choice as DiversityChoice)}
      />
      <p className="max-w-[65ch] text-body-small text-muted-foreground">
        Voluntary, and asked only where a set is checked against official forms. Setup saves nothing here: you
        answer in Profile, beside the permission that lets the Companion use your answers. Declining leaves these
        questions to you on each form.
      </p>
    </div>
  );
}

/** One country's work permit: its name as the heading, then the three knockout answers, each a group named
 *  by the country and the question. Profile holds any answer this card does not ask (the US visa status). */
function PermitQuestion({
  question,
  headingRef,
  profile,
  status,
  update,
}: {
  question: Extract<FormQuestion, { kind: "permit" }>;
  headingRef: RefObject<HTMLHeadingElement | null>;
  profile: AutofillProfile;
  status: SetupStatus;
  update: (next: (current: AutofillProfile) => AutofillProfile) => void;
}) {
  const countryId = useId();
  const baseId = useId();
  const given = permitAnswers(profile, question.market);
  const counted = status.autofill.work_auth_by_country[question.market];
  const allGiven = PERMIT_QUESTIONS.every((q) => given[q.key] !== undefined);
  // Read from the server's count once it has these three: what Profile still asks for this country.
  const more = allGiven && counted ? counted.answerable - counted.answered : 0;
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
        {PERMIT_QUESTIONS.map((q) => {
          const questionId = `${baseId}-${q.key}`;
          return (
            <li key={q.key} className="flex flex-wrap items-center justify-between gap-3">
              <span id={questionId} className="text-body-large">
                {q.label}
              </span>
              <div role="group" aria-labelledby={`${countryId} ${questionId}`} className="flex gap-2">
                {YES_NO.map((option) => {
                  const on = given[q.key] === option.value;
                  return (
                    <Button
                      key={option.label}
                      type="button"
                      variant={on ? "tonal" : "outline"}
                      aria-pressed={on}
                      onClick={() => update((current) => withPermitAnswer(current, question.market, q.key, option.value))}
                    >
                      {on ? <Check aria-hidden="true" /> : null}
                      {option.label}
                    </Button>
                  );
                })}
              </div>
            </li>
          );
        })}
      </ul>
      <p className="text-body-small text-muted-foreground">Each country asks this its own way. Never guessed for you.</p>
      {more > 0 ? (
        <div className="group/row flex flex-wrap items-center gap-x-3 text-body-small">
          <span>
            {more === 1 ? "1 more answer" : `${more} more answers`} for {question.label} in Profile.
          </span>
          <NextStep label="Answer in Profile" href={anchorHref("/profile", "autofill-work_auth")} />
        </div>
      ) : null}
    </div>
  );
}

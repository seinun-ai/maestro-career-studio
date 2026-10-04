/**
 * The What was submitted tab's pure pieces: the pill words, the header line, an answer's anchor,
 * and the voluntary (EEO) questions taken out of their pages. No React, no fetching.
 */
import type { AnswerSource, FilledAnswers, FilledField, FilledStep } from "@/lib/types";

/** One word per source: the pill on every answer. */
export const SOURCE_LABELS: Record<AnswerSource, string> = {
  profile: "Profile",
  resume: "Resume",
  custom: "Custom",
  written: "Written",
  inferred: "Inferred",
  you: "You",
  upload: "Upload",
};

/** "Filled on {host} · {n} pages · {date}". The to-check count follows it as its own control. */
export function receiptHeading(receipt: FilledAnswers, date: string): string {
  const pages = `${receipt.pages} ${receipt.pages === 1 ? "page" : "pages"}`;
  return [`Filled on ${receipt.host ?? "the employer's site"}`, pages, date].filter(Boolean).join(" · ");
}

/** A field's anchor, so the to-check count can jump to the first flagged answer. */
export function fieldAnchor(step: number, section: number, field: number): string {
  return `answer-${step}-${section}-${field}`;
}

/** The pages without their voluntary questions, and those questions on their own. */
export function splitVoluntary(steps: FilledStep[]): { steps: FilledStep[]; voluntary: FilledField[] } {
  const voluntary: FilledField[] = [];
  const kept = steps.map((step) => ({
    ...step,
    sections: step.sections
      .map((section) => {
        voluntary.push(...section.fields.filter((field) => field.eeo));
        return { ...section, fields: section.fields.filter((field) => !field.eeo) };
      })
      .filter((section) => section.fields.length > 0),
  }));
  return { steps: kept.filter((step) => step.sections.length > 0), voluntary };
}

/** The first flagged answer's anchor, or the voluntary group's when only it holds one. */
export function firstFlagged(steps: FilledStep[], voluntary: FilledField[], voluntaryId: string): string | null {
  for (const [s, step] of steps.entries()) {
    for (const [k, section] of step.sections.entries()) {
      const f = section.fields.findIndex((field) => field.flags.length > 0);
      if (f >= 0) return fieldAnchor(s, k, f);
    }
  }
  return voluntary.some((field) => field.flags.length > 0) ? voluntaryId : null;
}

"use client";

import type { RefObject } from "react";

import { GuardedLink as Link } from "@/components/guarded-link";
import { NewTabCue } from "@/components/new-tab-link";
import type { DiversityChoice } from "@/components/setup/setup-flow";
import { Button } from "@/components/ui/button";
import { LeadCard } from "@/components/ui/lead-card";
import { CheckDraw, NextStep } from "@/components/visual";
import { COMPANION_GUIDE_URL, CONNECTED_AGENTS_SETTINGS } from "@/lib/agent-links";
import { answered, groupCount, permitEntry, permitQuestions, profileForEditing } from "@/lib/autofill-options";
import { SETUP_STEPS, type AutofillProfile, type FormQuestion, type StepsDone } from "@/lib/setup-flow";
import { anchorHref } from "@/lib/settings-tabs";
import type { SetupStatus } from "@/lib/types";

const ALSO_CARD =
  "flex h-full flex-col gap-1 rounded-corner-md bg-card px-4.5 py-4 outline-none transition-colors duration-(--duration-short3) ease-standard hover:bg-surface-container-low focus-visible:ring-3 focus-visible:ring-ring";

/**
 * After the four steps: Add your first job is the Lead and the view's one filled button; Connect an agent
 * app and Add the Companion sit under it. It says plainly when a required step is still open (no key or no
 * resume) and what is left in Profile: each country whose work permit you left unanswered, linked to that
 * country's own first open question (never another country's set), and the diversity answers when you chose
 * to give them and left some blank.
 */
export function SetupDone({
  status,
  done,
  profile,
  questions,
  diversity,
  headingRef,
  go,
}: {
  status: SetupStatus;
  done: StepsDone;
  profile: AutofillProfile;
  questions: FormQuestion[];
  diversity: DiversityChoice;
  headingRef: RefObject<HTMLHeadingElement | null>;
  go: (step: number) => void;
}) {
  const ready = status.model_key.done && status.import_resumes.done;
  const personal = profile.personal as Record<string, unknown> | undefined;
  const name = typeof personal?.first_name === "string" ? personal.first_name.trim() : "";
  const open = SETUP_STEPS.flatMap((s, i) => (done[s.id] ? [] : [{ ...s, index: i }]));
  const permitsLeft = questions.flatMap((q) => {
    if (q.kind !== "permit") return [];
    const entry = permitEntry(profileForEditing(profile), q.market);
    const open = permitQuestions(q.vocab).find((field) => !answered(field, entry[field.key]));
    // The country's own control in Profile's Work permits tile (`af-permit-<market>-<key>`).
    return open
      ? [{ label: `Finish your work permit for ${q.label}`, href: anchorHref("/profile", `af-permit-${q.market}-${open.key}`) }]
      : [];
  });
  const eeo = groupCount(profile, "eeo");
  const inProfile = [
    ...permitsLeft,
    ...(diversity === "answer" && eeo.answered < eeo.answerable
      ? [{ label: "Finish the diversity questions", href: anchorHref("/profile", "autofill-eeo") }]
      : []),
  ];

  return (
    <div className="flex flex-col gap-7">
      <LeadCard eyebrow="Start here" action={{ label: "Add your first job", href: "/new" }}>
        <div className="flex items-center gap-3">
          {ready ? <CheckDraw className="size-6" /> : null}
          <h2 ref={headingRef} tabIndex={-1} className="text-headline-small outline-none">
            {ready ? (name ? `You're set, ${name}` : "You're set") : "Almost there"}
          </h2>
        </div>
        <p className="max-w-[65ch] text-body-medium text-muted-foreground">
          {ready
            ? "Start with one job. The rest can wait."
            : "Saving a job reads it with AI, and tailoring starts from your resume: add a key and a resume first."}
        </p>
        {open.length > 0 ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-body-small text-muted-foreground">Not done yet:</span>
            {open.map((s) => (
              <Button key={s.id} type="button" variant="outline" size="sm" onClick={() => go(s.index)}>
                {s.title}
              </Button>
            ))}
          </div>
        ) : null}
      </LeadCard>

      <section aria-labelledby="setup-also" className="flex flex-col gap-2.5">
        <h2 id="setup-also" className="text-title-small text-muted-foreground">
          Also
        </h2>
        <ul className="grid grid-cols-2 gap-3">
          <li>
            <Link href={CONNECTED_AGENTS_SETTINGS} className={ALSO_CARD}>
              <span className="text-title-small">Connect an agent app</span>
              <span className="text-body-small text-muted-foreground">Optional, for automations.</span>
            </Link>
          </li>
          <li>
            <a href={COMPANION_GUIDE_URL} target="_blank" rel="noopener noreferrer" className={ALSO_CARD}>
              <span className="flex items-center gap-1.5 text-title-small">
                Add the Companion
                <NewTabCue />
              </span>
              <span className="text-body-small text-muted-foreground">Fills job forms in your browser.</span>
            </a>
          </li>
        </ul>
      </section>

      {inProfile.length > 0 ? (
        <section aria-labelledby="setup-in-profile" className="flex flex-col gap-1">
          <h2 id="setup-in-profile" className="text-title-small text-muted-foreground">
            Left in Profile
          </h2>
          <ul className="divide-y">
            {inProfile.map((row) => (
              <li key={row.href} className="group/row flex items-center py-2">
                <NextStep label={row.label} href={row.href} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

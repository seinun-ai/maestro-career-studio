"use client";

import { PageHeader } from "@/components/page-shell";
import { useAutofillProfile } from "@/components/profile/autofill-profile";
import { groupValues, isBlank } from "@/lib/autofill-options";
import type { MarketSettingResponse, SetupStatus } from "@/lib/types";

/** The sections setup status counts, ready or not: the form-answer groups it reports (Contact, Work permits,
 *  Start and pay, and Diversity where a country you apply in has a checked set), Jobs you want and How you
 *  come across. Only what the status says, never a count of its own. */
export function readySections(status: SetupStatus): { ready: number; total: number } {
  const groups = Object.values(status.autofill.groups);
  const done = [
    ...groups.map((g) => g.answered >= g.answerable),
    status.job_preferences.done,
    status.persona.done,
  ];
  return { ready: done.filter(Boolean).length, total: done.length };
}

const RADIUS = 22;
const AROUND = 2 * Math.PI * RADIUS;

/** How many sections are ready, as a ring and in words. Round, because it is a state. */
function CompletionRing({ status }: { status: SetupStatus }) {
  const { ready, total } = readySections(status);
  const words = `${ready} of ${total} sections ready`;
  return (
    <div className="flex items-center gap-3">
      <svg width="52" height="52" viewBox="0 0 52 52" role="img" aria-label={words}>
        <circle cx="26" cy="26" r={RADIUS} fill="none" strokeWidth="6" className="stroke-surface-container" />
        <circle
          cx="26"
          cy="26"
          r={RADIUS}
          fill="none"
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={`${total ? (ready / total) * AROUND : 0} ${AROUND}`}
          transform="rotate(-90 26 26)"
          className="stroke-primary transition-[stroke-dasharray] duration-(--duration-medium2) ease-(--ease-standard)"
        />
      </svg>
      <span aria-hidden="true" className="flex flex-col">
        <span className="text-title-medium tabular-nums">
          {ready} of {total}
        </span>
        <span className="text-body-small text-muted-foreground">sections ready</span>
      </span>
    </div>
  );
}

/**
 * Profile's header: your name (from your contact answers, else "Profile"), one line of where you live and
 * where you apply, and how many sections are ready (setup status). No subtitle of words about the page
 * (owner decision D1): the line under the name is your own facts.
 */
export function ProfileHeader({ market, status }: { market: MarketSettingResponse; status: SetupStatus | undefined }) {
  const { profile } = useAutofillProfile();
  const personal = groupValues(profile, "personal");
  const name = [personal.first_name, personal.last_name]
    .filter((part): part is string => !isBlank(part))
    .map((part) => part.trim())
    .join(" ");
  const label = (key: string) => market.markets?.find((m) => m.key === key)?.label ?? key;
  const facts = `Lives in ${label(market.home)} · applies in ${market.apply_in.map(label).join(", ")}`;
  return (
    <PageHeader
      title={name || "Profile"}
      subtitle={facts}
      actions={status ? <CompletionRing status={status} /> : null}
    />
  );
}

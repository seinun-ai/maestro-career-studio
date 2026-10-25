"use client";

import { useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAutofillProfile } from "@/components/profile/autofill-profile";
import { FieldGrid } from "@/components/profile/field-control";
import { TileCard, type TileView } from "@/components/profile/tile";
import { useMarketQuery } from "@/components/profile/where-you-apply";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { SettingCardAction } from "@/components/settings/setting-card";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import {
  groupCount,
  groupFields,
  groupValues,
  homeMarket,
  isBlank,
  withField,
  type Profile,
} from "@/lib/autofill-options";
import { contactAdditions, hasFillableContactDetails } from "@/lib/contact-from-history";
import { couldnt } from "@/lib/error-text";
import type { KBProfileOut } from "@/lib/types";
import { useAutofillQuery } from "@/components/profile/use-autofill-query";

const SURFACE = "contact";

/** Your career history's contact block (`GET /api/kb/profile`), which Fill from career history reads. */
export function useCareerContact() {
  return useQuery({
    queryKey: ["kb", "profile"],
    queryFn: () => apiFetch<KBProfileOut>("/api/kb/profile"),
  });
}

/** Contact: the personal details forms ask, each saved as you go, and Fill from career history. Where you live
 *  (`homeMarket`) names the state line and says whether it counts; until that loads, it counts as "State". */
export function useContactTile(): TileView {
  const { profile } = useAutofillProfile();
  const home = homeMarket(useMarketQuery().data);
  const personal = groupValues(profile, "personal");
  const count = groupCount(profile, "personal", home);
  const shown = ["email", "phone"].map((key) => personal[key]).filter((v): v is string => !isBlank(v));
  return {
    state:
      count.answered === count.answerable
        ? { kind: "ready" }
        : { kind: "count", text: `${count.answered} of ${count.answerable}` },
    summary: <span className="truncate">{shown.length ? shown.join(" · ") : "No email or phone yet"}</span>,
    note: "Your name, address and links for forms",
    panel: <ContactCard />,
  };
}

function ContactCard() {
  const query = useAutofillQuery();
  return (
    <TileCard
      tile="contact"
      description="The Companion types these where a form asks."
      errorTitle="Couldn't load your form answers."
      query={query}
    >
      {() => <ContactEditor />}
    </TileCard>
  );
}

/**
 * Fill from career history: the blank contact fields filled from your career history's contact block, never
 * over an answer you gave. Profile's Contact and Setup's Form answers both offer it, each with its own
 * `update`. While career history has no contact details, `resumeDisabledReason` says why.
 */
export function useFillFromResume(profile: Profile, update: (next: (current: Profile) => Profile) => void) {
  const kbProfile = useCareerContact();
  const [isFillingFromResume, setIsFillingFromResume] = useState(false);
  const fillHintId = useId();

  const contactReady = hasFillableContactDetails(kbProfile.data?.contact);
  const resumeDisabledReason = kbProfile.isLoading
    ? "Loading your career history…"
    : kbProfile.isError
      ? "Couldn't load your career history."
      : "Add your contact details to your career history first.";

  const fillFromResume = async () => {
    setIsFillingFromResume(true);
    try {
      const { contact } = await apiFetch<KBProfileOut>("/api/kb/profile");
      const additions = contactAdditions(groupValues(profile, "personal"), contact);
      const count = Object.keys(additions).length;
      if (!count) {
        toast.info("Nothing new to add");
        return;
      }
      // Read again from the newest answers: a field typed while career history loaded is yours, and stays.
      update((current) => {
        const personal = groupValues(current, "personal");
        return { ...current, personal: { ...personal, ...contactAdditions(personal, contact) } };
      });
      toast.success(`Filled ${count} ${count === 1 ? "field" : "fields"} from your career history`);
    } catch (err) {
      toast.error(couldnt("load your career history", err));
    } finally {
      setIsFillingFromResume(false);
    }
  };

  return { contactReady, resumeDisabledReason, fillHintId, isFillingFromResume, fillFromResume };
}

/** Its button. It reads career history (GET /api/kb/profile), and says so. Disabled, it keeps focus and is
 *  described by `fillHintId`: the reason is text beside it, not a hover. */
export function FillFromResumeButton({ fill }: { fill: ReturnType<typeof useFillFromResume> }) {
  const { contactReady, fillHintId, isFillingFromResume, fillFromResume } = fill;
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      focusableWhenDisabled
      disabled={!contactReady || isFillingFromResume}
      aria-describedby={contactReady ? undefined : fillHintId}
      className="data-disabled:pointer-events-none data-disabled:opacity-50"
      onClick={fillFromResume}
    >
      {isFillingFromResume ? "Filling…" : "Fill from career history"}
    </Button>
  );
}

function ContactEditor() {
  const { profile, update, saveState } = useAutofillProfile();
  const home = homeMarket(useMarketQuery().data);
  const fill = useFillFromResume(profile, (next) => update(SURFACE, next));

  return (
    <div className="grid gap-4">
      <SettingCardAction>
        <AutosaveStatus {...saveState(SURFACE)} />
        <FillFromResumeButton fill={fill} />
      </SettingCardAction>
      {/* A disabled button's reason is text, not a hover. */}
      {!fill.contactReady ? (
        <p id={fill.fillHintId} className="text-muted-foreground text-body-small">
          {fill.resumeDisabledReason}
        </p>
      ) : null}
      <FieldGrid
        idPrefix="af-personal"
        group="personal"
        fields={groupFields("personal", home)}
        values={groupValues(profile, "personal")}
        onChange={(key, next) => update(SURFACE, (current) => withField(current, "personal", key, next))}
      />
    </div>
  );
}

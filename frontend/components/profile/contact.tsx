"use client";

import { useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAutofillProfile } from "@/components/profile/autofill-profile";
import { FieldGrid } from "@/components/profile/field-control";
import { TileCard, type TileView } from "@/components/profile/tile";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { SettingCardAction } from "@/components/settings/setting-card";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import { groupCount, groupFields, groupValues, isBlank, withField } from "@/lib/autofill-options";
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

/** Contact: the personal details forms ask, each saved as you go, and Fill from career history. */
export function useContactTile(): TileView {
  const { profile } = useAutofillProfile();
  const personal = groupValues(profile, "personal");
  const count = groupCount(profile, "personal");
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

function ContactEditor() {
  const { profile, update, saveState } = useAutofillProfile();
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
      update(SURFACE, (current) => {
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

  return (
    <div className="grid gap-4">
      <SettingCardAction>
        <AutosaveStatus {...saveState(SURFACE)} />
        {/* It reads career history (GET /api/kb/profile), and says so. */}
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
      </SettingCardAction>
      {/* A disabled button's reason is text, not a hover. */}
      {!contactReady ? (
        <p id={fillHintId} className="text-muted-foreground text-body-small">
          {resumeDisabledReason}
        </p>
      ) : null}
      <FieldGrid
        idPrefix="af-personal"
        group="personal"
        fields={groupFields("personal")}
        values={groupValues(profile, "personal")}
        onChange={(key, next) => update(SURFACE, (current) => withField(current, "personal", key, next))}
      />
    </div>
  );
}

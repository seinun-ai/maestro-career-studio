"use client";

import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";

import { LoadErrorState } from "@/components/load-error-state";
import { AutofillProfileProvider } from "@/components/profile/autofill-profile";
import { useContactTile } from "@/components/profile/contact";
import { useEeoConsentQuery } from "@/components/profile/diversity-consent";
import { DiversityFold } from "@/components/profile/diversity";
import { useEducationTile } from "@/components/profile/education";
import { EligibilityFold } from "@/components/profile/eligibility";
import { usePersonaTile } from "@/components/profile/how-you-come-across";
import { useJobsTile } from "@/components/profile/jobs-you-want";
import { useLanguagesTile } from "@/components/profile/languages";
import { NextUp } from "@/components/profile/next-up";
import { useQuestionsTile } from "@/components/profile/own-questions";
import { ProfileHeader } from "@/components/profile/profile-header";
import { useStartTile } from "@/components/profile/start-and-pay";
import { TileButton, TileCloseProvider, type TileView } from "@/components/profile/tile";
import { useAutofillQuery } from "@/components/profile/use-autofill-query";
import { useProfileSections } from "@/components/profile/use-profile-sections";
import { useMarketQuery, useWhereTile } from "@/components/profile/where-you-apply";
import { useWorkPermitsTile } from "@/components/profile/work-permits";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { loadErrorDetail } from "@/lib/error-text";
import { PROFILE_TILES, type TileId } from "@/lib/profile-tiles";
import { isLoadFailure } from "@/lib/query-state";
import type { EeoConsent, MarketSettingResponse, SetupStatus } from "@/lib/types";

const regionId = (id: TileId) => `profile-tile-${id}`;
const buttonId = (id: TileId) => `profile-tile-${id}-button`;

/**
 * Profile, facts about you (design refresh Task 7.2, board "Profile, facts about you"): the header (your name,
 * where you live and apply, how many sections are ready), Next up (the Lead: the first required answer still
 * missing, answered in place), nine tiles that each open their editor under the grid, and two folds,
 * Diversity questions and Eligibility. Every answer saves as you go. It needs the answers, the consent
 * record and your countries before it can draw; job preferences and the persona load in their own tiles.
 */
export function ProfileView({ focus }: { focus: (anchor: string) => void }) {
  const setupStatus = useQuery({
    queryKey: ["setup-status"],
    queryFn: () => apiFetch<SetupStatus>("/api/setup/status"),
    refetchOnMount: "always",
  });
  const autofill = useAutofillQuery();
  const consent = useEeoConsentQuery();
  const market = useMarketQuery();
  const queries = [autofill, consent, market];
  const ready = autofill.data && consent.data && market.data;
  const loadFailed = queries.some((q) => isLoadFailure(q));

  if (loadFailed && !ready) {
    return (
      <LoadErrorState
        className="py-8"
        title="Couldn't load your profile."
        detail={loadErrorDetail(queries.find((q) => q.error)?.error)}
        retrying={queries.some((q) => q.isFetching)}
        onRetry={() => queries.forEach((q) => void (isLoadFailure(q) && q.refetch()))}
      />
    );
  }
  if (!autofill.data || !consent.data || !market.data) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-14 w-72" />
        <Skeleton className="h-44 w-full rounded-corner-lg" />
        <Skeleton className="h-80 w-full rounded-corner-md" />
      </div>
    );
  }
  return (
    <AutofillProfileProvider served={autofill.data.value}>
      <ProfileBody status={setupStatus.data} market={market.data} consent={consent.data.value} focus={focus} />
    </AutofillProfileProvider>
  );
}

function ProfileBody({
  status,
  market,
  consent,
  focus,
}: {
  status: SetupStatus | undefined;
  market: MarketSettingResponse;
  consent: EeoConsent;
  focus: (anchor: string) => void;
}) {
  const sections = useProfileSections();
  const tiles: Record<TileId, TileView> = {
    contact: useContactTile(),
    where: useWhereTile(market),
    permits: useWorkPermitsTile(market),
    jobs: useJobsTile(status?.job_preferences.done),
    persona: usePersonaTile(
      status?.persona.done,
      status?.import_resumes.done === true ? undefined : "Import a resume first.",
    ),
    start: useStartTile(),
    education: useEducationTile(),
    languages: useLanguagesTile(),
    questions: useQuestionsTile(),
  };

  // A tile opened from its button hands focus to its editor, which sits under the grid. Instantly: opening
  // one is a frequent action, and frequent actions do not animate.
  const focusOnOpen = useRef<TileId | null>(null);
  useEffect(() => {
    const id = focusOnOpen.current;
    if (!id || sections.tile !== id) return;
    focusOnOpen.current = null;
    const region = document.getElementById(regionId(id));
    region?.focus({ preventScroll: true });
    region?.scrollIntoView({ behavior: "auto", block: "nearest" });
  }, [sections.tile]);

  const toggle = (id: TileId) => {
    if (sections.tile === id) {
      sections.openTile(null);
      return;
    }
    focusOnOpen.current = id;
    sections.openTile(id);
  };
  const close = (id: TileId) => {
    sections.openTile(null);
    document.getElementById(buttonId(id))?.focus();
  };

  return (
    <>
      <ProfileHeader market={market} status={status} />
      <NextUp
        market={market}
        onOpenDiversity={() => {
          sections.setFold("diversity", true);
          focus("autofill-eeo");
        }}
      />
      {/* `autofill` was the Autofill tab's card: a link to it lands on the tiles. */}
      <section id="autofill" aria-label="Facts about you" className="flex flex-col gap-4">
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(16rem,1fr))] gap-3">
          {PROFILE_TILES.map((tile) => (
            <li key={tile.id}>
              <TileButton
                id={tile.id}
                domId={buttonId(tile.id)}
                view={tiles[tile.id]}
                open={sections.tile === tile.id}
                regionId={regionId(tile.id)}
                onToggle={() => toggle(tile.id)}
              />
            </li>
          ))}
        </ul>
        {/* Every editor stays mounted while closed, so a typed draft and its leave guard survive. */}
        {PROFILE_TILES.map((tile) => (
          <div
            key={tile.id}
            id={regionId(tile.id)}
            role="region"
            aria-label={tile.title}
            tabIndex={-1}
            hidden={sections.tile !== tile.id}
            className="outline-none"
          >
            <TileCloseProvider onClose={() => close(tile.id)}>{tiles[tile.id].panel}</TileCloseProvider>
          </div>
        ))}
      </section>
      <div className="flex flex-col gap-2">
        <DiversityFold
          market={market}
          consent={consent}
          open={sections.folds.includes("diversity")}
          onOpenChange={(open) => sections.setFold("diversity", open)}
        />
        <EligibilityFold
          open={sections.folds.includes("eligibility")}
          onOpenChange={(open) => sections.setFold("eligibility", open)}
        />
      </div>
    </>
  );
}

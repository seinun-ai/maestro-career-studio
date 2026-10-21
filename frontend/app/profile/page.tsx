"use client";

import { PageShell } from "@/components/page-shell";
import { ProfileView } from "@/components/profile/profile-view";
import { useFocusSection } from "@/lib/use-focus-section";

/**
 * Who the candidate is: facts about you, as tiles (design refresh Task 7.2, owner decision D11; Settings holds
 * how the app behaves). One page, no tabs: a deep link opens the tile or fold that holds its card
 * (`lib/profile-tiles.ts`), and the page's one `focus` lands it.
 */
export default function ProfilePage() {
  const focus = useFocusSection();
  return (
    <PageShell>
      <ProfileView focus={focus} />
    </PageShell>
  );
}

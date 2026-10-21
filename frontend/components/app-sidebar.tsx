"use client";

import { Suspense, useId, useState } from "react";
import { GuardedLink as Link } from "@/components/guarded-link";
import { usePathname, useSearchParams } from "next/navigation";
import { ChevronRight, FilePlus2, type LucideIcon } from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { buttonVariants } from "@/components/ui/button";
import { MaestroMark } from "@/components/brand-logo";
import { useModKey } from "@/hooks/use-mod-key";
import { useNeedsYouCount } from "@/hooks/use-needs-you-count";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { navCurrent } from "@/lib/nav";
import { needsYouBadge, type NavBadge } from "@/lib/needs-you";
import { shortcutLabel } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: LucideIcon };

// Today first, then the pages a job search lives on (board "Today page"). The rarer tools fold under
// More tools; Profile and Settings sit in the footer. A new route goes in one of these lists.
const MAIN_ITEMS: NavItem[] = [
  { href: "/today", label: "Today", icon: CONCEPT_ICONS.today },
  { href: "/applications", label: "Jobs", icon: CONCEPT_ICONS.jobs },
  { href: "/proposals", label: "Agent inbox", icon: CONCEPT_ICONS.agentInbox },
  { href: "/base-resumes", label: "Base resumes", icon: CONCEPT_ICONS.baseResume },
  { href: "/career", label: "Career history", icon: CONCEPT_ICONS.careerHistory },
  { href: "/analytics", label: "Analytics", icon: CONCEPT_ICONS.analytics },
];

const MORE_TOOLS: NavItem[] = [
  { href: "/automations", label: "Automations", icon: CONCEPT_ICONS.automations },
  { href: "/referrals", label: "Referrals", icon: CONCEPT_ICONS.referrals },
  { href: "/templates", label: "Templates", icon: CONCEPT_ICONS.templates },
  { href: "/chat", label: "Assistant", icon: CONCEPT_ICONS.assistant },
];

const ACCOUNT_ITEMS: NavItem[] = [
  { href: "/profile", label: "Profile", icon: CONCEPT_ICONS.you },
  { href: "/settings", label: "Settings", icon: CONCEPT_ICONS.settings },
];

// The Needs-you count wears the Needs you chip's orange (status-chip.tsx).
// The attention role's container pair, the same as the Needs you chip. It is
// a solid fill, so it holds 4.5:1 on all four row states
// (test_frontend_color_roles.py).
const NEEDS_YOU_BADGE = "bg-attention-container text-on-attention-container";

export function AppSidebar() {
  const pathname = usePathname();
  const mod = useModKey();

  return (
    <Sidebar>
      <SidebarHeader className="flex flex-row items-center justify-between gap-2">
        <div className="flex items-center gap-2 px-2 py-1.5">
          <MaestroMark aria-hidden="true" className="h-5 w-auto shrink-0" />
          <span className="text-title-small">Maestro CS</span>
        </div>
        <SidebarTrigger
          className="shrink-0"
          // Only on screen while the sidebar shows, so a press always hides it.
          title={`Hide sidebar (${shortcutLabel(mod, "B")})`}
          aria-keyshortcuts="Meta+B Control+B"
        />
      </SidebarHeader>
      <SidebarContent>
        {/* `?from=proposals` decides which section a job page sits in, and
            useSearchParams() needs a Suspense boundary for the static prerender
            (Next 16 CSR bailout). The fallback is the same nav with `from`
            UNKNOWN (undefined): a job page then marks no section rather than
            a wrong one; every other route renders exactly the final nav. */}
        <Suspense fallback={<MainNav pathname={pathname} from={undefined} />}>
          <MainNavWithSearch pathname={pathname} />
        </Suspense>
      </SidebarContent>
      <SidebarFooter>
        <SidebarSeparator className="mx-0" />
        <nav aria-label="Account">
          <NavMenu items={ACCOUNT_ITEMS} pathname={pathname} from={null} />
        </nav>
      </SidebarFooter>
    </Sidebar>
  );
}

function MainNavWithSearch({ pathname }: { pathname: string }) {
  const from = useSearchParams().get("from");
  return <MainNav pathname={pathname} from={from} />;
}

function MainNav({ pathname, from }: { pathname: string; from: string | null | undefined }) {
  // One <nav> around the primary destinations, a second around the
  // account pair in the footer: a screen reader's landmark list then
  // names them instead of offering two unlabeled "navigation" entries.
  const fabCurrent = navCurrent(pathname, "/new");
  // Unknown on the server-rendered fallback (no data yet): no badge, the
  // fallback rule (it must not claim state it cannot know).
  const needsYou = needsYouBadge(useNeedsYouCount());
  return (
    <nav aria-label="Main" className="flex flex-col">
      <div className="px-2 pt-2">
        <Link
          href="/new"
          aria-current={fabCurrent}
          className={cn(
            // Current: the full-strength role, M3's selected state for a
            // container-coloured control; the container fill is ~1.05:1 from
            // the active row. Geometry stays the extended FAB either way.
            buttonVariants({ variant: fabCurrent ? "default" : "fab", size: "lg" }),
            "h-10 gap-2.5 rounded-corner-lg px-4",
          )}
        >
          <FilePlus2 className="size-4" aria-hidden="true" />
          Add job
        </Link>
      </div>
      <SidebarGroup>
        <SidebarGroupContent>
          <NavMenu
            items={MAIN_ITEMS}
            pathname={pathname}
            from={from}
            badges={{ "/today": needsYou }}
          />
        </SidebarGroupContent>
      </SidebarGroup>
      <MoreTools pathname={pathname} from={from} />
    </nav>
  );
}

/** The rarer tools behind one disclosure row. Untouched, it is open on a page it holds, so the current
 *  page is never folded out of sight; once pressed, it keeps what you chose from page to page. */
function MoreTools({ pathname, from }: { pathname: string; from: string | null | undefined }) {
  const panelId = useId();
  const holdsCurrent = MORE_TOOLS.some((item) => navCurrent(pathname, item.href, from) !== undefined);
  const [open, setOpen] = useState<boolean | null>(null);
  const expanded = open ?? holdsCurrent;
  return (
    <SidebarGroup className="pt-0">
      <SidebarGroupContent>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              type="button"
              aria-expanded={expanded}
              aria-controls={panelId}
              onClick={() => setOpen(!expanded)}
              className="text-muted-foreground"
            >
              <ChevronRight
                aria-hidden="true"
                className={cn(
                  "transition-[rotate] duration-(--duration-short3) ease-standard",
                  expanded && "rotate-90",
                )}
              />
              <span>More tools</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
        <div id={panelId} hidden={!expanded}>
          <NavMenu items={MORE_TOOLS} pathname={pathname} from={from} />
        </div>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}

function NavMenu({
  items,
  pathname,
  from,
  badges,
}: {
  items: NavItem[];
  pathname: string;
  from: string | null | undefined;
  badges?: Partial<Record<string, NavBadge | null>>;
}) {
  return (
    <SidebarMenu>
      {items.map((item) => {
        const Icon = item.icon;
        const current = navCurrent(pathname, item.href, from);
        const badge = badges?.[item.href] ?? null;
        return (
          <SidebarMenuItem key={item.href}>
            <SidebarMenuButton
              isActive={current !== undefined}
              render={
                <Link
                  href={item.href}
                  aria-current={current}
                  // The count in words, in the name: "Today, 3 need you".
                  // Starts with the visible label (WCAG 2.5.3). Not an
                  // sr-only span: out of flow, Chrome joined it as "Agent
                  // inbox , 3 need you".
                  aria-label={badge ? `${item.label}, ${badge.spoken}` : undefined}
                >
                  <Icon />
                  {/* truncate explicitly: the button's [&>span:last-child]
                      rule no longer reaches the label once a badge follows. */}
                  <span className="min-w-0 truncate">{item.label}</span>
                  {badge ? (
                    // Seen, not read: the link's aria-label says it.
                    <span
                      aria-hidden="true"
                      className={cn(
                        "ml-auto inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full px-1.5 text-label-medium tabular-nums",
                        NEEDS_YOU_BADGE,
                      )}
                    >
                      {badge.text}
                    </span>
                  ) : null}
                </Link>
              }
            />
          </SidebarMenuItem>
        );
      })}
    </SidebarMenu>
  );
}

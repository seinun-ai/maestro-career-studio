"use client";

import { Suspense } from "react";
import { GuardedLink as Link } from "@/components/guarded-link";
import { usePathname, useSearchParams } from "next/navigation";
import {
  Bot,
  FilePlus2,
  Inbox,
  FileText,
  BarChart3,
  BriefcaseBusiness,
  Handshake,
  LayoutTemplate,
  MessageSquare,
  Settings as SettingsIcon,
  UserRound,
  type LucideIcon,
} from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
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
import { navCurrent } from "@/lib/nav";
import { needsYouBadge, type NavBadge } from "@/lib/needs-you";
import { shortcutLabel } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: LucideIcon };

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Job search",
    items: [
      { href: "/applications", label: "Jobs", icon: Inbox },
      { href: "/proposals", label: "Agent inbox", icon: Bot },
      { href: "/referrals", label: "Referrals", icon: Handshake },
    ],
  },
  {
    label: "Career library",
    items: [
      { href: "/career", label: "Career history", icon: BriefcaseBusiness },
      { href: "/base-resumes", label: "Base resumes", icon: FileText },
      { href: "/templates", label: "Templates", icon: LayoutTemplate },
    ],
  },
  {
    label: "Tools",
    items: [
      { href: "/chat", label: "Assistant", icon: MessageSquare },
      { href: "/analytics", label: "Analytics", icon: BarChart3 },
    ],
  },
];

const ACCOUNT_ITEMS: NavItem[] = [
  { href: "/profile", label: "Profile", icon: UserRound },
  { href: "/settings", label: "Settings", icon: SettingsIcon },
];

// The Needs-you count wears the Needs you chip's orange (status-chip.tsx).
// Dark text is orange-300, one step lighter than the chip's orange-400: on the
// current row under the pointer the chip's shade reads 3.88:1, and this one
// holds 4.5:1 on all four row states (test_frontend_color_roles.py).
const NEEDS_YOU_BADGE = "bg-orange-500/10 text-orange-800 dark:text-orange-300";

export function AppSidebar() {
  const pathname = usePathname();
  const mod = useModKey();

  return (
    <Sidebar>
      <SidebarHeader className="flex flex-row items-center justify-between gap-2">
        <div className="flex items-center gap-2 px-2 py-1.5">
          <MaestroMark aria-hidden="true" className="h-5 w-auto shrink-0" />
          <span className="text-sm font-semibold">Maestro CS</span>
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
            "h-10 gap-2.5 rounded-[16px] px-4",
          )}
        >
          <FilePlus2 className="size-4" aria-hidden="true" />
          Add job
        </Link>
      </div>
      {NAV_GROUPS.map((group) => (
        <SidebarGroup key={group.label}>
          <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
          <SidebarGroupContent>
            <NavMenu
              items={group.items}
              pathname={pathname}
              from={from}
              badges={{ "/proposals": needsYou }}
            />
          </SidebarGroupContent>
        </SidebarGroup>
      ))}
    </nav>
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
                  // The count in words, in the name: "Agent inbox, 3 need
                  // you". Starts with the visible label (WCAG 2.5.3). Not an
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
                        "ml-auto inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full px-1.5 text-xs font-medium tabular-nums",
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

"use client";

import { Suspense } from "react";
import Link from "next/link";
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
import { navCurrent } from "@/lib/nav";
import { shortcutLabel } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: LucideIcon };

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Job search",
    items: [
      { href: "/applications", label: "Applications", icon: Inbox },
      { href: "/proposals", label: "Agent Proposals", icon: Bot },
      { href: "/referrals", label: "Referrals", icon: Handshake },
    ],
  },
  {
    label: "Career library",
    items: [
      { href: "/career", label: "Career KB", icon: BriefcaseBusiness },
      { href: "/base-resumes", label: "Base Resumes", icon: FileText },
      { href: "/templates", label: "Templates", icon: LayoutTemplate },
    ],
  },
  {
    label: "Tools",
    items: [
      { href: "/chat", label: "Chat", icon: MessageSquare },
      { href: "/analytics", label: "Analytics", icon: BarChart3 },
    ],
  },
];

const ACCOUNT_ITEMS: NavItem[] = [
  { href: "/profile", label: "Profile", icon: UserRound },
  { href: "/settings", label: "Settings", icon: SettingsIcon },
];

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
          title={`Toggle sidebar (${shortcutLabel(mod, "B")})`}
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
          New application
        </Link>
      </div>
      {NAV_GROUPS.map((group) => (
        <SidebarGroup key={group.label}>
          <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
          <SidebarGroupContent>
            <NavMenu items={group.items} pathname={pathname} from={from} />
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
}: {
  items: NavItem[];
  pathname: string;
  from: string | null | undefined;
}) {
  return (
    <SidebarMenu>
      {items.map((item) => {
        const Icon = item.icon;
        const current = navCurrent(pathname, item.href, from);
        return (
          <SidebarMenuItem key={item.href}>
            <SidebarMenuButton
              isActive={current !== undefined}
              render={
                <Link href={item.href} aria-current={current}>
                  <Icon />
                  <span>{item.label}</span>
                </Link>
              }
            />
          </SidebarMenuItem>
        );
      })}
    </SidebarMenu>
  );
}

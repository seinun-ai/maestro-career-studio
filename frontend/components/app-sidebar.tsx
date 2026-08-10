"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
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
  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`);

  return (
    <Sidebar>
      <SidebarHeader className="flex flex-row items-center justify-between gap-2">
        <div className="px-2 py-1.5 text-sm font-semibold">Maestro CS</div>
        <SidebarTrigger className="shrink-0" />
      </SidebarHeader>
      <SidebarContent>
        {/* One <nav> around the primary destinations, a second around the
            account pair in the footer: a screen reader's landmark list then
            names them instead of offering two unlabeled "navigation" entries. */}
        <nav aria-label="Main" className="flex flex-col">
        <div className="px-2 pt-2">
          <Link
            href="/new"
            className={cn(
              // `tonal` from buttonVariants rather than a hand-rolled copy —
              // this used to re-implement the height, transition and
              // press-scale Button already owns, and drifted from the other 24
              // tonal fills in the process.
              buttonVariants({ variant: "tonal", size: "lg" }),
              "h-10 gap-2.5 rounded-full px-4 hover:shadow-sm",
              isActive("/new") && "bg-primary/15 shadow-sm",
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
              <NavMenu items={group.items} isActive={isActive} />
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
        </nav>
      </SidebarContent>
      <SidebarFooter>
        <SidebarSeparator className="mx-0" />
        <nav aria-label="Account">
          <NavMenu items={ACCOUNT_ITEMS} isActive={isActive} />
        </nav>
      </SidebarFooter>
    </Sidebar>
  );
}

function NavMenu({
  items,
  isActive,
}: {
  items: NavItem[];
  isActive: (href: string) => boolean;
}) {
  return (
    <SidebarMenu>
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <SidebarMenuItem key={item.href}>
            <SidebarMenuButton
              isActive={isActive(item.href)}
              render={
                <Link href={item.href}>
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

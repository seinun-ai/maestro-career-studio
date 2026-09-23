"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ComponentProps, useCallback } from "react";

import { useConfirm } from "@/components/confirm-dialog";
import { allowLeave, leaveBlocked, onSentinel } from "@/lib/leave-guard";

/** True at once when nothing is unsaved, else asks. The one copy of the question. */
export function useConfirmLeave() {
  const confirm = useConfirm();
  return useCallback(
    async () =>
      !leaveBlocked("in-app") ||
      confirm({
        title: "Leave without saving?",
        description: "Changes you haven't saved on this page will be lost.",
        confirmLabel: "Leave",
        cancelLabel: "Stay",
        destructive: true,
      }),
    [confirm],
  );
}

type GuardedLinkProps = Omit<ComponentProps<typeof Link>, "href" | "onNavigate"> & {
  href: string;
};

/**
 * The app's only `next/link` (pinned by test_frontend_leave_guard.py). With nothing
 * unsaved it IS Link. With unsaved work it cancels first and asks second: Link reads
 * `preventDefault` the moment `onNavigate` returns (next/dist/client/app-dir/link.js),
 * so an awaited confirm would be too late. On "Leave" it replays the navigation through
 * the router. Modifier-clicks, downloads and external URLs never reach `onNavigate`, and
 * none of them unmounts this page.
 */
export function GuardedLink({ href, replace, scroll, ...props }: GuardedLinkProps) {
  const router = useRouter();
  const confirmLeave = useConfirmLeave();
  return (
    <Link
      {...props}
      href={href}
      replace={replace}
      scroll={scroll}
      onNavigate={(event) => {
        if (!leaveBlocked("in-app")) return;
        event.preventDefault();
        void confirmLeave().then((leave) => {
          if (!leave) return;
          allowLeave();
          // A push while the sentinel is current would leave that duplicate
          // under the new page, so Back would land on a dead same-URL step.
          if (replace || onSentinel()) router.replace(href, { scroll });
          else router.push(href, { scroll });
        });
      }}
    />
  );
}

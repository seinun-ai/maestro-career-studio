"use client";

import { useId, type ReactNode } from "react";

import { GuardedLink as Link } from "@/components/guarded-link";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** The lead card's one action: a link (`href`) or a press (`onClick`), with an optional leading icon. */
export type LeadAction = { label: string; icon?: ReactNode } & (
  | { href: string; onClick?: never; pending?: never }
  | { onClick: () => void; pending?: boolean; href?: never }
);

/** The Lead tier: the one thing that matters most on a page. An eyebrow in `primary` names it, the
 * content is the caller's, and `action` is the view's one filled button (so the page around it has
 * none). An optional `aside` sits on a quiet panel beside the content and wraps under it when the
 * card is narrow. The card floats a little (`shadow-level1`), the one resting card that does. */
export function LeadCard({ eyebrow, aside, action, children, className }: {
  eyebrow: string;
  aside?: ReactNode;
  action?: LeadAction;
  children: ReactNode;
  className?: string;
}) {
  const eyebrowId = useId();
  return (
    <section
      aria-labelledby={eyebrowId}
      className={cn("flex flex-wrap gap-7 rounded-corner-lg bg-card p-7 shadow-level1", className)}
    >
      <div className="flex min-w-0 flex-[1_1_420px] flex-col gap-4">
        <span id={eyebrowId} className="text-label-medium text-primary">{eyebrow}</span>
        {children}
        {action ? (
          <div className="flex flex-wrap items-center gap-3">
            {action.href !== undefined ? (
              <Button variant="default" size="lg" nativeButton={false} render={<Link href={action.href} />}>
                {action.icon}
                {action.label}
              </Button>
            ) : (
              <Button variant="default" size="lg" pending={action.pending} onClick={action.onClick}>
                {action.icon}
                {action.label}
              </Button>
            )}
          </div>
        ) : null}
      </div>
      {aside ? (
        <div className="flex min-w-0 flex-[0_1_300px] flex-col justify-center gap-3.5 rounded-corner-md bg-surface-container-low p-5">
          {aside}
        </div>
      ) : null}
    </section>
  );
}

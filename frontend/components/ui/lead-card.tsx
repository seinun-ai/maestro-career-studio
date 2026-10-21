"use client";

import { useId, type MouseEvent, type ReactNode } from "react";

import { GuardedLink as Link } from "@/components/guarded-link";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** The lead card's one action: a link (`href`, `external` for a page outside the app, opened in a new tab) or a
 * press (`onClick`), with an optional leading icon. `disabled` keeps it focusable and inert (a write is running):
 * a link refuses the press too, keyboard or not. A link's own `onClick` runs first and may cancel it. */
export type LeadAction = { label: string; icon?: ReactNode; disabled?: boolean } & (
  | { href: string; external?: boolean; onClick?: (event: MouseEvent<HTMLAnchorElement>) => void; pending?: never }
  | { onClick: () => void; pending?: boolean; href?: never; external?: never }
);

function LeadButton({ action }: { action: LeadAction }) {
  const content = (
    <>
      {action.icon}
      {action.label}
    </>
  );
  if (action.href !== undefined) {
    const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
      if (action.disabled) {
        event.preventDefault();
        return;
      }
      action.onClick?.(event);
    };
    return (
      <Button
        variant="default"
        size="lg"
        disabled={action.disabled}
        aria-disabled={action.disabled || undefined}
        focusableWhenDisabled
        nativeButton={false}
        render={
          action.external ? (
            <a href={action.href} target="_blank" rel="noopener noreferrer" onClick={onClick} />
          ) : (
            <Link href={action.href} onClick={onClick} />
          )
        }
      >
        {content}
      </Button>
    );
  }
  return (
    <Button
      variant="default"
      size="lg"
      pending={action.pending}
      disabled={action.disabled}
      focusableWhenDisabled
      onClick={action.onClick}
    >
      {content}
    </Button>
  );
}

/** The Lead tier: the one thing that matters most on a page. An eyebrow in `primary` names it, the
 * content is the caller's, and `action` is the view's one filled button (so the page around it has
 * none). `secondary` sits beside it: quieter controls the caller draws (outline, link, a ⋯), never
 * filled. `footer` goes under the button row: the lead's own rows (the job page's Cover letter and
 * Application questions). `media` is a picture before the content at its own width (the tailored
 * resume's page), and an optional `aside` sits on a quiet panel after it; both wrap under the content
 * when the card is narrow. The card floats a little (`shadow-level1`), the one resting card that does. */
export function LeadCard({ eyebrow, media, aside, action, secondary, footer, children, className }: {
  eyebrow: string;
  media?: ReactNode;
  aside?: ReactNode;
  action?: LeadAction;
  secondary?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const eyebrowId = useId();
  return (
    <section
      aria-labelledby={eyebrowId}
      className={cn("flex flex-wrap gap-7 rounded-corner-lg bg-card p-7 shadow-level1", className)}
    >
      {media ? <div className="flex min-w-0 shrink-0 flex-col">{media}</div> : null}
      <div className="flex min-w-0 flex-[1_1_420px] flex-col gap-4">
        <span id={eyebrowId} className="text-label-medium text-primary">{eyebrow}</span>
        {children}
        {action || secondary ? (
          <div className="flex flex-wrap items-center gap-3">
            {action ? <LeadButton action={action} /> : null}
            {secondary}
          </div>
        ) : null}
        {footer}
      </div>
      {aside ? (
        <div className="flex min-w-0 flex-[0_1_300px] flex-col justify-center gap-3.5 rounded-corner-md bg-surface-container-low p-5">
          {aside}
        </div>
      ) : null}
    </section>
  );
}

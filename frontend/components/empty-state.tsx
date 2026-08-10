import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * The one empty state for list surfaces.
 *
 * There were three: Applications used a dashed box with an icon, a heading, a
 * sentence and a CTA; Proposals used centred text inside a plain Card;
 * Referrals used a single muted sentence with no box at all. Same moment in the
 * same product, told three ways — and the weakest of them (a bare sentence) gave
 * the user nothing to do next.
 *
 * `title` is the state, `description` is what to do about it, `action` is the
 * way to do it. Only the title is required: a filtered-to-nothing list has
 * nothing to offer but the fact, while a genuinely empty one usually should.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-3 rounded-xl border border-dashed py-16 text-center",
        className,
      )}
    >
      {Icon ? <Icon className="text-muted-foreground/50 size-8" /> : null}
      <div>
        <p className="text-sm font-medium">{title}</p>
        {description ? (
          <p className="text-muted-foreground mt-0.5 text-sm">{description}</p>
        ) : null}
      </div>
      {action}
    </div>
  );
}

/**
 * The container a data table sits in on a list page.
 *
 * Applications wrapped its table in a bare `rounded-xl border` div while
 * Referrals wrapped an identical table in a full Card with its own title —
 * so the same content had a heading on one page and not the other, and two
 * different containment treatments. This is the Applications shape, which is
 * the right one: the page header already names the surface, so a card title
 * repeating it is a second heading for one thing.
 */
export function TableFrame({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "animate-fade-rise overflow-hidden rounded-xl border",
        className,
      )}
    >
      {children}
    </div>
  );
}

import { ChevronRight } from "lucide-react";

import { GuardedLink as Link } from "@/components/guarded-link";

/** A row's next step (owner rule D3), one look for every row: your move is a blue text link with a
 * chevron, their move is grey text. The tonal fill shows only while the row is hovered, so the row
 * that uses it carries `group/row`. */
export function NextStep(props: { label: string; href: string } | { waiting: string }) {
  if ("waiting" in props) {
    return <span className="text-body-medium text-muted-foreground tabular-nums">{props.waiting}</span>;
  }
  return (
    <Link
      href={props.href}
      className="-ml-2 inline-flex h-7 items-center gap-0.5 rounded-corner-sm px-2 text-label-large text-primary transition-colors duration-(--duration-short3) ease-standard group-hover/row:bg-secondary-container group-hover/row:text-on-secondary-container"
    >
      {props.label}
      <ChevronRight aria-hidden="true" className="size-3.5 shrink-0" />
    </Link>
  );
}

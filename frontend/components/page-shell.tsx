import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * The one page shell. Every top-level route renders exactly this, so the title
 * always starts at the same x and the vertical rhythm is the same everywhere.
 *
 * It exists because the alternative was measured and it was bad: four widths
 * (6xl/5xl/4xl/3xl) and four gaps (8/6/5/4) assigned per author, and because
 * `mx-auto` centres a narrower cap, the page title walked ~85px sideways as you
 * moved between sidebar items. Nothing about a settings form wants a different
 * left margin than a job list; the variation carried no meaning.
 *
 * **A narrow reading measure is a BODY concern, not a shell concern.** A page
 * whose prose wants ~65 characters wraps its own content in `PageMeasure`; it
 * does not narrow the shell, because that is what moves the header. Keep this
 * split — it is the whole reason the header can no longer drift.
 */
export function PageShell({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <main
      className={cn(
        "mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 p-6",
        className,
      )}
    >
      {children}
    </main>
  );
}

/**
 * A reading-measure column for prose-heavy bodies (health reports, long-form
 * results). Sits INSIDE PageShell, under the header, so the header keeps the
 * shared origin while the text stays readable.
 */
export function PageMeasure({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex w-full max-w-3xl flex-col gap-6", className)}>
      {children}
    </div>
  );
}

/**
 * The one page header. Title, optional one-clause subtitle, optional trailing
 * actions.
 *
 * `actions` is a slot rather than a list of props because the trailing cluster
 * genuinely differs (a button, a button pair, a switch beside a button) — what
 * must NOT differ is the type scale, the baseline, and the wrap behaviour. The
 * cluster carries `ml-auto` and the row wraps, so a long title pushes actions
 * to their own line instead of squeezing the title toward zero width (the job
 * page shipped that bug: `truncate` on a zero-width box renders nothing).
 *
 * Type scale is fixed here on purpose — page title `text-[22px] font-medium
 * tracking-tight`, subtitle `text-sm text-muted-foreground`, one clause. Call
 * sites do not get to restate or override it.
 */
export function PageHeader({
  title,
  subtitle,
  actions,
  leading,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  /** Rendered before the title block — a back button, a monogram. */
  leading?: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn("flex flex-wrap items-start justify-between gap-3", className)}
    >
      {leading}
      <div className="min-w-0 grow basis-[16rem]">
        <h1 className="text-[22px] font-medium tracking-tight">{title}</h1>
        {/* A div, not a <p>: the subtitle slot takes NODES, and the base
            resume header puts an interactive role chip in it. A <div> inside
            a <p> is invalid HTML, and React reported it as a hydration error
            on every load of that page. Prose subtitles render identically. */}
        {subtitle ? (
          <div className="text-muted-foreground text-sm">{subtitle}</div>
        ) : null}
      </div>
      {/* Right-aligned by the header's justify-between, NOT by ml-auto here.
          Both hold the cluster at the right edge while it shares the title's
          line — but when it wraps (the studios' toolbar cannot fit beside a
          title under ~660px, which is every width with the PDF preview open)
          ml-auto held it against the right edge of its OWN line, leaving a
          void under the title. A lone item on a wrapped line sits at the line
          START under space-between, so it aligns with the title instead. The
          unwrapped layout is identical either way. */}
      {actions ? (
        <div className="flex flex-wrap items-center gap-2">
          {actions}
        </div>
      ) : null}
    </header>
  );
}

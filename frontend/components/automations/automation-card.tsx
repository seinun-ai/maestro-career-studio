"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { ChevronDown, CircleCheck, Copy, Globe2, type LucideIcon } from "lucide-react";
import { toast } from "sonner";

import { RunReport } from "@/components/automations/recent-runs";
import { RunOutcome } from "@/components/proposals/run-outcome";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DayStrip, NextStep } from "@/components/visual";
import { useCopy } from "@/hooks/use-copy";
import { agentDisplayName } from "@/lib/agent-name";
import { reportLine } from "@/lib/agent-runs";
import { APPLY_CARD_ID, NEED_LABELS } from "@/lib/automations";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { formatTimeAgo } from "@/lib/format-date";
import type { AgentRun, AutomationCard as AutomationCardData } from "@/lib/types";
import { cn } from "@/lib/utils";

const NEED_ICON: Partial<Record<keyof typeof NEED_LABELS, LucideIcon>> = {
  email: CONCEPT_ICONS.email,
  web: Globe2,
};

/** What a card needs besides Maestro: every card needs Maestro, so that badge would say nothing. */
function Needs({ card }: { card: AutomationCardData }) {
  const needs = card.needs.filter((need) => need !== "maestro");
  if (needs.length === 0) return null;
  return (
    <span className="flex shrink-0 flex-wrap items-center gap-1">
      <span className="sr-only">Needs</span>
      {needs.map((need) => {
        const NeedIcon = NEED_ICON[need];
        return (
          <Badge key={need} variant="tonal">
            {NeedIcon ? <NeedIcon aria-hidden="true" /> : null}
            {NEED_LABELS[need]}
          </Badge>
        );
      })}
    </span>
  );
}

/** The attended Apply session: scheduling it is full automation mode's card, so say where that lives. */
function ApplyNote({ card, className }: { card: AutomationCardData; className?: string }) {
  if (!(card.id === APPLY_CARD_ID && card.kind === "attended")) return null;
  return <p className={cn("text-muted-foreground max-w-[65ch]", className)}>Scheduled applying comes with full automation mode.</p>;
}

/**
 * One Copy prompt per card (D5: the same prompt for any agent app, so no app names). It copies the prompt
 * the backend built; a failed clipboard write opens the prompt under the card, focused, so it can be
 * selected. Returns the button and the place the prompt opens.
 */
function useCopyPrompt(card: AutomationCardData): { button: ReactNode; prompt: ReactNode } {
  const [open, setOpen] = useState(false);
  const promptRef = useRef<HTMLPreElement>(null);
  const focusPromptWhenShown = useRef(false);
  const text = card.prompt;

  // After a failed copy the prompt is the next thing to do: focus lands on it (and selects it) once it is
  // on screen.
  useEffect(() => {
    if (open && focusPromptWhenShown.current) {
      focusPromptWhenShown.current = false;
      promptRef.current?.focus();
    }
  }, [open]);

  // One message on a failed copy: `onError` replaces the hook's own toast, and the fallback below opens the prompt.
  const { copied, copy } = useCopy({
    onError: () => toast.error("Couldn't copy. Select the prompt below instead."),
  });

  async function copyPrompt() {
    const ok = await copy(text);
    if (ok) {
      toast.success("Prompt copied. Paste it into your agent app.");
    } else if (promptRef.current) {
      // Already open: focus it now. Otherwise open it, and the effect focuses it on arrival.
      promptRef.current.focus();
    } else {
      focusPromptWhenShown.current = true;
      setOpen(true);
    }
  }

  const button = (
    <Button variant="tonal" onClick={() => void copyPrompt()}>
      {copied ? <CircleCheck aria-hidden="true" /> : <Copy aria-hidden="true" />}
      {copied ? "Copied" : "Copy prompt"}
    </Button>
  );
  const prompt = open ? (
    <pre
      ref={promptRef}
      tabIndex={0}
      aria-label={`Prompt for ${card.title}`}
      // Keyboard focus selects the prompt alone, so Ctrl+C copies it.
      onFocus={(e) => window.getSelection()?.selectAllChildren(e.currentTarget)}
      className="bg-muted max-h-80 overflow-auto rounded-corner-md p-3 text-body-medium whitespace-pre-wrap select-all"
    >
      {text}
    </pre>
  ) : null;
  return { button, prompt };
}

/**
 * A Reporting card: an automation with a run in its strip's 14 days. Only the run log speaks (MCP
 * `record_run`): the days it reported, its newest report in one line, then Copy prompt and one link to the
 * result. Never a schedule, a connection state or a way to start a run (D5). `runs` are this automation's,
 * newest first.
 */
export function AutomationCard({ card, runs }: { card: AutomationCardData; runs: readonly AgentRun[] }) {
  const { button, prompt } = useCopyPrompt(card);
  const [reportOpen, setReportOpen] = useState(false);
  const headingId = useId();
  const reportId = useId();
  const newest = runs[0];
  const hasReport = !!newest.digest || newest.jobs.length > 0;
  return (
    <article aria-labelledby={headingId} className="group/row flex min-w-0 flex-col gap-4 rounded-corner-md bg-card p-5">
      <div className="flex min-w-0 items-center gap-2">
        <h3 id={headingId} className="min-w-0 flex-1 text-title-medium">
          {card.title}
        </h3>
        <Needs card={card} />
      </div>
      <p className="text-muted-foreground max-w-[65ch]">{card.summary}</p>
      <ApplyNote card={card} />
      <DayStrip runs={runs} />
      <p className="flex min-w-0 flex-wrap items-center gap-2">
        <RunOutcome outcome={newest.outcome} />
        <span className="text-muted-foreground min-w-0 tabular-nums wrap-anywhere">
          {reportLine(newest, agentDisplayName(newest.agent), formatTimeAgo)}
        </span>
      </p>
      {/* gap-4: NextStep pulls itself 8px left to line up in a row. */}
      <div className="mt-auto flex flex-wrap items-center gap-4">
        {button}
        {(newest.counts.proposed ?? 0) > 0 ? (
          <NextStep label="See in Agent inbox" href="/proposals" />
        ) : hasReport ? (
          <Button
            variant="link"
            aria-expanded={reportOpen}
            aria-controls={reportOpen ? reportId : undefined}
            onClick={() => setReportOpen((o) => !o)}
          >
            Last report
            <ChevronDown aria-hidden="true" className={cn("size-3.5", reportOpen && "rotate-180")} />
          </Button>
        ) : null}
      </div>
      {reportOpen ? <RunReport run={newest} id={reportId} /> : null}
      {prompt}
    </article>
  );
}

/**
 * A compact row for an automation with no report in the strip's 14 days: what it does and needs, and Copy
 * prompt. `lastReport` is the finish time of a retained run older than the strip, so the row never reads as
 * never run.
 */
export function AutomationRow({ card, lastReport }: { card: AutomationCardData; lastReport?: string }) {
  const { button, prompt } = useCopyPrompt(card);
  return (
    <li className="flex min-w-0 flex-col gap-3 px-5 py-3">
      <div className="flex min-w-0 items-center gap-4">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <h3 className="text-title-small">{card.title}</h3>
          <p className="text-muted-foreground max-w-[65ch] text-body-small">{card.summary}</p>
          <ApplyNote card={card} className="text-body-small" />
          {lastReport ? (
            <p className="text-muted-foreground text-body-small">{`Last report ${formatTimeAgo(lastReport)}`}</p>
          ) : null}
        </div>
        <Needs card={card} />
        {button}
      </div>
      {prompt}
    </li>
  );
}

/** What each automation never does, one line each: the body of the page's "What each one never does" fold. */
export function NeverList({ cards }: { cards: readonly AutomationCardData[] }) {
  return (
    <dl className="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-6 gap-y-2">
      {cards.map((card) =>
        card.never ? (
          <div key={card.id} className="contents">
            <dt className="text-title-small">{card.title}</dt>
            <dd className="flex max-w-[65ch] items-start gap-1.5">
              <CONCEPT_ICONS.cannot className="text-muted-foreground mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              {card.never}
            </dd>
          </div>
        ) : null,
      )}
    </dl>
  );
}

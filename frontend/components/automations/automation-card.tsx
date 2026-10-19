"use client";

import { useEffect, useId, useRef, useState } from "react";
import { CircleCheck, Copy, Globe2, Hand, Wrench, type LucideIcon } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RunOutcome } from "@/components/proposals/run-outcome";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useCopy } from "@/hooks/use-copy";
import { APPLY_CARD_ID, NEED_LABELS } from "@/lib/automations";
import { formatTimeAgo } from "@/lib/format-date";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { lastRanLine, type RunOutcome as Outcome } from "@/lib/agent-runs";
import type { AutomationCard as AutomationCardData } from "@/lib/types";

const KIND_LABEL = {
  scheduled: "Scheduled",
  attended: "Attended",
  custom: "Custom",
} as const;

const KIND_ICON: Record<keyof typeof KIND_LABEL, LucideIcon> = {
  scheduled: CONCEPT_ICONS.scheduled,
  attended: Hand,
  custom: Wrench,
};

const NEED_ICON: Partial<Record<keyof typeof NEED_LABELS, LucideIcon>> = {
  email: CONCEPT_ICONS.email,
  web: Globe2,
};

/** One automation: what it does, what it needs, what it never does, and the
 * prompt to copy. A failed clipboard write opens the prompt so it can be
 * selected. */
export function AutomationCard({
  card,
  lastRun,
  outcome,
}: {
  card: AutomationCardData;
  /** Undefined while no run data is available, null when this card never ran. */
  lastRun?: string | null;
  /** How that newest run ended; none while unknown or never run. */
  outcome?: Outcome;
}) {
  const [open, setOpen] = useState(false);
  const promptId = useId();
  const promptRef = useRef<HTMLPreElement>(null);
  const focusPromptWhenShown = useRef(false);
  const text = card.prompt;
  const ranLine = lastRanLine(lastRun, formatTimeAgo);
  const KindIcon = KIND_ICON[card.kind];

  // After a failed copy the prompt is the next thing to do: focus lands on it
  // (and selects it) once it is on screen.
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
      // Already open: focus it now. Otherwise open it, and the effect
      // focuses it on arrival (a flag left set would steal a later Show).
      promptRef.current.focus();
    } else {
      focusPromptWhenShown.current = true;
      setOpen(true);
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <CardTitle role="heading" aria-level={2}>
          {card.title}
        </CardTitle>
        <Badge variant="outline">
          <KindIcon aria-hidden="true" />
          {KIND_LABEL[card.kind]}
        </Badge>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="max-w-[65ch]">{card.summary}</p>
        {ranLine ? (
          <p className="text-muted-foreground flex flex-wrap items-center gap-2 text-body-small">
            {lastRun === null ? <CONCEPT_ICONS.notRun className="size-3.5 shrink-0" aria-hidden="true" /> : null}
            {ranLine}
            {lastRun && outcome ? <RunOutcome outcome={outcome} /> : null}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-muted-foreground text-label-medium">Needs</span>
          {card.needs.map((need) => {
            const NeedIcon = NEED_ICON[need];
            return (
              <Badge key={need} variant="tonal">
                {NeedIcon ? <NeedIcon aria-hidden="true" /> : null}
                {NEED_LABELS[need]}
              </Badge>
            );
          })}
        </div>
        {card.never ? (
          <p className="text-muted-foreground flex max-w-[65ch] items-start gap-1.5 text-body-small">
            <CONCEPT_ICONS.cannot className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            {card.never}
          </p>
        ) : null}
        {card.id === APPLY_CARD_ID && card.kind === "attended" ? (
          <p className="text-muted-foreground max-w-[65ch]">
            Scheduled applying comes with full automation mode.
          </p>
        ) : null}
        <div className="flex items-center gap-2">
          <Button onClick={() => void copyPrompt()}>
            {copied ? <CircleCheck aria-hidden="true" /> : <Copy aria-hidden="true" />}
            {copied ? "Copied" : "Copy prompt"}
          </Button>
          <Button
            variant="ghost"
            aria-expanded={open}
            aria-controls={open ? promptId : undefined}
            onClick={() => setOpen((o) => !o)}
          >
            {open ? "Hide prompt" : "Show prompt"}
          </Button>
        </div>
        {open ? (
          <pre
            ref={promptRef}
            id={promptId}
            tabIndex={0}
            aria-label={`Prompt for ${card.title}`}
            // Keyboard focus selects the prompt alone, so Ctrl+C copies it.
            onFocus={(e) => window.getSelection()?.selectAllChildren(e.currentTarget)}
            className="bg-muted max-h-80 overflow-auto rounded-corner-md p-3 text-body-medium whitespace-pre-wrap select-all"
          >
            {text}
          </pre>
        ) : null}
      </CardContent>
    </Card>
  );
}

"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Copy } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { APPLY_CARD_ID, NEED_LABELS, promptFor } from "@/lib/automations";
import type { AgentApp, AutomationCard as AutomationCardData } from "@/lib/types";

const KIND_LABEL = {
  scheduled: "Scheduled",
  attended: "Attended",
  custom: "Custom",
} as const;

/** One automation: what it does, what it needs, what it never does, and the
 * prompt to copy for the chosen app. Copy is off for an app Maestro can't
 * reach; a failed clipboard write opens the prompt so it can be selected. */
export function AutomationCard({
  card,
  app,
  disabledReasonId,
}: {
  card: AutomationCardData;
  app: AgentApp;
  /** The app note that says why Copy is off; Copy points at it. */
  disabledReasonId?: string;
}) {
  const [open, setOpen] = useState(false);
  const promptId = useId();
  const promptRef = useRef<HTMLPreElement>(null);
  const focusPromptWhenShown = useRef(false);
  const text = promptFor(card, app);

  // After a failed copy the prompt is the next thing to do: focus lands on it
  // (and selects it) once it is on screen.
  useEffect(() => {
    if (open && focusPromptWhenShown.current) {
      focusPromptWhenShown.current = false;
      promptRef.current?.focus();
    }
  }, [open]);

  function copy() {
    // `Promise.resolve().then` turns a missing clipboard API (an insecure
    // page), which throws at once, into the same rejection `.catch` handles.
    Promise.resolve()
      .then(() => navigator.clipboard.writeText(text))
      .then(() => toast.success(`Prompt copied. Paste it into ${app.label}.`))
      .catch(() => {
        // Already open: focus it now. Otherwise open it, and the effect
        // focuses it on arrival (a flag left set would steal a later Show).
        if (promptRef.current) promptRef.current.focus();
        else {
          focusPromptWhenShown.current = true;
          setOpen(true);
        }
        toast.error("Couldn't copy. Select the prompt below instead.");
      });
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <CardTitle role="heading" aria-level={2}>
          {card.title}
        </CardTitle>
        <Badge variant="outline">{KIND_LABEL[card.kind]}</Badge>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3">
        <p className="max-w-[65ch]">{card.summary}</p>
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-muted-foreground text-label-medium">Needs</span>
          {card.needs.map((need) => (
            <Badge key={need} variant="tonal">
              {NEED_LABELS[need]}
            </Badge>
          ))}
        </div>
        {card.never ? (
          <p className="text-muted-foreground max-w-[65ch]">{card.never}</p>
        ) : null}
        {card.id === APPLY_CARD_ID && card.kind === "attended" ? (
          <p className="text-muted-foreground max-w-[65ch]">
            Scheduled applying comes with full automation mode.
          </p>
        ) : null}
        <div className="flex items-center gap-2">
          <Button
            onClick={copy}
            disabled={!app.reachable}
            // A disabled <button> drops keyboard focus and says nothing about
            // why; this one stays focusable and points at the app note.
            focusableWhenDisabled
            className="data-disabled:pointer-events-none data-disabled:opacity-50"
            aria-describedby={!app.reachable ? disabledReasonId : undefined}
          >
            <Copy aria-hidden="true" /> Copy prompt
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

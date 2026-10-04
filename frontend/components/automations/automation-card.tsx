"use client";

import { useId, useState } from "react";
import { Copy } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NEED_LABELS, promptFor } from "@/lib/automations";
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
}: {
  card: AutomationCardData;
  app: AgentApp;
}) {
  const [open, setOpen] = useState(false);
  const promptId = useId();
  const text = promptFor(card, app);

  function copy() {
    navigator.clipboard
      .writeText(text)
      .then(() => toast.success(`Prompt copied. Paste it into ${app.label}.`))
      .catch(() => {
        setOpen(true);
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
        {card.id === "apply-session" && card.kind === "attended" ? (
          <p className="text-muted-foreground max-w-[65ch]">
            Scheduled applying comes with full automation mode.
          </p>
        ) : null}
        <div className="mt-auto flex items-center gap-2">
          <Button onClick={copy} disabled={!app.reachable}>
            <Copy aria-hidden="true" /> Copy prompt
          </Button>
          <Button
            variant="ghost"
            aria-expanded={open}
            aria-controls={promptId}
            onClick={() => setOpen((o) => !o)}
          >
            {open ? "Hide prompt" : "Show prompt"}
          </Button>
        </div>
        {open ? (
          <pre
            id={promptId}
            tabIndex={0}
            aria-label={`Prompt for ${card.title}`}
            className="bg-muted max-h-80 overflow-auto rounded-corner-md p-3 text-body-small whitespace-pre-wrap select-all"
          >
            {text}
          </pre>
        ) : null}
      </CardContent>
    </Card>
  );
}

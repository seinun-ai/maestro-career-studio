import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { cn } from "@/lib/utils";

export type ActorKind =
  | "you" | "ai" | "assistant" | "agent" | "careerHistory" | "resume" | "document" | "jobWords" | "merged" | "fromResume";

const ACTORS: Record<ActorKind, { Icon: LucideIcon; word: string }> = {
  you: { Icon: CONCEPT_ICONS.you, word: "You" },
  ai: { Icon: CONCEPT_ICONS.ai, word: "AI" },
  assistant: { Icon: CONCEPT_ICONS.assistant, word: "Assistant" },
  agent: { Icon: CONCEPT_ICONS.agentInbox, word: "Connected agent" },
  careerHistory: { Icon: CONCEPT_ICONS.careerHistory, word: "Career history" },
  resume: { Icon: CONCEPT_ICONS.baseResume, word: "Your resume" },
  document: { Icon: CONCEPT_ICONS.attachment, word: "Document" },
  jobWords: { Icon: CONCEPT_ICONS.jobWords, word: "Job's words" },
  merged: { Icon: CONCEPT_ICONS.merged, word: "Merged" },
  fromResume: { Icon: CONCEPT_ICONS.fromResume, word: "From a resume" },
};

/** Who or what a thing came from: the register's icon plus a word. For an agent pass `agentDisplayName(...)` as `name`. */
export function ActorChip({ kind, name, title, children, className }: {
  kind: ActorKind; name?: string | null; title?: string; children?: ReactNode; className?: string;
}) {
  const { Icon, word } = ACTORS[kind];
  return (
    <span title={title}
      className={cn("inline-flex h-5 shrink-0 items-center gap-1 rounded-full bg-surface-container px-2 text-label-medium text-foreground", className)}>
      <Icon aria-hidden="true" className="size-3 shrink-0" />
      {name || word}
      {children}
    </span>
  );
}

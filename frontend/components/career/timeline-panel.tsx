import {
  Bot,
  CheckCircle2,
  CircleDot,
  FilePlus2,
  ListPlus,
  Send,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatAbsoluteDateTime, formatTimeAgo } from "@/lib/format-date";
import type { KBTimelineEvent } from "@/lib/types";

const ICONS = {
  created: CircleDot,
  doc_added: FilePlus2,
  points_minted: ListPlus,
  point_approved: CheckCircle2,
  point_captured: Bot,
  ported: Send,
};

export function TimelinePanel({ events }: { events: KBTimelineEvent[] }) {
  const ordered = [...events].sort(
    (left, right) => Date.parse(right.ts) - Date.parse(left.ts),
  );

  return (
    <Card className="rounded-2xl">
      <CardHeader>
        <CardTitle>Timeline</CardTitle>
        <p className="text-muted-foreground text-sm">Recent changes to this career item.</p>
      </CardHeader>
      <CardContent>
        {ordered.length === 0 ? (
          <div className="rounded-xl bg-muted/45 px-5 py-7 text-center">
            <p className="text-sm font-medium">No activity yet</p>
            <p className="text-muted-foreground mt-1 text-xs">Changes will appear here as they happen.</p>
          </div>
        ) : (
          <ol className="space-y-4">
            {ordered.map((event, index) => {
              const Icon = ICONS[event.type as keyof typeof ICONS] ?? CircleDot;
              return (
                <li key={`${event.ts}-${event.type}-${index}`} className="flex gap-3">
                  <div className="bg-primary/10 mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full text-primary">
                    <Icon className="size-3.5" aria-hidden="true" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm leading-snug">{event.label}</p>
                    <p
                      className="text-muted-foreground mt-0.5 text-xs"
                      title={formatAbsoluteDateTime(event.ts)}
                    >
                      {formatTimeAgo(event.ts)}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

import { GuardedLink as Link } from "@/components/guarded-link";


import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ChatKbCapture } from "@/lib/types";
import { CONCEPT_ICONS } from "@/lib/concept-icons";

const DraftsIcon = CONCEPT_ICONS.drafts;

export function KbCaptureCard({ capture }: { capture: ChatKbCapture }) {
  return (
    <div className="border-primary/30 bg-primary/5 rounded-corner-md border px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-body-medium">
          <Badge variant="secondary">Career history</Badge>
          <span>
            Saved {capture.point_count}{" "}
            {capture.point_count === 1 ? "draft bullet" : "draft bullets"} to{" "}
            <span className="font-medium">{capture.entity_title}</span>
          </span>
        </div>
        <Button size="sm" variant="ghost" render={<Link href="/career#kb-inbox" />}>
          <DraftsIcon aria-hidden="true" /> Review drafts
        </Button>
      </div>
    </div>
  );
}

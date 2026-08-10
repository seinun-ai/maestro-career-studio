import Link from "next/link";
import { Inbox } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ChatKbCapture } from "@/lib/types";

export function KbCaptureCard({ capture }: { capture: ChatKbCapture }) {
  return (
    <div className="border-primary/30 bg-primary/5 rounded-md border px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm">
          <Badge variant="secondary">Career KB</Badge>
          <span>
            Saved {capture.point_count} {capture.point_count === 1 ? "draft" : "drafts"} for{" "}
            <span className="font-medium">{capture.entity_title}</span>
          </span>
        </div>
        <Button size="sm" variant="ghost" render={<Link href="/career#inbox" />}>
          <Inbox aria-hidden="true" /> Review inbox
        </Button>
      </div>
    </div>
  );
}

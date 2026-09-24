"use client";

import { useId, useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";

import { SettingCard } from "@/components/settings/setting-card";
import { useVersion } from "@/hooks/use-version";
import { FRONTEND_VERSION } from "@/lib/version";
import { cn } from "@/lib/utils";

const GUIDE = "https://github.com/seinun-ai/maestro-career-studio/blob/main/docs/GETTING_STARTED.md";
/** The guide's update step, which says how for each kind of install (pinned against its heading). */
const UPDATE_GUIDE_URL = `${GUIDE}#7-keeping-it-up-to-date`;

/** One term and its value. At 375 the pair wraps, and a 40-character Git SHA
 *  breaks anywhere, instead of pushing the page sideways. */
function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2.5">
      <dt className="text-muted-foreground text-sm">{label}</dt>
      <dd className="min-w-0 text-sm wrap-anywhere">{children}</dd>
    </div>
  );
}

/** A link that opens the user's browser. The app itself never asks GitHub
 *  anything; clicking one is the user opening a page. */
function OutLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="underline underline-offset-4 hover:no-underline"
    >
      {children}
    </a>
  );
}

export function AboutSection() {
  const version = useVersion();

  return (
    <SettingCard
      id="about"
      title="About"
      description="Your app version."
      errorTitle="Couldn't load version info."
      skeleton="h-24 w-full"
      query={version}
    >
      {(data) => (
        <div className="grid gap-2">
          <dl className="divide-y">
            <Row label="Version">
              <span className="font-mono">{data.version}</span>
            </Row>
            <Row label="Updates">
              <OutLink href={UPDATE_GUIDE_URL}>How to update</OutLink>
            </Row>
            <Row label="What's new">
              <OutLink href="https://github.com/seinun-ai/maestro-career-studio/releases">
                Release notes
              </OutLink>
            </Row>
          </dl>
          <TechnicalDetails
            rows={[
              ["Frontend", FRONTEND_VERSION],
              ["Backend", data.version],
              ["Schema revision", data.schema_revision],
              ["Git SHA", data.git_sha ?? "Not recorded"],
            ]}
          />
        </div>
      )}
    </SettingCard>
  );
}

/** The build's parts, for a support question: closed by default, `hidden`
 *  rather than unmounted like the other disclosures here. */
function TechnicalDetails({ rows }: { rows: [string, string][] }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <div className="grid gap-1">
      <button
        type="button"
        className="text-muted-foreground hover:text-foreground flex items-center gap-1 justify-self-start text-xs"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
      >
        <ChevronRight
          className={cn("size-3.5 transition-transform", open && "rotate-90")}
          aria-hidden="true"
        />
        Technical details
      </button>
      <dl id={panelId} hidden={!open} className="divide-y">
        {rows.map(([label, value]) => (
          <Row key={label} label={label}>
            <span className="font-mono">{value}</span>
          </Row>
        ))}
      </dl>
    </div>
  );
}

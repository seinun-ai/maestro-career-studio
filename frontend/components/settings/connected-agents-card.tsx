"use client";

import { useId } from "react";
import { BookOpen } from "lucide-react";

import { GuardedLink as Link } from "@/components/guarded-link";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

// The Agent inbox lane's lib/agent-links.ts takes these three at merge; the pin
// test_the_card_links_point_at_real_headings allows exactly one definition of each.
const REPO = "https://github.com/seinun-ai/maestro-career-studio/blob/main";
const CONNECT_AGENT_GUIDE_URL = `${REPO}/docs/GETTING_STARTED.md#5-connect-your-ai-assistant-optional`;
const JOB_HUNT_SKILL_URL = `${REPO}/docs/skills/README.md`;
const AGENT_APPLICATIONS_URL = `${REPO}/README.md#going-all-the-way-agent-applications`;

const LINKS = [
  { href: CONNECT_AGENT_GUIDE_URL, label: "How to connect an agent" },
  { href: JOB_HUNT_SKILL_URL, label: "Ready-made skills" },
  { href: AGENT_APPLICATIONS_URL, label: "How agent applications work" },
] as const;

/**
 * What a connected agent is, first in Settings › Connected agents, above the
 * next-step hints and the Auto-apply limits it explains.
 *
 * Not a SettingCard: it fetches nothing, so it has no loading or error state
 * (the Appearance precedent). Every "can't" is one the server or the tool set
 * enforces; the one guarantee that is only recorded (the yes before a submit)
 * is said to be a record, not a lock, as the README says. It also names the two
 * helpers that are part of the app, so "connected agent" means only MCP clients.
 */
export function ConnectedAgentsCard() {
  const canId = useId();
  const cantId = useId();
  return (
    <Card id="connected-agents">
      <CardHeader>
        <CardTitle role="heading" aria-level={2}>
          Connected agents
        </CardTitle>
        <CardDescription>
          AI apps on this computer, such as Claude, Codex or the ChatGPT desktop app, that use
          Maestro CS for you. They connect through MCP (Model Context Protocol), the standard
          way AI apps reach other programs.
        </CardDescription>
      </CardHeader>
      <CardContent className="@container/setting">
        <div className="grid gap-6 text-sm">
          <div className="grid gap-4 @lg/setting:grid-cols-2">
            <div className="grid content-start gap-1.5">
              <h3 id={canId} className="font-medium">
                They can
              </h3>
              <ul aria-labelledby={canId} className="text-muted-foreground grid list-disc gap-1 pl-5">
                <li>Save and score jobs, and tailor your resumes.</li>
                <li>Read your career history and job preferences.</li>
                <li>
                  Put the jobs they find in your{" "}
                  <Link href="/proposals" className="text-primary underline underline-offset-4">
                    Agent inbox
                  </Link>{" "}
                  for you to accept or skip.
                </li>
              </ul>
            </div>
            <div className="grid content-start gap-1.5">
              <h3 id={cantId} className="font-medium">
                They can&apos;t
              </h3>
              <ul aria-labelledby={cantId} className="text-muted-foreground grid list-disc gap-1 pl-5">
                <li>Apply to more jobs a day than you allow below.</li>
                <li>Delete anything in your career history.</li>
                <li>Connect from claude.ai or chatgpt.com in a browser.</li>
              </ul>
            </div>
          </div>
          <p className="text-muted-foreground max-w-[65ch]">
            Maestro CS itself never looks for jobs or submits an application. Before each
            submit, the agent asks for your yes and records it. That record is an audit
            trail, not a lock, so run apply sessions while you watch.
          </p>
          <p className="text-muted-foreground max-w-[65ch]">
            Two helpers are part of the app, not connected agents: the Assistant, which you talk
            to inside this app, and Companion, the Maestro CS browser extension, which saves jobs
            and fills application forms in your browser.
          </p>
          <div className="flex flex-wrap gap-2">
            {/* Plain links styled as buttons: Base UI's Button renders an <a> with
                role="button", so a screen reader heard a button that navigates. */}
            {LINKS.map(({ href, label }) => (
              <a
                key={href}
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                <BookOpen className="size-4" aria-hidden="true" />
                {label}
              </a>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

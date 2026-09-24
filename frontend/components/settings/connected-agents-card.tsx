"use client";

import { useId } from "react";
import { BookOpen } from "lucide-react";

import { GuardedLink as Link } from "@/components/guarded-link";
import { NewTabCue } from "@/components/new-tab-link";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { AGENT_APPLICATIONS_URL, CONNECT_AGENT_GUIDE_URL, JOB_HUNT_SKILL_URL } from "@/lib/agent-links";

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
 * (the Appearance precedent). It names the two helpers that are part of the
 * app, so "connected agent" means only MCP clients.
 *
 * Every line is what the MCP tools allow (backend/mcp_server/server.py), no
 * more and no less:
 * - Find jobs, Agent inbox: store_extracted_jd(source="agent"), propose_application.
 *   Accept or skip is yours; record_triage records the decision you state.
 * - Read: get_career_context, kb_list_entities, kb_get_entity, kb_list_points,
 *   get_job_search_brief (location, work authorization, persona).
 * - Add to and change: kb_capture, kb_ingest_resume and kb_edit_point leave
 *   bullets in draft; kb_approve_points approves or retires them, and its "only after
 *   the user said yes" is a docstring rule the agent is given, not a server check;
 *   kb_create_entity, kb_edit_entity and kb_edit_profile write at once.
 * - Resumes: create_base_resume, duplicate_base_resume, update_base_resume,
 *   edit_base_resume, tailor_application, tailor_session, quick_tailor.
 * - Fill in and submit: list_proposals runs accepted proposals only;
 *   get_autofill_profile, generate_qa_answers, prepare_application_pdf_upload
 *   feed the agent's own browser; record_consent records your yes and reserves
 *   a daily-limit slot; mark_submitted needs a receipt or your own word.
 * - Can't delete: no MCP tool deletes an item or a bullet (retire and archive
 *   keep them).
 * - Daily limit: services/proposals._enforce_daily_cap refuses a recorded yes
 *   past the cap (reserved in the last 24 hours). The yes is recorded by the
 *   agent, so the app can't stop one that skips it, as the paragraph says.
 * - Browser apps: stdio MCP on this computer only (docs/GETTING_STARTED.md §5).
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
                <li>
                  Find jobs and file them in your{" "}
                  <Link href="/proposals" className="text-primary underline underline-offset-4">
                    Agent inbox
                  </Link>{" "}
                  for you to queue or skip.
                </li>
                <li>Read your career history and job preferences.</li>
                <li>
                  Add to and change your career history. New or reworded bullets arrive as drafts
                  for you to approve. Other changes, such as an item&apos;s dates or your summary,
                  skills and contact details, apply at once.
                </li>
                <li>
                  Approve bullets, or mark them Not used, in your career history. They&apos;re told to do
                  this only after you say yes. That&apos;s a rule they&apos;re given, not a lock.
                </li>
                <li>Create, edit and tailor your resumes.</li>
                <li>Fill in and submit applications you queued, after your yes.</li>
              </ul>
            </div>
            <div className="grid content-start gap-1.5">
              <h3 id={cantId} className="font-medium">
                They can&apos;t
              </h3>
              <ul aria-labelledby={cantId} className="text-muted-foreground grid list-disc gap-1 pl-5">
                <li>Go past the daily limit below.</li>
                <li>Delete an item or a bullet from your career history.</li>
                <li>Connect from claude.ai or chatgpt.com in a browser.</li>
              </ul>
            </div>
          </div>
          <p className="text-muted-foreground max-w-[65ch]">
            Maestro CS itself never looks for jobs or submits an application. Before each
            submit, the agent asks for your yes and records it. The daily limit below counts
            those yeses over the last 24 hours. The app records each yes but can&apos;t stop an
            agent, so stay with it while it applies.
          </p>
          <p className="text-muted-foreground max-w-[65ch]">
            Two helpers are part of the app, not connected agents: the Assistant, which you talk
            to inside this app, and the Companion, the Maestro CS browser extension, which saves jobs
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
                <NewTabCue />
              </a>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

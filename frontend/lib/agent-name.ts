/**
 * Who filed a proposal, in words. `proposed_by` is stored raw: "you" for the
 * web app's Queue in Agent inbox, an MCP client's self-declared
 * clientInfo.name ("claude-ai", "codex-mcp-client") for a
 * connected agent, null when unknown. Pure (lib/agent-name.test.ts); pinned by
 * test_frontend_agent_inbox.py. Also names a KB point's writer.
 */

/** Known clients by product, matched on a whole word of the name ("precursor-bot" is not Cursor). */
const KNOWN_WORDS: ReadonlyArray<readonly [string, string]> = [
  ["claude", "Claude"],
  ["codex", "Codex"],
  ["chatgpt", "ChatGPT"],
  ["cursor", "Cursor"],
  ["windsurf", "Windsurf"],
  ["gemini", "Gemini"],
];
/** Known clients by their whole name. ChatGPT's connectors send "openai-mcp" (not verified against a
 *  primary source: plan open question 8); any other "openai-…" name is some script, read as its words. */
const KNOWN_NAMES: Readonly<Record<string, string>> = { "openai-mcp": "ChatGPT" };
/** Words that only say "an MCP client": the Python MCP SDK's default clientInfo.name is "mcp". */
const GENERIC_WORDS = new Set(["mcp", "client"]);
const ACRONYMS = new Set(["ai", "api", "cli", "ide", "mcp"]);

/** One word of an unknown name: an acronym in capitals, a lower-case word
 *  capitalised, and a word the client already cased ("iPhone", "クロード")
 *  kept as sent. */
function titleWord(word: string): string {
  if (ACRONYMS.has(word.toLowerCase())) return word.toUpperCase();
  if (word !== word.toLowerCase()) return word;
  return word.charAt(0).toUpperCase() + word.slice(1);
}

/** "Claude" for "claude-ai"; an unknown name title-cased ("my-agent" →
 *  "My Agent"), never shown as a slug; null for "you", nothing, or a name
 *  that says only "an MCP client". */
export function agentDisplayName(raw: string | null | undefined): string | null {
  const name = (raw ?? "").trim();
  if (!name || name.toLowerCase() === "you") return null;
  const known = KNOWN_NAMES[name.toLowerCase()];
  if (known) return known;
  const words = name.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean);
  for (const [word, label] of KNOWN_WORDS) {
    if (words.includes(word)) return label;
  }
  if (words.every((word) => GENERIC_WORDS.has(word))) return null;
  return name
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map(titleWord)
    .join(" ");
}

/** Statuses a proposal you filed can have only if its accept never happened. */
const NEVER_QUEUED = new Set(["pending_review", "needs_decision", "expired"]);

/** "Proposed by Claude"; "Queued by you" (a web Queue accepts at once), or
 *  "Proposed by you" when that accept never happened; "Proposed by a
 *  connected agent" when the filer is unknown (null). An older backend does
 *  not send the filer (undefined): nothing is claimed, so no by-line. */
export function proposalByLine(proposedBy: string | null | undefined, status: string): string | null {
  if (proposedBy === undefined) return null;
  if (proposedBy === "you") return NEVER_QUEUED.has(status) ? "Proposed by you" : "Queued by you";
  return `Proposed by ${agentDisplayName(proposedBy) ?? "a connected agent"}`;
}

/** The tracker's mark on an application with `source: "agent"`. Only LINKING a proposal sets it
 *  (routers/proposals.py `_validate_and_stamp_application`, `services/proposals.record_decision`):
 *  you may have made the application yourself, and queued it yourself, so no agent "found" it. */
export const LINKED_APPLICATION_MARK = "Linked to a proposal in Agent inbox";

/** The tracker's mark on an agent-captured saved job: the newest proposal's filer
 *  when an agent filed one, else the capture itself. */
export function agentMarkLabel(proposedBy: string | null | undefined): string {
  const name = agentDisplayName(proposedBy);
  return name ? `Proposed by ${name}` : "Found by a connected agent";
}

/**
 * What a Queue in Agent inbox found (lib/api.ts `promoteJobToAgentQueue`): the
 * proposal's filer ("you", a client name, null unknown, undefined from a
 * backend that does not say) and its status when the POST returned it. Only a
 * Proposed one (`pending_review`) was queued: the backend accepts from there
 * alone.
 */
export type QueueResult = { proposedBy: string | null | undefined; status: string };

/** Why a Queue left an open proposal as it was: every open status but pending_review. */
const ALREADY: Readonly<Record<string, string>> = {
  needs_decision: "it needs you",
  needs_human: "it needs you",
  accepted: "it's already queued",
  approved: "it's being applied to",
};

/**
 * The toast after Queue in Agent inbox. The POST keeps a job's open proposal
 * and its first filer, so a Queue on a job a connected agent had just
 * proposed stays "Proposed by <agent>" wherever its by-line shows; the toast
 * says why, once, where the user acted, and says so when nothing was queued.
 */
export function queuedToast({ proposedBy, status }: QueueResult): string {
  const agent =
    proposedBy === undefined || proposedBy === "you"
      ? null
      : (agentDisplayName(proposedBy) ?? "A connected agent");
  if (status === "pending_review") {
    return agent ? `Queued in your Agent inbox. ${agent} proposed it first.` : "Queued in your Agent inbox.";
  }
  const why = ALREADY[status];
  if (agent) return `Already in your Agent inbox. ${agent} proposed it first${why ? `, and ${why}` : ""}.`;
  return why ? `Already in your Agent inbox. ${why.charAt(0).toUpperCase()}${why.slice(1)}.` : "Already in your Agent inbox.";
}

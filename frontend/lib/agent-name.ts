/**
 * Who filed a proposal, in words. `proposed_by` is stored raw: "you" for the
 * web app's Queue in Agent inbox, an MCP client's self-declared
 * clientInfo.name ("claude-ai", "codex-mcp-client") for a
 * connected agent, null when unknown. Pure (lib/agent-name.test.ts); pinned by
 * test_frontend_agent_inbox.py.
 */
const KNOWN: ReadonlyArray<readonly [RegExp, string]> = [
  [/claude/i, "Claude"],
  [/codex/i, "Codex"],
  // ChatGPT's own clientInfo.name is unverified (plan open question 8):
  // either word matches it.
  [/chatgpt|openai/i, "ChatGPT"],
  [/cursor/i, "Cursor"],
  [/windsurf/i, "Windsurf"],
  [/gemini/i, "Gemini"],
];
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
 *  "My Agent"), never shown as a slug; null for "you" or nothing. */
export function agentDisplayName(raw: string | null | undefined): string | null {
  const name = (raw ?? "").trim();
  if (!name || name.toLowerCase() === "you") return null;
  for (const [pattern, label] of KNOWN) {
    if (pattern.test(name)) return label;
  }
  return name
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map(titleWord)
    .join(" ");
}

/** "Proposed by Claude", "Queued by you" (a web promotion is queued at once),
 *  or "Proposed by a connected agent" when the filer is unknown. */
export function proposalByLine(proposedBy: string | null | undefined): string {
  if (proposedBy === "you") return "Queued by you";
  return `Proposed by ${agentDisplayName(proposedBy) ?? "a connected agent"}`;
}

/** The tracker's mark on an agent-captured row: the newest proposal's filer
 *  when an agent filed one, else the capture itself. */
export function agentMarkLabel(proposedBy: string | null | undefined): string {
  const name = agentDisplayName(proposedBy);
  return name ? `Proposed by ${name}` : "Found by a connected agent";
}

/**
 * The toast after Queue in Agent inbox. The POST keeps a job's open proposal
 * and its first filer, so a Queue on a job a connected agent had just
 * proposed stays "Proposed by <agent>" wherever its by-line shows; the toast
 * says why, once, where the user acted. `undefined` is a backend that does
 * not report the filer: claim nothing.
 */
export function queuedToast(proposedBy: string | null | undefined): string {
  if (proposedBy === undefined || proposedBy === "you") return "Queued in your Agent inbox.";
  const by = agentDisplayName(proposedBy) ?? "A connected agent";
  return `Queued in your Agent inbox. ${by} proposed it first.`;
}

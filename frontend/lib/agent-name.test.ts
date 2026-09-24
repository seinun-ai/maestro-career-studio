import assert from "node:assert/strict";
import { test } from "node:test";

import { agentDisplayName, agentMarkLabel, proposalByLine, queuedToast } from "./agent-name.ts";

test("known clients read as their product", () => {
  assert.equal(agentDisplayName("claude-ai"), "Claude");
  assert.equal(agentDisplayName("Claude Desktop"), "Claude");
  assert.equal(agentDisplayName("claude-code"), "Claude");
  assert.equal(agentDisplayName("codex-mcp-client"), "Codex");
  assert.equal(agentDisplayName("openai-mcp"), "ChatGPT");
  assert.equal(agentDisplayName("ChatGPT"), "ChatGPT");
  assert.equal(agentDisplayName("cursor-vscode"), "Cursor");
});

test("a known name matches whole words only", () => {
  assert.equal(agentDisplayName("precursor-bot"), "Precursor Bot");
  assert.equal(agentDisplayName("claudette"), "Claudette");
  assert.equal(agentDisplayName("my_codex_fork"), "Codex"); // a whole word
  // Only the known ChatGPT client name is ChatGPT; another OpenAI script reads as its words.
  assert.equal(agentDisplayName("openai-agents-python"), "Openai Agents Python");
  assert.equal(agentDisplayName("openai"), "Openai");
});

test("the MCP SDK's default name says nothing about who it is", () => {
  for (const raw of ["mcp", "MCP", " mcp ", "mcp-client"]) assert.equal(agentDisplayName(raw), null, raw);
  assert.equal(proposalByLine("mcp", "pending_review"), "Proposed by a connected agent");
  assert.equal(agentMarkLabel("mcp"), "Found by a connected agent");
});

test("an unknown client is title-cased, never a slug", () => {
  assert.equal(agentDisplayName("my-agent"), "My Agent");
  assert.equal(agentDisplayName("mcp_inspector"), "MCP Inspector");
  assert.equal(agentDisplayName("  job   hunter  "), "Job Hunter");
});

test("a name the client cased, or wrote in another script, shows as sent", () => {
  assert.equal(agentDisplayName("iPhone Helper"), "iPhone Helper");
  assert.equal(agentDisplayName("Café Agent"), "Café Agent");
  assert.equal(agentDisplayName("café-agent"), "Café Agent");
  assert.equal(agentDisplayName("クロード"), "クロード");
  assert.equal(agentDisplayName("Ассистент"), "Ассистент");
});

test("you and nothing are not agent names", () => {
  for (const raw of ["you", "You", "", "  ", null, undefined]) assert.equal(agentDisplayName(raw), null);
});

test("the by-line", () => {
  assert.equal(proposalByLine("claude-ai", "pending_review"), "Proposed by Claude");
  assert.equal(proposalByLine("you", "accepted"), "Queued by you");
  assert.equal(proposalByLine("you", "approved"), "Queued by you");
  assert.equal(proposalByLine(null, "accepted"), "Proposed by a connected agent");
  assert.equal(proposalByLine("クロード", "needs_human"), "Proposed by クロード");
});

test("your Queue whose accept never happened is not Queued by you", () => {
  for (const status of ["pending_review", "needs_decision", "expired"]) {
    assert.equal(proposalByLine("you", status), "Proposed by you", status);
  }
});

test("an older backend that does not say who filed it: no by-line at all", () => {
  for (const status of ["pending_review", "accepted"]) assert.equal(proposalByLine(undefined, status), null);
});

test("the tracker mark falls back to the capture", () => {
  assert.equal(agentMarkLabel("codex-mcp-client"), "Proposed by Codex");
  assert.equal(agentMarkLabel("you"), "Found by a connected agent");
  assert.equal(agentMarkLabel(null), "Found by a connected agent");
});

test("a Queue that joined an agent's proposal says whose it stays", () => {
  const q = (proposedBy: string | null | undefined) => queuedToast({ proposedBy, status: "pending_review" });
  assert.equal(q("you"), "Queued in your Agent inbox.");
  assert.equal(q(undefined), "Queued in your Agent inbox.");
  assert.equal(q("claude-ai"), "Queued in your Agent inbox. Claude proposed it first.");
  assert.equal(q(null), "Queued in your Agent inbox. A connected agent proposed it first.");
});

test("a Queue on a proposal past review says where it is, and queues nothing", () => {
  const q = (proposedBy: string | null | undefined, status: string) => queuedToast({ proposedBy, status });
  assert.equal(q("claude-ai", "needs_decision"), "Already in your Agent inbox. Claude proposed it first, and it needs you.");
  assert.equal(q("codex-mcp-client", "needs_human"), "Already in your Agent inbox. Codex proposed it first, and it needs you.");
  assert.equal(q("claude-ai", "accepted"), "Already in your Agent inbox. Claude proposed it first, and it's already queued.");
  assert.equal(q(null, "approved"), "Already in your Agent inbox. A connected agent proposed it first, and it's being applied to.");
  assert.equal(q("you", "accepted"), "Already in your Agent inbox. It's already queued.");
  assert.equal(q(undefined, "needs_human"), "Already in your Agent inbox. It needs you.");
  assert.equal(q("you", "from_a_newer_backend"), "Already in your Agent inbox.");
});

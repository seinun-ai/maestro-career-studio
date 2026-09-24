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
  assert.equal(proposalByLine("claude-ai"), "Proposed by Claude");
  assert.equal(proposalByLine("you"), "Queued by you");
  assert.equal(proposalByLine(null), "Proposed by a connected agent");
  assert.equal(proposalByLine(undefined), "Proposed by a connected agent");
  assert.equal(proposalByLine("クロード"), "Proposed by クロード");
});

test("the tracker mark falls back to the capture", () => {
  assert.equal(agentMarkLabel("codex-mcp-client"), "Proposed by Codex");
  assert.equal(agentMarkLabel("you"), "Found by a connected agent");
  assert.equal(agentMarkLabel(null), "Found by a connected agent");
});

test("a Queue that joined an agent's proposal says whose it stays", () => {
  assert.equal(queuedToast("you"), "Queued in your Agent inbox.");
  assert.equal(queuedToast(undefined), "Queued in your Agent inbox.");
  assert.equal(queuedToast("claude-ai"), "Queued in your Agent inbox. Claude proposed it first.");
  assert.equal(queuedToast(null), "Queued in your Agent inbox. A connected agent proposed it first.");
});

// Run: node --test mcpb/tests/
// Node's built-in runner, so the bundle keeps zero dependencies.
"use strict";

const { test } = require("node:test");
const assert = require("node:assert");
const { execFileSync, spawnSync } = require("node:child_process");
const path = require("node:path");

const SHIM = path.join(__dirname, "..", "server", "index.js");
const INIT = JSON.stringify({
  jsonrpc: "2.0", id: 1, method: "initialize",
  params: { protocolVersion: "2024-11-05", capabilities: {},
            clientInfo: { name: "test", version: "0" } },
}) + "\n";

const hasDocker = (() => {
  try { execFileSync("docker", ["version"], { stdio: "ignore" }); return true; }
  catch { return false; }
})();

test("a missing container is reported as a sentence, not a docker error", (t) => {
  if (!hasDocker) return t.skip("docker not available");
  const r = spawnSync(process.execPath, [SHIM], {
    input: INIT,
    env: { ...process.env, MAESTRO_CS_CONTAINER: "definitely-not-a-container" },
    encoding: "utf8",
  });
  // The raw Docker line still reaches stderr — clients surface it as a log and
  // swallowing it would hide the real cause — but our sentence must follow it,
  // naming the container and what to do.
  assert.match(r.stderr, /\[maestro-career-studio\]/);
  assert.match(r.stderr, /definitely-not-a-container/);
  assert.match(r.stderr, /docker compose up -d/);
  assert.match(r.stderr, /COMPOSE_PROJECT_NAME/);
  assert.notStrictEqual(r.status, 0, "must exit non-zero so the client shows it failed");
});

test("docker resolves even with an empty PATH (how Claude Desktop launches us)", (t) => {
  if (!hasDocker) return t.skip("docker not available");
  // Claude Desktop runs extensions with PATH=/usr/bin:/bin:/usr/sbin:/sbin, and
  // Docker Desktop installs to /usr/local/bin. A bare `docker` therefore fails
  // with ENOENT and no output — the failure that made the first build of this
  // extension disconnect immediately. An empty PATH reproduces it exactly.
  const r = spawnSync(process.execPath, [SHIM], {
    input: INIT,
    env: { PATH: "", HOME: process.env.HOME,
           MAESTRO_CS_CONTAINER: "definitely-not-a-container" },
    encoding: "utf8",
  });
  assert.doesNotMatch(r.stderr, /could not find the `docker` executable/,
    "must locate docker by absolute path, not via PATH");
  // Reaching the container check proves docker itself ran.
  assert.match(r.stderr, /definitely-not-a-container/);
});

test("an explicit docker path is honoured over the search list", () => {
  const r = spawnSync(process.execPath, [SHIM], {
    input: INIT,
    env: { PATH: "", HOME: process.env.HOME,
           MAESTRO_CS_DOCKER: "/nonexistent/docker", MAESTRO_CS_CONTAINER: "x" },
    encoding: "utf8",
  });
  // A deliberate override must not silently fall through to a working docker;
  // the search list is not a safety net for a typo the user can see and fix.
  assert.match(r.stderr, /could not find the `docker` executable|nonexistent\/docker/);
  assert.notStrictEqual(r.status, 0);
});

test("unsaved user_config placeholders are ignored, not obeyed", (t) => {
  if (!hasDocker) return t.skip("docker not available");
  // Claude Desktop passes a field the user never filled in as its LITERAL
  // placeholder, not as an empty string. Believing one is what made this
  // extension exit 39ms after initialize with no visible cause.
  const r = spawnSync(process.execPath, [SHIM], {
    input: INIT,
    env: {
      PATH: "", HOME: process.env.HOME,
      MAESTRO_CS_DOCKER: "${user_config.docker_path}",
      MAESTRO_CS_CONTAINER: "${user_config.container_name}",
      MAESTRO_CS_MCP_PROFILE: "${user_config.profile}",
    },
    encoding: "utf8",
  });
  assert.doesNotMatch(r.stderr, /Docker path" setting points at/,
    "a placeholder is not a user instruction");
  assert.doesNotMatch(r.stderr, /user_config/,
    "no placeholder should reach docker as a real value");
});

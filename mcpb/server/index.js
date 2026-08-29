#!/usr/bin/env node
// Stdio proxy: Claude Desktop <-> the MCP server inside the backend container.
//
// Why a shim rather than `"command": "docker"` straight in the manifest: the
// MCPB spec allows a command that is a binary on PATH, but it also requires
// `entry_point` to reference a file actually inside the bundle. A stub entry
// point that never runs satisfies the letter and not the intent, and a shell
// script would need platform_overrides for the .sh/.cmd split. This file is
// both the entry point and the command, matching the spec's own Node example.
//
// It runs on the Node that ships inside Claude Desktop and has no dependencies,
// so the packed bundle stays small enough to commit alongside the repo.
"use strict";

const { spawn } = require("node:child_process");
const fs = require("node:fs");

// A user_config field the user never filled in arrives as its LITERAL
// placeholder — "${user_config.docker_path}", not an empty string — so every
// value read here must be screened before it is believed. Treating one as real
// input is what made this extension refuse to start: the docker override was
// "not an executable file", and before that the container name was a string no
// container could ever match.
const setting = (name) => {
  const raw = (process.env[name] || "").trim();
  return /^\$\{.*\}$/.test(raw) ? "" : raw;
};

const container = setting("MAESTRO_CS_CONTAINER") || "maestro-career-studio-backend-1";
const profile = setting("MAESTRO_CS_MCP_PROFILE") || "full";

// Write synchronously: a message queued on process.stderr can be lost when the
// process exits in the same tick, and the host only shows us what it received.
const fail = (message) => {
  fs.writeSync(2, `\n[maestro-career-studio] ${message}\n`);
};

// Claude Desktop launches extensions with PATH=/usr/bin:/bin:/usr/sbin:/sbin —
// a GUI app does not inherit your shell PATH — and Docker installs to
// /usr/local/bin. A bare `docker` therefore fails with ENOENT and no output,
// which is exactly why setup-mcp.sh resolves absolute paths for GUI clients.
// Look where Docker Desktop actually puts things, and let user_config override.
const override = setting("MAESTRO_CS_DOCKER");
const dockerCandidates = [
  "/usr/local/bin/docker",
  "/opt/homebrew/bin/docker",
  "/Applications/Docker.app/Contents/Resources/bin/docker",
  `${process.env.HOME || ""}/.docker/bin/docker`,
  "/usr/bin/docker",
].filter(Boolean);

const runnable = (p) => {
  try { fs.accessSync(p, fs.constants.X_OK); return true; } catch { return false; }
};

// An explicit setting is not a hint. If it is wrong, say so rather than quietly
// running a different docker than the one the user asked for.
if (override && !runnable(override)) {
  fail(
    `the "Docker path" setting points at ${override}, which is not an ` +
    "executable file. Correct it, or clear it to search the usual locations."
  );
  process.exit(1);
}

const dockerBin = override || dockerCandidates.find(runnable);

if (!dockerBin) {
  fail(
    "could not find the `docker` executable. Claude Desktop runs extensions " +
    "with a minimal PATH, so Docker must be located by absolute path. Looked " +
    `in: ${dockerCandidates.join(", ")}. Set this extension's "Docker path" ` +
    "setting to what `which docker` prints in a terminal."
  );
  process.exit(1);
}

// BACKEND_URL is the CONTAINER-internal address: the app listens on 8000 inside
// the container regardless of which host port compose published. That is why
// this transport cannot get the 8000-vs-8001 confusion wrong.
const args = [
  "exec", "-i",
  "-e", "BACKEND_URL=http://localhost:8000",
  "-e", `MAESTRO_CS_MCP_PROFILE=${profile}`,
  container,
  "python", "-m", "mcp_server.server",
];

// Pipe explicitly rather than inheriting fds. Claude Desktop runs extensions in
// Electron's Node, where the parent's stdin/stdout are not guaranteed to be
// ordinary inheritable descriptors — `stdio: "inherit"` connected the container
// to nothing and the transport closed the moment the server tried to answer.
// Explicit streams work the same in both runtimes.
const child = spawn(dockerBin, args, { stdio: ["pipe", "pipe", "pipe"] });

process.stdin.pipe(child.stdin);
child.stdout.pipe(process.stdout);

// The client going away closes our stdin, which closes the container's; neither
// side should die with an unhandled EPIPE on the way out.
const ignoreEpipe = (stream) => {
  stream.on("error", (err) => { if (err && err.code !== "EPIPE") throw err; });
};
ignoreEpipe(process.stdin);
ignoreEpipe(process.stdout);
ignoreEpipe(child.stdin);

// Forward the server's stderr (clients surface it as logs) while keeping a copy,
// so a startup failure can be reported as a sentence instead of a Docker error.
let stderr = "";
child.stderr.on("data", (chunk) => {
  stderr += chunk.toString();
  process.stderr.write(chunk);
});

child.on("error", (err) => {
  if (err.code === "ENOENT") {
    fail(`could not run ${dockerBin}. Is Docker Desktop installed and running?`);
  } else {
    fail(`could not start docker: ${err.message}`);
  }
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (code !== 0 && /No such container|is not running/i.test(stderr)) {
    fail(
      `the container "${container}" is not running. Start the app with ` +
      "`docker compose up -d` from your Maestro CS checkout. If your stack " +
      "uses a different COMPOSE_PROJECT_NAME, set this extension's " +
      "\"Container name\" setting to what `docker ps` reports."
    );
  }
  process.exit(signal ? 1 : code === null ? 1 : code);
});

// A client that goes away should not leave a docker exec behind.
for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => { child.kill(sig); });
}

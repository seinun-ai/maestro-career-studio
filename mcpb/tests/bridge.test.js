// Run: node --test mcpb/tests/*.test.js
"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const { spawn, spawnSync } = require("node:child_process");
const { once } = require("node:events");
const path = require("node:path");

const BRIDGE = path.join(__dirname, "..", "server", "index.js");
const INITIALIZE = {
  jsonrpc: "2.0", id: 1, method: "initialize",
  params: {
    protocolVersion: "2025-03-26", capabilities: {},
    clientInfo: { name: "bridge-test-client", version: "1" },
  },
};
const INITIALIZED = { jsonrpc: "2.0", method: "notifications/initialized" };
const LIST = { jsonrpc: "2.0", id: 2, method: "tools/list" };

async function fakeServer(t, respond) {
  const requests = [];
  const server = http.createServer(async (req, res) => {
    let line = "";
    for await (const chunk of req) line += chunk;
    const request = {
      method: req.method, url: req.url, headers: req.headers,
      line, body: JSON.parse(line),
    };
    requests.push(request);
    await respond(request, res, requests);
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  t.after(() => new Promise((resolve) => {
    server.close(resolve);
    server.closeAllConnections();
  }));
  return { url: `http://127.0.0.1:${server.address().port}`, requests };
}

function json(res, body, headers = {}) {
  res.writeHead(200, { "Content-Type": "application/json", ...headers });
  res.end(JSON.stringify(body));
}

function startBridge(t, url, env = {}) {
  const child = spawn(process.execPath, [BRIDGE], {
    env: {
      PATH: "", MAESTRO_CS_BACKEND_URL: url, MAESTRO_CS_MCP_PROFILE: "full",
      ...env,
    },
    stdio: ["pipe", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.setEncoding("utf8").on("data", (chunk) => { stdout += chunk; });
  child.stderr.setEncoding("utf8").on("data", (chunk) => { stderr += chunk; });
  child.stdin.on("error", (error) => {
    if (error.code !== "EPIPE") throw error;
  });
  const timeout = setTimeout(() => child.kill("SIGKILL"), 5000);
  t.after(() => { clearTimeout(timeout); child.kill("SIGKILL"); });
  const done = once(child, "close").then(([code, signal]) => {
    clearTimeout(timeout);
    return { code, signal, stdout, stderr };
  });
  return { child, done };
}

async function runBridgeLines(t, url, lines, env) {
  const { child, done } = startBridge(t, url, env);
  child.stdin.end(lines.map((line) => line + "\n").join(""));
  const result = await done;
  assert.equal(result.code, 0, result.stderr);
  assert.equal(result.signal, null);
  return result;
}

async function runBridge(t, url, messages, env) {
  return runBridgeLines(t, url, messages.map((message) => JSON.stringify(message)), env);
}

function stdoutMessages(result) {
  if (!result.stdout) return [];
  assert.ok(result.stdout.endsWith("\n"), "each JSON-RPC output ends in a newline");
  return result.stdout.trimEnd().split("\n").map((line) => JSON.parse(line));
}

test("initialize adopts the session id and forwards the client's exact request", async (t) => {
  const server = await fakeServer(t, ({ body }, res) => {
    if (body.method === "initialize") {
      json(res, { jsonrpc: "2.0", id: 1, result: {} }, { "mcp-session-id": "session-1" });
    } else {
      json(res, { jsonrpc: "2.0", id: 2, result: { tools: [] } });
    }
  });
  const result = await runBridge(t, server.url, [INITIALIZE, LIST]);
  assert.deepEqual(stdoutMessages(result), [
    { jsonrpc: "2.0", id: 1, result: {} },
    { jsonrpc: "2.0", id: 2, result: { tools: [] } },
  ]);
  assert.equal(result.stderr, "");
  assert.equal(server.requests[0].line, JSON.stringify(INITIALIZE));
  assert.equal(server.requests[0].headers["mcp-session-id"], undefined);
  assert.equal(server.requests[1].headers["mcp-session-id"], "session-1");
  for (const request of server.requests) {
    assert.equal(request.method, "POST");
    assert.equal(request.url, "/mcp");
    assert.equal(request.headers.accept, "application/json, text/event-stream");
    assert.equal(request.headers["content-type"], "application/json");
  }
});

test("a notification accepted with 202 writes nothing to stdout", async (t) => {
  const server = await fakeServer(t, (_req, res) => {
    res.writeHead(202);
    res.end();
  });
  const result = await runBridge(t, server.url, [INITIALIZED]);
  assert.equal(result.stdout, "");
  assert.equal(result.stderr, "");
  assert.equal(server.requests.length, 1);
});

test("a backend restart replays initialize and initialized before retrying once", async (t) => {
  let session = "session-1";
  let initialized = false;
  const server = await fakeServer(t, ({ body, headers }, res) => {
    if (body.method === "initialize") {
      json(res, { jsonrpc: "2.0", id: 1, result: {} }, { "mcp-session-id": session });
    } else if (headers["mcp-session-id"] !== session) {
      res.writeHead(404);
      res.end("Session not found");
    } else if (body.method === "notifications/initialized") {
      initialized = true;
      res.writeHead(202);
      res.end();
    } else if (body.id === "before-restart") {
      json(res, { jsonrpc: "2.0", id: body.id, result: {} });
      session = "session-2";
      initialized = false;
    } else if (initialized) {
      json(res, { jsonrpc: "2.0", id: 2, result: { tools: [] } });
    } else {
      res.writeHead(400);
      res.end("Not initialized");
    }
  });
  const result = await runBridge(t, server.url, [
    INITIALIZE, INITIALIZED, { ...LIST, id: "before-restart" }, LIST,
  ]);
  assert.deepEqual(stdoutMessages(result), [
    { jsonrpc: "2.0", id: 1, result: {} },
    { jsonrpc: "2.0", id: "before-restart", result: {} },
    { jsonrpc: "2.0", id: 2, result: { tools: [] } },
  ]);
  assert.deepEqual(server.requests.map(({ body }) => body.method), [
    "initialize", "notifications/initialized", "tools/list", "tools/list",
    "initialize", "notifications/initialized", "tools/list",
  ]);
  assert.equal(server.requests[4].headers["mcp-session-id"], undefined);
  assert.equal(server.requests[4].line, JSON.stringify(INITIALIZE));
  assert.equal(server.requests[5].line, JSON.stringify(INITIALIZED));
  assert.equal(server.requests[5].headers["mcp-session-id"], "session-2");
  assert.equal(server.requests[6].headers["mcp-session-id"], "session-2");
});

test("connection refusal prints the start sentence and preserves the request id", async (t) => {
  const url = "http://127.0.0.1:1";
  const result = await runBridge(t, url, [{ ...LIST, id: "refused" }]);
  const message = `Maestro Career Studio is not running at ${url}. Start it (docker compose up -d, or open the app) and try again.`;
  assert.equal(result.stderr, message + "\n");
  assert.deepEqual(stdoutMessages(result), [
    { jsonrpc: "2.0", id: "refused", error: { code: -32000, message } },
  ]);
});

test("connection refusal for a notification produces only stderr", async (t) => {
  const result = await runBridge(t, "http://127.0.0.1:1", [INITIALIZED]);
  assert.equal(result.stdout, "");
  assert.match(result.stderr, /^Maestro Career Studio is not running at /);
});

const TIMEOUT_MESSAGE = "Maestro Career Studio did not answer within 10 minutes. The request may still finish in the app.";

test("an unanswered request times out without saying the app is stopped or retrying", async (t) => {
  const server = await fakeServer(t, () => {});
  const result = await runBridge(t, server.url, [LIST], { MAESTRO_CS_BRIDGE_TIMEOUT_MS: "50" });
  assert.deepEqual(stdoutMessages(result), [
    { jsonrpc: "2.0", id: 2, error: { code: -32000, message: TIMEOUT_MESSAGE } },
  ]);
  assert.equal(result.stderr, TIMEOUT_MESSAGE + "\n");
  assert.equal(server.requests.length, 1, "a timeout never retries work that may still finish");
});

test("the overall deadline includes a response body that keeps sending data", async (t) => {
  const server = await fakeServer(t, (_req, res) => {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.write(" ");
    const interval = setInterval(() => res.write(" "), 10);
    res.on("close", () => clearInterval(interval));
    t.after(() => clearInterval(interval));
  });
  const result = await runBridge(t, server.url, [LIST], { MAESTRO_CS_BRIDGE_TIMEOUT_MS: "80" });
  assert.equal(stdoutMessages(result)[0].error.message, TIMEOUT_MESSAGE);
  assert.equal(result.stderr, TIMEOUT_MESSAGE + "\n");
  assert.equal(server.requests.length, 1);
});

test("a dropped connection does not claim that Maestro is not running", async (t) => {
  const server = await fakeServer(t, (_req, res) => res.destroy());
  const result = await runBridge(t, server.url, [LIST]);
  const [message] = stdoutMessages(result);
  assert.equal(message.id, 2);
  assert.equal(message.error.code, -32000);
  assert.doesNotMatch(message.error.message, /not running/);
  assert.match(message.error.message, /request may still finish/);
  assert.equal(result.stderr, message.error.message + "\n");
  assert.equal(server.requests.length, 1);
});

test("an invalid backend URL keeps the connection-failure sentence", async (t) => {
  for (const url of ["not a URL", "ftp://localhost:8001"]) {
    const result = await runBridge(t, url, [LIST]);
    const message = `Maestro Career Studio is not running at ${url}. Start it (docker compose up -d, or open the app) and try again.`;
    assert.deepEqual(stdoutMessages(result), [
      { jsonrpc: "2.0", id: 2, error: { code: -32000, message } },
    ]);
    assert.equal(result.stderr, message + "\n");
  }
});

test("JSON null and primitive lines are ignored with one sentence each, then processing continues", async (t) => {
  const result = await runBridge(t, "not a URL", [null, true, false, 42, "text", LIST]);
  const messages = stdoutMessages(result);
  assert.equal(messages.length, 1);
  assert.equal(messages[0].id, 2);
  assert.equal(messages[0].error.code, -32000);
  const stderr = result.stderr.trimEnd().split("\n");
  assert.equal(stderr.length, 6);
  for (const sentence of stderr.slice(0, 5)) {
    assert.equal(sentence, "The MCP message must be a JSON object or array.");
  }
});

test("failed HTTP posts of client responses never echo an error with the response id", async (t) => {
  const server = await fakeServer(t, (_req, res) => {
    res.writeHead(500);
    res.end("Backend error");
  });
  const responses = [
    { jsonrpc: "2.0", id: "client-result", result: {} },
    { jsonrpc: "2.0", id: "client-error", error: { code: -32601, message: "Unknown method" } },
  ];
  const result = await runBridge(t, server.url, responses);
  assert.equal(result.stdout, "");
  assert.deepEqual(server.requests.map(({ body }) => body), responses);
});

test("connection failures answer only requests with a method and id, including batches", async (t) => {
  const responses = [
    { jsonrpc: "2.0", id: "client-result", result: {} },
    { jsonrpc: "2.0", id: "client-error", error: { code: -32601, message: "Unknown method" } },
  ];
  const result = await runBridge(t, "not a URL", [
    ...responses, [...responses, INITIALIZED, null, { ...LIST, id: 0 }],
  ]);
  const messages = stdoutMessages(result);
  assert.equal(messages.length, 1);
  assert.ok(Array.isArray(messages[0]));
  assert.equal(messages[0].length, 1);
  assert.equal(messages[0][0].id, 0);
  assert.equal(messages[0][0].error.code, -32000);
});

test("unparseable input returns Parse error with id null and continues to the next line", async (t) => {
  const result = await runBridgeLines(t, "not a URL", ["{", JSON.stringify(LIST)]);
  const messages = stdoutMessages(result);
  assert.deepEqual(messages[0], {
    jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" },
  });
  assert.equal(messages.length, 2);
  assert.equal(messages[1].id, 2);
});

test("hunt selects /mcp/hunt and an unexpanded profile selects /mcp", async (t) => {
  const server = await fakeServer(t, (_req, res) => {
    json(res, { jsonrpc: "2.0", id: 2, result: {} });
  });
  for (const profile of ["hunt", "${user_config.profile}"]) {
    await runBridge(t, server.url + "/", [LIST], { MAESTRO_CS_MCP_PROFILE: profile });
  }
  assert.deepEqual(server.requests.map(({ url }) => url), ["/mcp/hunt", "/mcp"]);
});

test("backend and profile placeholders use the default Maestro URL", () => {
  const result = spawnSync(process.execPath, ["-e", `
    const { mcpUrl } = require(${JSON.stringify(BRIDGE)});
    process.stdout.write(mcpUrl());
  `], {
    env: {
      MAESTRO_CS_BACKEND_URL: "${user_config.backend_url}",
      MAESTRO_CS_MCP_PROFILE: "${user_config.profile}",
    }, encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout, "http://localhost:8001/mcp");
});

test("HTTP failures and non-JSON bodies emit JSON-RPC errors, never raw text", async (t) => {
  const server = await fakeServer(t, ({ body }, res) => {
    res.writeHead(body.id === "non-json" ? 200 : 500);
    res.end("<html>Backend error\nwith a second line</html>");
  });
  const result = await runBridge(t, server.url, [
    { ...LIST, id: 0 }, { ...LIST, id: "non-json" }, INITIALIZED,
  ]);
  const messages = stdoutMessages(result);
  assert.equal(messages.length, 2, "a failed notification has no JSON-RPC response");
  assert.deepEqual(messages.map(({ id }) => id), [0, "non-json"]);
  for (const message of messages) {
    assert.equal(message.jsonrpc, "2.0");
    assert.equal(message.error.code, -32000);
    assert.match(message.error.message, /^[^\n]+\.$/);
    assert.doesNotMatch(message.error.message, /<html>|second line/);
  }
});

test("404 without a session returns an error without replaying", async (t) => {
  const server = await fakeServer(t, (_req, res) => {
    res.writeHead(404);
    res.end();
  });
  const result = await runBridge(t, server.url, [LIST]);
  assert.equal(stdoutMessages(result)[0].error.code, -32000);
  assert.equal(server.requests.length, 1);
});

test("404 on the retry returns an error and never loops", async (t) => {
  let initializes = 0;
  const server = await fakeServer(t, ({ body }, res) => {
    if (body.method === "initialize") {
      initializes += 1;
      json(res, { jsonrpc: "2.0", id: 1, result: {} }, {
        "mcp-session-id": `session-${initializes}`,
      });
    } else {
      res.writeHead(body.method === "notifications/initialized" ? 202 : 404);
      res.end();
    }
  });
  const result = await runBridge(t, server.url, [INITIALIZE, INITIALIZED, LIST]);
  const messages = stdoutMessages(result);
  assert.equal(messages.length, 2);
  assert.equal(messages[1].id, 2);
  assert.equal(messages[1].error.code, -32000);
  assert.equal(initializes, 2);
  assert.equal(server.requests.length, 6);
});

test("requests wait for preceding responses and batch JSON passes through as an array", async (t) => {
  let previousFinished = true;
  let overlapped = false;
  const server = await fakeServer(t, async ({ body }, res) => {
    if (!previousFinished) overlapped = true;
    previousFinished = false;
    await new Promise((resolve) => setTimeout(resolve, 30));
    json(res, Array.isArray(body)
      ? [{ jsonrpc: "2.0", id: "batch", result: {} }]
      : { jsonrpc: "2.0", id: body.id, result: {} });
    previousFinished = true;
  });
  const result = await runBridge(t, server.url, [LIST, [{ ...LIST, id: "batch" }]]);
  assert.equal(overlapped, false);
  assert.deepEqual(stdoutMessages(result), [
    { jsonrpc: "2.0", id: 2, result: {} },
    [{ jsonrpc: "2.0", id: "batch", result: {} }],
  ]);
});

// 2026-07-28 clients send no initialize: each message names its revision in params._meta.
const MODERN_VERSION = "2026-07-28";
const ENVELOPE = {
  "io.modelcontextprotocol/protocolVersion": MODERN_VERSION,
  "io.modelcontextprotocol/clientInfo": { name: "bridge-test-client", version: "1" },
  "io.modelcontextprotocol/clientCapabilities": {},
};
const modern = (message) => ({ ...message, params: { ...message.params, _meta: ENVELOPE } });
const ROUTING_HEADERS = ["mcp-protocol-version", "mcp-method", "mcp-name"];
const routingHeaders = ({ headers }) => Object.fromEntries(
  ROUTING_HEADERS.filter((name) => Object.hasOwn(headers, name)).map((name) => [name, headers[name]]),
);
const answerById = ({ body }, res) => {
  if (Object.hasOwn(body, "id")) json(res, { jsonrpc: "2.0", id: body.id, result: {} });
  else { res.writeHead(202); res.end(); }
};

test("a 2026-07-28 request carries its version, method and name as headers", async (t) => {
  const server = await fakeServer(t, answerById);
  const messages = [
    modern({ jsonrpc: "2.0", id: "discover", method: "server/discover" }),
    modern({ ...LIST, id: "list" }),
    modern({ jsonrpc: "2.0", id: "call", method: "tools/call", params: { name: "list_jobs", arguments: { limit: 5 } } }),
    modern({ jsonrpc: "2.0", id: "prompt", method: "prompts/get", params: { name: "start_here" } }),
    modern({ jsonrpc: "2.0", id: "read", method: "resources/read", params: { uri: "notes://setup" } }),
  ];
  const result = await runBridge(t, server.url, messages);
  assert.deepEqual(stdoutMessages(result), messages.map(({ id }) => ({ jsonrpc: "2.0", id, result: {} })));
  assert.equal(result.stderr, "");
  const version = { "mcp-protocol-version": MODERN_VERSION };
  assert.deepEqual(server.requests.map(routingHeaders), [
    { ...version, "mcp-method": "server/discover" },
    { ...version, "mcp-method": "tools/list" },
    { ...version, "mcp-method": "tools/call", "mcp-name": "list_jobs" },
    { ...version, "mcp-method": "prompts/get", "mcp-name": "start_here" },
    { ...version, "mcp-method": "resources/read", "mcp-name": "notes://setup" },
  ]);
  for (const [index, request] of server.requests.entries()) {
    assert.equal(request.line, JSON.stringify(messages[index]), "the body is forwarded untouched");
    assert.equal(request.headers["mcp-session-id"], undefined);
    assert.equal(request.headers.accept, "application/json, text/event-stream");
  }
});

test("a name outside plain printable ASCII travels in the SDK's base64 form", async (t) => {
  const server = await fakeServer(t, answerById);
  // Expected values are the SDK's own encode_header_value output for each name.
  const names = [
    ["notes://café/résumé ✓", "=?base64?bm90ZXM6Ly9jYWbDqS9yw6lzdW3DqSDinJM=?="],
    [" padded ", "=?base64?IHBhZGRlZCA=?="],
    ["tab\there", "=?base64?dGFiCWhlcmU=?="],
    ["=?base64?bGlzdA==?=", "=?base64?PT9iYXNlNjQ/YkdsemRBPT0/PQ==?="],
  ];
  await runBridge(t, server.url, names.map(([uri], id) => modern({
    jsonrpc: "2.0", id, method: "resources/read", params: { uri },
  })));
  assert.deepEqual(server.requests.map(({ headers }) => headers["mcp-name"]), names.map(([, header]) => header));
});

test("2025 traffic carries none of the routing headers and keeps its session", async (t) => {
  const server = await fakeServer(t, (request, res) => {
    if (request.body.method === "initialize") {
      json(res, { jsonrpc: "2.0", id: 1, result: {} }, { "mcp-session-id": "session-1" });
    } else {
      answerById(request, res);
    }
  });
  await runBridge(t, server.url, [
    INITIALIZE, INITIALIZED, LIST,
    { jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "list_jobs", arguments: {} } },
    { ...LIST, id: 4, params: { _meta: { progressToken: "progress-1" } } },
  ]);
  assert.deepEqual(server.requests.map(routingHeaders), [{}, {}, {}, {}, {}]);
  assert.deepEqual(server.requests.map(({ headers }) => headers["mcp-session-id"]), [
    undefined, "session-1", "session-1", "session-1", "session-1",
  ]);
});

test("a 2026-07-28 request neither sends, adopts nor clears the 2025 session", async (t) => {
  const server = await fakeServer(t, (request, res) => {
    if (request.body.method === "initialize") {
      json(res, { jsonrpc: "2.0", id: 1, result: {} }, { "mcp-session-id": "session-1" });
    } else {
      answerById(request, res);
    }
  });
  await runBridge(t, server.url, [INITIALIZE, modern({ ...LIST, id: "modern" }), LIST]);
  assert.deepEqual(server.requests.map(({ headers }) => headers["mcp-session-id"]), [
    undefined, undefined, "session-1",
  ]);
  assert.deepEqual(server.requests.map(({ headers }) => headers["mcp-protocol-version"]), [
    undefined, MODERN_VERSION, undefined,
  ]);
});

test("a 404 to a 2026-07-28 request is not a lost session, so nothing is replayed", async (t) => {
  const server = await fakeServer(t, ({ body }, res) => {
    if (body.method === "initialize") {
      json(res, { jsonrpc: "2.0", id: 1, result: {} }, { "mcp-session-id": "session-1" });
    } else if (body.method === "notifications/initialized") {
      res.writeHead(202);
      res.end();
    } else {
      res.writeHead(404, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ jsonrpc: "2.0", id: body.id, error: { code: -32601, message: "Method not found" } }));
    }
  });
  const result = await runBridge(t, server.url, [
    INITIALIZE, INITIALIZED, modern({ jsonrpc: "2.0", id: "listen", method: "subscriptions/listen" }),
  ]);
  assert.deepEqual(server.requests.map(({ body }) => body.method), [
    "initialize", "notifications/initialized", "subscriptions/listen",
  ]);
  const messages = stdoutMessages(result);
  assert.equal(messages.length, 2);
  assert.equal(messages[1].id, "listen");
  assert.ok(messages[1].error);
});

test("a 2026-07-28 notification carries its version and method; responses and batches go as before", async (t) => {
  const server = await fakeServer(t, (_req, res) => {
    res.writeHead(202);
    res.end();
  });
  const notification = modern({ jsonrpc: "2.0", method: "notifications/cancelled", params: { requestId: "call" } });
  const result = await runBridge(t, server.url, [
    notification,
    { jsonrpc: "2.0", id: "server-request", result: { _meta: ENVELOPE } },
    [modern({ ...LIST, id: "batch" })],
  ]);
  assert.equal(result.stdout, "");
  assert.deepEqual(server.requests.map(routingHeaders), [
    { "mcp-protocol-version": MODERN_VERSION, "mcp-method": "notifications/cancelled" },
    {},
    {},
  ]);
});

test("empty stdin exits successfully", async (t) => {
  const result = await runBridge(t, "http://127.0.0.1:1", []);
  assert.equal(result.stdout, "");
  assert.equal(result.stderr, "");
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  test(`${signal} exits successfully while stdin remains open`, {
    skip: process.platform === "win32" && "child.kill does not deliver POSIX signals on Windows",
  }, async (t) => {
    const { child, done } = startBridge(t, "http://127.0.0.1:1");
    const output = once(child.stdout, "data");
    child.stdin.write(JSON.stringify(LIST) + "\n");
    await Promise.race([output, done]);
    child.kill(signal);
    const result = await done;
    assert.equal(result.code, 0, result.stderr);
    assert.equal(result.signal, null);
    assert.equal(stdoutMessages(result).length, 1);
  });
}

test("requiring the bridge does not start transport or write output", () => {
  const result = spawnSync(process.execPath, ["-e", `require(${JSON.stringify(BRIDGE)})`], {
    env: { PATH: "" }, encoding: "utf8",
  });
  assert.equal(result.status, 0);
  assert.equal(result.stdout, "");
  assert.equal(result.stderr, "");
});

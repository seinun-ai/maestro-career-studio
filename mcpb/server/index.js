#!/usr/bin/env node
// Claude Desktop stdio ↔ Maestro's HTTP MCP endpoint. Node ≥ 18; no dependencies.
"use strict";

const readline = require("node:readline");
const http = require("node:http");
const https = require("node:https");

const DEFAULT_TIMEOUT_MS = 10 * 60 * 1000;
const TIMEOUT_MESSAGE = "Maestro Career Studio did not answer within 10 minutes. The request may still finish in the app.";

function postBody(url, headers, line, timeoutMs) {
  return new Promise((resolve, reject) => {
    let timer;
    const finish = (error, response) => {
      clearTimeout(timer);
      if (error) reject(error);
      else resolve(response);
    };
    try {
      const target = new URL(url);
      const transport = target.protocol === "http:" ? http : target.protocol === "https:" ? https : null;
      if (!transport) throw Object.assign(new Error("Invalid MCP URL"), { code: "ERR_INVALID_URL" });
      const request = transport.request(target, { method: "POST", headers }, (response) => {
        let text = "";
        response.setEncoding("utf8");
        response.on("data", (chunk) => { text += chunk; });
        response.on("error", finish);
        response.on("aborted", () => finish(Object.assign(new Error("Response interrupted"), { code: "ECONNRESET" })));
        response.on("end", () => finish(null, {
          status: response.statusCode, sessionId: response.headers["mcp-session-id"], text,
        }));
      });
      request.on("error", finish);
      // One deadline covers DNS, connection, headers and the complete body.
      timer = setTimeout(() => {
        const error = Object.assign(new Error(TIMEOUT_MESSAGE), { code: "MAESTRO_CS_BRIDGE_TIMEOUT" });
        finish(error);
        request.destroy(error);
      }, timeoutMs);
      request.end(line);
    } catch (error) {
      finish(error);
    }
  });
}

// A 2026-07-28 message has no initialize or session: it names its revision in params._meta, and the
// SDK routes on MCP-Protocol-Version, then checks Mcp-Method and Mcp-Name against the body.
const PROTOCOL_VERSION_KEY = "io.modelcontextprotocol/protocolVersion";
const NAME_PARAMS = new Map([["tools/call", "name"], ["prompts/get", "name"], ["resources/read", "uri"]]);

// The SDK's header codec (encode_header_value): printable ASCII without edge spaces goes as is,
// anything else as =?base64?<UTF-8>?=, so no value is one Node refuses or the server misreads.
const headerValue = (value) => (
  /^[\x20-\x7E]*$/.test(value) && value === value.trim() && !/^=\?base64\?.*\?=$/.test(value)
    ? value : `=?base64?${Buffer.from(value, "utf8").toString("base64")}?=`
);

function routingHeaders(message) {
  const params = Array.isArray(message) ? undefined : message.params;
  const meta = params && typeof params === "object" ? params._meta : undefined;
  const version = meta && typeof meta === "object" ? meta[PROTOCOL_VERSION_KEY] : undefined;
  if (typeof version !== "string") return undefined;
  const headers = { "MCP-Protocol-Version": headerValue(version) };
  if (typeof message.method === "string") headers["Mcp-Method"] = headerValue(message.method);
  const nameKey = NAME_PARAMS.get(message.method);
  if (nameKey && typeof params[nameKey] === "string") headers["Mcp-Name"] = headerValue(params[nameKey]);
  return headers;
}

// Unfilled user_config values can arrive as literal placeholders.
const setting = (name) => {
  const raw = (process.env[name] || "").trim();
  return /^\$\{.*\}$/.test(raw) ? "" : raw;
};

const mcpUrl = (
  backendUrl = setting("MAESTRO_CS_BACKEND_URL") || "http://localhost:8001",
  profile = setting("MAESTRO_CS_MCP_PROFILE") || "full",
) => `${backendUrl.replace(/\/+$/, "")}/mcp${profile === "full" ? "" : `/${profile}`}`;

async function main() {
  const backendUrl = setting("MAESTRO_CS_BACKEND_URL") || "http://localhost:8001";
  const url = mcpUrl(backendUrl);
  const configuredTimeout = Number(setting("MAESTRO_CS_BRIDGE_TIMEOUT_MS"));
  const timeoutMs = Number.isFinite(configuredTimeout) && configuredTimeout > 0
    ? configuredTimeout : DEFAULT_TIMEOUT_MS;
  let sessionId;
  let initializeLine;
  let initializedLine;

  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.on(signal, () => process.exit(0));
  }

  const write = (body) => process.stdout.write(JSON.stringify(body) + "\n");
  const fail = (request, message) => {
    const requests = Array.isArray(request) ? request : [request];
    const errors = requests.filter((item) => item && Object.hasOwn(item, "method") && Object.hasOwn(item, "id"))
      .map(({ id }) => ({ jsonrpc: "2.0", id, error: { code: -32000, message } }));
    if (errors.length) write(Array.isArray(request) ? errors : errors[0]);
  };

  async function post(line, routing) {
    const headers = {
      Accept: "application/json, text/event-stream",
      "Content-Type": "application/json",
      ...routing,
    };
    if (sessionId && !routing) headers["Mcp-Session-Id"] = sessionId;
    let response;
    try {
      response = await postBody(url, headers, line, timeoutMs);
    } catch (error) {
      const connectionFailure = ["ECONNREFUSED", "ENOTFOUND", "EHOSTUNREACH", "ERR_INVALID_URL", "ERR_INVALID_PROTOCOL"].includes(error.code);
      const message = error.code === "MAESTRO_CS_BRIDGE_TIMEOUT" ? TIMEOUT_MESSAGE : connectionFailure
        ? `Maestro Career Studio is not running at ${backendUrl}. Start it (docker compose up -d, or open the app) and try again.`
        : "Maestro Career Studio could not complete the request. The request may still finish in the app.";
      process.stderr.write(message + "\n");
      throw new Error(message);
    }
    let body;
    if (response.status === 200) {
      try { body = JSON.parse(response.text); }
      catch { throw new Error("Maestro Career Studio returned an invalid JSON response."); }
    }
    return { status: response.status, sessionId: response.sessionId, body };
  }

  function accepted(response) {
    if (response.status !== 200 && response.status !== 202) {
      throw new Error(`Maestro Career Studio returned HTTP ${response.status}.`);
    }
    return response;
  }

  const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity, terminal: false });
  // Await each complete response, including a session replay, before reading on.
  for await (const line of lines) {
    if (!line.trim()) continue;
    let request;
    try { request = JSON.parse(line); }
    catch {
      write({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } });
      continue;
    }
    if (request === null || typeof request !== "object") {
      process.stderr.write("The MCP message must be a JSON object or array.\n");
      continue;
    }
    const routing = routingHeaders(request);
    if (routing) {
      // No session to send, adopt or replay: a 404 here is the server's answer, not a lost session.
      try {
        const response = accepted(await post(line, routing));
        if (response.status === 200) write(response.body);
      } catch (error) {
        fail(request, error.message);
      }
      continue;
    }
    if (request.method === "initialize") initializeLine = line;
    if (request.method === "notifications/initialized") initializedLine = line;
    try {
      let response = await post(line);
      if (response.status === 404 && sessionId && initializeLine) {
        // A restarted backend must see a fresh handshake without the stale id.
        sessionId = undefined;
        const initialized = accepted(await post(initializeLine));
        sessionId = initialized.sessionId;
        if (initializedLine) accepted(await post(initializedLine));
        response = await post(line);
      }
      accepted(response);
      if (request.method === "initialize") sessionId = response.sessionId;
      if (response.status === 200) write(response.body);
    } catch (error) {
      fail(request, error.message);
    }
  }
}

module.exports = { mcpUrl, setting, main };
if (require.main === module) main();

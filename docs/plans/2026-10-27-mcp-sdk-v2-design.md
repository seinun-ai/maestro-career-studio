# Moving the MCP server to SDK 2.x (audit Phase 4): design

Date: 2026-10-27. Owner-approved in conversation. Follows Phase 3c (coverage holes, 94 tools; on main 1e15d155). Moves `mcp_server` from `mcp` 1.30 to 2.3 and the 2026-07-28 protocol revision, behaviour unchanged.

## Goal

Agents see exactly what they see today: the same tools per set, the same schemas, the same answers, the same refusal texts. Clients speaking the 2026-07-28 revision (no handshake, no sessions) are served too, alongside 2025-era clients.

## Owner calls

- **Upgrade only.** No "input required" questions, no real cache lifetimes, no `subscriptions/listen`. Asking the user mid-tool would put Maestro into the conversation the agent owns.
- **A real SDK server per set** (approach B), not a port of today's hand-written per-set handlers (A), and not one server filtering per request (C: sets have their own instructions, and the revision says lists must not vary per connection).
- **Genuine crashes read "Error executing tool X"**, the 2.x default; the server log keeps the traceback. Deliberate refusals read word for word, as today.

## Facts this rests on (checked in the 2.3.0 source, 2026-10-27)

- `mcp.server.fastmcp` is gone; `FastMCP` is `mcp.server.mcpserver.MCPServer`, `Context` and `ToolError` live under it.
- `MCPServer(tools=[...])` takes `Tool` objects; `remove_tool` is public; `list_tools`/`call_tool`/`list_prompts`/`get_prompt` are documented override points.
- `MCPServer._handle_call_tool` turns a `ToolError` into an `is_error` result carrying its text. `Tool.run` wraps any other exception as `UnexpectedToolError("Error executing tool <name>")` with the message dropped. Our `BackendError` is a plain `Exception`, so without a translation every backend refusal would lose its reason.
- Sync tools run through `anyio.to_thread.run_sync` on anyio's default limiter (shared with FastAPI's sync endpoints). `Tool.fn`/`Tool.is_async` still exist, so our wrapper still works.
- `StreamableHTTPSessionManager` serves both eras from one endpoint: a request whose `mcp-protocol-version` header names a non-handshake version goes to the modern path; anything else takes the 2025 path (stateful here). It still takes `security_settings`, `session_idle_timeout`, `max_request_body_size` (default now 4 MiB) and adds `max_sessions`. A manager runs once; `MCPServer.session_manager` exists "for mounting multiple MCPServer instances in a single FastAPI application".
- The modern path requires `Mcp-Method` and `Mcp-Name` headers that match the body.
- For a modern request the SDK synthesizes `session.client_params` from `_meta` (`io.modelcontextprotocol/clientInfo` plus capabilities), so `_client_label` keeps working when the client names itself.
- Each server appends an `OpenTelemetryMiddleware` (span per message: method, tool name, error text on a crash). `MCPServer.middleware` is the public list.
- The 1.x line is still maintained (1.30.0 on 2026-09-07, the day 2.2.0 shipped), so this is not urgent; it is housekeeping before clients start requiring 2026-07-28.

## 1. A server per set

- `server.mcp` stays the one registry; every `@mcp.tool` registration is unchanged apart from imports.
- A builder makes one `_ServedMCP` per set in `PROFILE_ALLOWLISTS` (full included) from the registry's `Tool` objects in that set, with `orientation.instructions_for(set)`, the app version, and the set name.
- `_ServedMCP.call_tool` (per set): a removed tool's name answers with `replaced.replaced_message(name, served=<this set>)`; a removed argument answers with `replaced.refused_argument`; `CURRENT_PROFILE` is set for the call; refusal texts are translated (section 2).
- `_ServedMCP.list_prompts`/`get_prompt` serve the playbook cards for the set (full: all), read off the event loop as today.
- HTTP: `McpEndpoint` builds the sets once and, on each lifespan run, a fresh session manager per set with today's settings: JSON responses, stateful 2025 path, 6-hour idle timeout, 16 MiB bodies, SDK DNS-rebinding protection off (the app's Host → Origin → CORS middleware is the one definition). Routing, the `career`/`explore` aliases and the 404 for an unknown set are unchanged. The hand-written list/call/prompt handlers go.
- stdio: `main()` runs the set object for `MAESTRO_CS_MCP_PROFILE`. `apply_profile_filter`'s mutation of the global registry goes.
- Threads: HTTP sets keep the dedicated 8-thread limiter (a tool waiting on loopback REST must never starve the endpoint it waits on).
- Tracing: the SDK's `OpenTelemetryMiddleware` is removed from each set, so a configured Langfuse (OpenTelemetry-based) still sees only model calls.

## 2. Refusal texts

- One translation in `_ServedMCP.call_tool`: an `UnexpectedToolError` whose cause is a `BackendError` becomes `ToolError("Error executing tool <name>: <reason>")`, the text 1.x produced.
- Deliberate refusals raised in tool code become `ToolError`. The plan audits the `ValueError`/`RuntimeError` raise sites in `mcp_server/` and says which are deliberate.
- Anything else is a crash: the agent reads `Error executing tool <name>`, the log keeps the traceback.

## 3. Protocol

- Client label: `_client_label` keeps reading `session.client_params` (handshake for 2025 clients, per-request `_meta` for 2026-07-28 clients that send `clientInfo`); the `MAESTRO_CS_MCP_CLIENT` fallback stays.
- Claude Desktop bridge (`mcpb/server/index.js`): for a request whose `_meta` carries `io.modelcontextprotocol/protocolVersion`, it sends `MCP-Protocol-Version`, `Mcp-Method` and, for a named method, `Mcp-Name` from the body. 2025 traffic is untouched. The bundle is re-packed at release (already pending).
- From the SDK, unasked: `resultType`, `server/discover`, `serverInfo` in results.
- Cache hints: TTL 0, private, for every cacheable method (no caching, as today).
- Tool order: registration order, already stable; a test pins it.

## 4. Dependencies

- `mcp>=2.3,<3` (pyproject comment rewritten). New transitive packages: `mcp-types`, `httpx2`; floors `pydantic>=2.12`, `anyio>=4.9` (the lock already meets them).
- `requirements.lock` regenerated with hashes (pip-compile, same command as its header). A CVE-flagged package the regeneration touches, such as `opentelemetry-api`, goes to a fixed version.

## 5. Testing

- Golden record first: before the bump, a test script records on 1.30, per set, `tools/list`, `prompts/list`, one call result per answer shape and one of each refusal kind (removed tool, removed argument, outside the set, backend 409, backend validation). The record is committed as a fixture; after the bump the same calls match it, apart from fields the revision adds.
- Loopback, both eras: a 2025 handshake with a session (raw JSON-RPC over HTTP), and a 2026-07-28 client (the 2.x client).
- Targeted: client label in both eras; a 15 MiB evidence upload; set isolation; generic crash text with a logged traceback; no OpenTelemetry middleware; cache hints; tool order; bridge header mirroring (node tests).
- Gates: full backend suite (xdist), node tests, slop ratchet, SYSTEM.md gate.
- Live: scratch backend (spare port, scratch `MAESTRO_HOME`) driven by both eras and through the bridge, re-running the Phase 3c walk.

## 6. Docs

- SYSTEM.md is at its 90% line: SDK detail goes to `docs/agent-surfaces.md`; SYSTEM.md keeps the invariant in one line.
- `mcp_server/README.md`, the pyproject comment, CHANGELOG Unreleased ("agents see no change; clients on the 2026-07-28 revision are served").

## Out of scope

"Input required" questions, real cache lifetimes, `subscriptions/listen`, a Skills extension (none exists in the spec yet; the playbooks already ship as MCP prompts and plugin skills), pushing or releasing.

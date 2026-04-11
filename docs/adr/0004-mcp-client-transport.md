# ADR-0004: MCP Client Transport Selection

**Status:** Accepted  
**Date:** 2026-04-11  
**Deciders:** Agent Studio Architecture Team

## Context

Agent Studio is an MCP client that connects to a heterogeneous fleet of MCP servers: some are cheap, stateless binaries best spawned as child processes (Git MCP, Filesystem MCP, Fetch MCP); some are shared stateful services that must persist across orchestrator replicas (Ruflo for cross-session memory, a central code-review-graph instance with its SQLite graph); some are user-managed existing services with their own network addresses (the user's WMS MCP server, a GitHub-maintained MCP server); and some will be added dynamically by operators from the MCP Marketplace. No single transport mechanism fits all of these deployment models.

The MCP specification defines three transport mechanisms that the `@modelcontextprotocol/sdk` supports: `stdio` (the client spawns the server as a subprocess and exchanges JSON-RPC over stdin/stdout), `streamable-http` (HTTP requests with chunked/SSE response streaming for tool calls), and `sse` (server-sent events over a persistent HTTP connection, useful for servers that push notifications). The choice of transport has direct implications for deployment topology, failure modes, latency, and how secrets are passed to servers.

`stdio` transport is ideal for local sidecar processes — it requires no network configuration, the server lifetime is tied to the client process, secrets can be passed as environment variables at spawn time, and there is zero network overhead. However, `stdio` servers cannot be shared across orchestrator replicas, which rules it out for services like Ruflo where cross-replica memory consistency is required. `streamable-http` enables a single server instance to be shared across many clients (replicas, tenants) and allows the server to be deployed independently of the orchestrator. `sse` provides the same sharing capability as `streamable-http` but is better suited for servers that push unsolicited events (health updates, streaming partial results). The transport choice must be made per server, not globally, and must be declarable in config so operators can change it as deployment models evolve.

## Decision

The `mcp-client` package supports all three MCP transports — `stdio`, `streamable-http`, and `sse` — selectable per server entry in the `McpServerSpec` registry. Every `McpServerSpec` declares exactly one transport via its `transport` field. The client instantiates the appropriate `@modelcontextprotocol/sdk` transport class at connection time based on this field. Transport-specific configuration is co-located in the spec: `stdio` entries carry a `command` array and `env` block; `streamable-http` and `sse` entries carry a `url` and optional auth headers (resolved from the secrets backend at connection time, never stored in the spec itself).

The expected transport assignments for the built-in server fleet are: `stdio` for Git, Filesystem, Fetch, Playwright (spawned per orchestrator pod, sandboxed inside Docker); `streamable-http` for a centrally deployed Ruflo service, a shared code-review-graph sidecar, the GitHub MCP server, and any enterprise system the user's WMS server exposes over HTTP; and `sse` for servers that push streaming partial results or health notifications. Operators can change a server's transport without changing any agent-runtime code — only the `McpServerSpec` entry needs updating, and the hot-reload mechanism (ADR-0011) applies the change without restarting the orchestrator.

## Consequences

### Positive
- Each MCP server can be deployed in the model that fits it best — cheap stateless sidecars via `stdio`, shared stateful services via HTTP — without forcing a one-size-fits-all network topology.
- `stdio` servers get secrets via environment variable injection at spawn time, which is the most operationally simple and secure path (no credentials traverse the network).
- `streamable-http` and `sse` servers can be horizontally scaled and load-balanced independently of the orchestrator, enabling Ruflo and code-review-graph to serve multiple orchestrator replicas from a single persistent data store.
- Adding a new transport type in a future MCP SDK version requires only a new branch in the transport factory function; no changes to `McpServerSpec` schema consumers.

### Negative / Trade-offs
- Supporting three transports means the `mcp-client` connection lifecycle manager must handle three distinct connection/reconnection patterns. `stdio` processes can crash and must be re-spawned; HTTP connections have keep-alive semantics; SSE connections must handle reconnection with `Last-Event-ID`. This adds implementation complexity relative to a single-transport design.
- Per-server transport configuration increases the surface area of the `McpServerSpec` schema; operators must understand which transport to choose when registering a new server in the MCP Marketplace.
- `streamable-http` servers must expose CORS headers and handle authentication at the HTTP layer; the client must inject auth headers from the secrets backend on every request, which requires careful secret rotation handling.

### Neutral
- The MCP specification may evolve to deprecate or merge transport types; the transport factory is the single point of change if the SDK drops a transport in a future version.
- In development environments where running a central Ruflo service is inconvenient, a developer can override a `streamable-http` Ruflo entry to `stdio` by changing the local `agent-studio.mcp.yaml` — no code changes needed.

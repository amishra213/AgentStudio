# ADR-0011: Dynamic MCP Manager with Hot-Reload and MCP Marketplace Catalog

**Status:** Accepted  
**Date:** 2026-04-11  
**Deciders:** Agent Studio Architecture Team

## Context

Agent Studio's MCP server fleet is not static. New enterprise systems become relevant as tenants onboard (a new Jira instance, a Slack workspace, a custom internal tool). New community MCP servers appear that provide capabilities useful to the delivery loop. Existing servers need to be upgraded when upstream projects release improvements or security fixes. Tenants may want to disable a server for a period (e.g. disable web search during an audit period) without removing it from the registry permanently.

In a naive implementation, adding or upgrading an MCP server requires an operator to edit a config file and restart the orchestrator. For a hosted multi-tenant service, orchestrator restarts are disruptive — in-flight tasks lose their streaming connections, HITL approval flows are interrupted, and the service may enter a brief degraded state during pod restart. The restartless alternative requires a runtime registry that the running orchestrator can observe for changes.

Security is the primary concern in a dynamic system. The registry controls which code runs in the orchestrator's process space (stdio servers are spawned as child processes) or is reachable over the network (HTTP/SSE servers). A supply-chain attack that introduces a malicious `source.kind=git` server, or a misconfiguration that widens an allowlist beyond intended scope, could grant agents access to capabilities that an operator never intended. The dynamic manager must therefore apply the same allowlist diff safety check on every upgrade, and must require explicit human approval for any registration that introduces new code execution paths (git-cloned or binary sources).

The mental model for operators should be familiar. Agent Studio already has a SKILLs loader that lets users drop new capabilities into a directory without redeploying. The MCP manager should feel like the same pattern applied to servers rather than skills: declarative registration, an `install/enable/disable/remove` lifecycle, and immediate availability without restarts.

## Decision

The MCP Registry supports runtime hot-reload: adding, removing, upgrading, enabling, and disabling servers is picked up by the running orchestrator without a restart. The hot-reload mechanism is driven by: a PostgreSQL `LISTEN/NOTIFY` channel for tenant-override changes made via the Web UI or REST API (changes committed to the `mcp_server_registrations` DB table immediately notify all orchestrator pods); and a file-system watcher for changes to per-project `agent-studio.mcp.yaml` files checked into the target repo. In-flight tasks keep the snapshot of servers they started with (their McpServerSpec set is captured at task start); new tasks see the updated set. This prevents a mid-task server upgrade from destabilizing a running task.

New tools that appear in an upgraded server's manifest default to DENIED in the allowlist until an operator explicitly grants them — the allowlist-diff check runs automatically after every upgrade and surfaces new tools in the Web UI "MCP Manager" view. The Web UI exposes a curated "MCP Marketplace" catalog (shipped as part of the platform) listing known-good servers (Ruflo, Git, GitHub, Playwright, Filesystem, Fetch, Slack, Confluence, Jira, Notion, and others). An operator installs a catalogued server by clicking Install, filling in required secrets/config references, and submitting — the manager writes the registration to the DB, probes health, runs the allowlist diff, and makes the tools available immediately. Unlisted servers can be added by pasting a raw `McpServerSpec` YAML or JSON.

Server registrations of `source.kind=git` or `source.kind=binary` require explicit human approval (routed through the HITL flow) before activation, because these kinds execute arbitrary code in the orchestrator's environment. Every registry mutation (add/remove/upgrade/enable/disable, allowlist change) is written to an append-only audit log with actor, timestamp, diff, and reason.

## Consequences

### Positive
- Operators can add new capabilities (a new enterprise connector, a new knowledge source, a new browser automation server) without deploying new orchestrator code or causing a service restart.
- The curated MCP Marketplace lowers the barrier to enabling well-known servers — most tenants will never need to write a raw `McpServerSpec`.
- New tools from an upgraded server default to DENIED, providing a safe default posture: a supply-chain surprise cannot silently widen the attack surface without operator action.
- The same mental model (declarative registration, install/enable/disable/remove lifecycle) applies to both SKILLs and MCP servers, reducing the number of concepts operators must learn.
- Hot-reload enables zero-downtime upgrades for HTTP/SSE servers; stdio servers are re-spawned gracefully (new tasks get the new version, in-flight tasks finish on the old version).

### Negative / Trade-offs
- Hot-reload of stdio servers (spawned child processes) requires careful lifecycle management: the old child process must be drained and killed gracefully while the new one is spawned, and the transition window must not lose in-flight tool calls. This is complex to implement correctly.
- The PostgreSQL `LISTEN/NOTIFY` mechanism for cross-pod hot-reload adds a dependency on the Postgres connection being maintained and responsive; if the connection is lost and re-established, missed notifications must be reconciled from the DB state.
- A curated marketplace requires ongoing curation effort to keep entries up-to-date with upstream version changes, new configuration requirements, and deprecations.
- The mandatory human approval for `source.kind=git` and `source.kind=binary` registrations adds friction for operators who want to rapidly prototype with a git-cloned community server. This friction is intentional and cannot be waived without operator-level RBAC override.

### Neutral
- The MCP Manager exposes a CLI (`mcp list`, `mcp install`, `mcp upgrade`, `mcp disable`, `mcp enable`, `mcp remove`, `mcp test`, `mcp describe`) that mirrors the Web UI operations for automation and scripting use cases.
- Per-project `agent-studio.mcp.yaml` files in the target repo travel with the code, enabling project-specific server configurations (e.g. a project-specific WMS endpoint) without affecting other tenants or projects.
- The version pin + upgrade-safety model (opt-in upgrades, allowlist diff check) mirrors how the monorepo manages its own npm dependencies — operators familiar with one system understand the other.

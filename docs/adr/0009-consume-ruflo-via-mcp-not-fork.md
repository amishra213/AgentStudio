# ADR-0009: Consume Ruflo via MCP Only — Do Not Fork

**Status:** Accepted  
**Date:** 2026-04-11  
**Deciders:** Agent Studio Architecture Team

## Context

Ruflo (`ruvnet/ruflo`) ships a rich set of capabilities: HNSW-indexed vector memory, PostgreSQL RuVector storage, AgentDB, 8 memory types across project/local/user scopes, pattern storage and retrieval, and — beyond the memory layer — a swarm orchestration system with queen, router, and consensus primitives for multi-agent coordination. Agent Studio needs only Ruflo's memory and pattern tools. The question is whether to consume Ruflo as an unmodified upstream distribution, fork it to customize behavior, or selectively import its internal libraries.

Forking Ruflo would give Agent Studio the ability to modify memory schemas, add new scope types, tune retrieval algorithms, and strip out the swarm features. However, a fork immediately creates a divergent codebase: every upstream bug fix, security patch, or new memory capability added to Ruflo must be manually merged into the fork. Given that Ruflo is an active project and Agent Studio's team is focused on platform concerns (orchestration, UI, MCP client, delivery bundle), maintaining a fork would be a compounding maintenance burden with no clear end state. The primary reason to fork — customizing behavior — can be achieved at the MCP protocol level instead: the per-role tool allowlist in the MCP Server Registry (ADR-0010) is the mechanism for restricting which Ruflo tools are accessible, without touching Ruflo's internals.

Selectively importing Ruflo's internal libraries (e.g. importing only its HNSW memory module as an npm package) was considered but ruled out because Ruflo does not publish its internals as individually installable packages. Importing internal modules across a package boundary creates an implicit coupling to Ruflo's internal structure that would break silently on any upstream refactor.

Consuming Ruflo as an MCP server via its published tool interface is the cleanest approach: the interface is stable and versioned, the Agent Studio codebase has no knowledge of Ruflo's internals, upgrades are managed by updating the version pin in the MCP Registry, and the boundary is explicit and auditable. The swarm/queen/router/consensus tools are simply absent from the per-role allowlists — they are never called, never exposed to agents, and their existence in Ruflo's manifest is irrelevant to Agent Studio's operation.

## Decision

Ruflo is consumed as-is from its upstream distribution, accessed exclusively via its MCP server interface. Agent Studio does not fork Ruflo, does not import Ruflo's internal libraries, and does not modify Ruflo's behavior. The Ruflo entry in the MCP Server Registry specifies a pinned version, transport configuration (`stdio` for local deployment or `streamable-http` for central deployment — ADR-0004), and a per-role tool allowlist that permits only `memory.*` and `pattern.*` tools. All of Ruflo's swarm/queen/router/consensus tools are absent from every role's allowlist and are therefore unreachable from any agent call.

Upgrades are managed through the normal MCP Registry lifecycle (ADR-0011): when a new Ruflo version is available, the operator upgrades the version pin, the registry re-runs the health check and allowlist diff, and any new tools that appear in the upgraded manifest default to DENIED until explicitly granted. The `MemoryClient` wrapper in `agent-runtime` (ADR-0005) is the single point of adaptation if a Ruflo API change requires a call-site update; no other package has direct knowledge of Ruflo's tool interface.

## Consequences

### Positive
- Zero ongoing maintenance burden from a fork; all upstream bug fixes, security patches, and memory capability improvements are available by updating the version pin and running the allowlist diff check.
- The MCP protocol boundary is a clean, explicit contract; Ruflo can be upgraded, replaced, or run in multiple configurations (local stdio, central HTTP) without any change to agent-runtime code.
- The per-role tool allowlist enforces the scope boundary (memory + pattern only) without requiring any code changes to Ruflo itself; the restriction is entirely on Agent Studio's side.
- A clean non-fork relationship means Agent Studio can credibly contribute memory-related improvements back to Ruflo upstream rather than maintaining them in a private fork.

### Negative / Trade-offs
- Agent Studio cannot customize Ruflo's internal memory retrieval algorithms, schema, or scope model without contributing changes upstream (which requires upstream maintainer review and may not be accepted on Agent Studio's schedule).
- If Ruflo's published tool interface changes in a breaking way between versions, the `MemoryClient` wrapper must be updated and the version pin held until the update is complete — a short window of version lock.
- Ruflo's swarm features are pinned to the same version as the memory features; the deployment includes code that is deliberately never used. This is a minor inefficiency but not a correctness or security concern (unused tools are blocked at the allowlist layer).

### Neutral
- This ADR is a companion to ADR-0005 (which establishes the delegation of memory to Ruflo) and ADR-0010 (which establishes how allowlists enforce scope boundaries). The three decisions form an interlocking policy.
- If Ruflo were ever abandoned or its license changed incompatibly, the migration path is: implement a replacement MCP server that exposes the same `memory.*` and `pattern.*` tool names, update the Ruflo registry entry to point to the replacement, and update the `MemoryClient` wrapper if any signatures changed. No other package requires modification.

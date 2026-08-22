# ADR-0002: MCP Is the Sole Integration Substrate

## Status
Accepted — supersedes an earlier draft that specified a bespoke HTTP + webhook "Agent Protocol".

## Context
Meridian needs agents to read tickets, do work against external systems, and write results back.
Three ways to connect them:

1. A **bespoke agent protocol** — Meridian defines its own dispatch/callback contract that every
   agent vendor implements.
2. **Fixed connectors** — Meridian builds an integration per external system, as traditional
   trackers do.
3. **MCP** — Meridian exposes its own MCP server, and agents reach every other system through
   MCP servers too.

The requirement that decides it: the harness must be able to choose which tool to use at runtime
from a set that changes as the workspace enables new servers, with no Meridian deployment. That is
precisely a tool-discovery-and-invocation problem, which MCP already standardises and which model
runtimes — OpenHands among them — already speak as clients.

## Decision
**MCP is the only agent integration substrate.**

- Meridian exposes a **Meridian MCP Server** — `tickets.query`, `claim`, `comment`,
  `update_status`, `complete`, `ask_human`, `handoff`, `usage.report`, `capabilities.list`. This is
  the *only* programmatic write path for agents.
- Every external capability is likewise an MCP server, acquired from the marketplace or registered
  privately.
- There is no Meridian-specific agent SDK and no bespoke callback contract. A harness participates
  by being an MCP client.
- Meridian never proxies tool traffic: the harness calls MCP servers directly. Meridian governs
  *which* servers it may call and records *that* it did.

## Alternatives Considered
- **Bespoke agent protocol.** Rejected: it would require every vendor to implement a
  Meridian-specific contract, and — decisively — it would not give the harness a *discoverable*
  tool surface. Runtime tool selection over a changing enabled set is the whole point of D5, and a
  fixed dispatch/callback shape does not provide it. It would also mean building manifest
  validation, schema negotiation, and transport handling that MCP already specifies.
- **Fixed connectors.** Rejected: capability would then change only by Meridian release, directly
  contradicting D7.
- **MCP plus a push-dispatch fallback.** Rejected as unnecessary complexity — see
  [ADR-0007](0007-harness-owned-routing.md), which covers how work reaches the harness without a
  second protocol.

## Consequences
- Any MCP-speaking runtime can be a harness; swapping OpenHands for another is a registration
  change, not an integration project.
- Enabling a marketplace or private MCP server changes agent capability with no redeploy (SC-4).
- Meridian must handle the full failure surface of arbitrary external servers — unreachable,
  slow, malformed, or dishonest about their effect classes. Hence certification, effect-class
  verification, health tracking, and per-call recording
  ([`mcp-marketplace.md`](../03-components/mcp-marketplace.md), [`06-security.md`](../06-security.md) §3).
- Because tool selection is model-driven over a discoverable set, the **grant set becomes the
  security boundary** rather than the protocol shape. That is why grants are tool-level,
  default-closed, and enforced server-side on every call
  ([`permissions-rbac.md`](../03-components/permissions-rbac.md) §3–4).
- Meridian's own API surface must be designed as *tools for a model*, not just endpoints for a UI:
  small, well-described, typed errors, idempotent, and lease-guarded.

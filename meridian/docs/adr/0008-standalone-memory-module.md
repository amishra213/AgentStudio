# ADR-0008: Memory Is a Standalone Service Consumed Over MCP

## Status
Accepted

## Context
Agents repeat mistakes and rediscover the same facts across tickets. A memory layer is the obvious
remedy, and there are three plausible shapes for it:

1. **Embedded in Meridian** — a `memory` table and a retrieval call inside the Core service.
2. **Inside the harness** — let OpenHands (or whichever runtime) keep its own memory.
3. **A standalone service exposed as an MCP server** — its own store, own API, own release cycle.

The decision interacts with several existing invariants: MCP is the sole integration substrate
([ADR-0002](0002-mcp-as-integration-substrate.md)); the harness is swappable
([ADR-0007](0007-harness-owned-routing.md)); and capability reaches agents only through grants
([`permissions-rbac.md`](../03-components/permissions-rbac.md) §3).

## Decision
Memory is a **standalone service (Mnemos)** with its own datastore and version line, exposed as an
MCP server and consumed by agents through ordinary grants. It ingests work outcomes through a thin
adapter over Meridian's event stream and holds no compile-time dependency on Meridian.

Read and write are **separate MCP tools**, so recall can be granted without the ability to teach.

## Alternatives Considered

- **Embedded in Meridian.** Rejected on three counts. It would make memory access *ambient* rather
  than granted, bypassing the security model that everything else obeys — a profile with ticket
  access would implicitly have memory access. It would put memory in the ticket write path, so a
  memory outage becomes a ticketing outage. And it would make measuring memory's contribution
  nearly impossible, since there would be no boundary to A/B across
  ([`memory-module.md`](../03-components/memory-module.md) §7).

- **Harness-owned memory.** Rejected as directly contrary to
  [ADR-0007](0007-harness-owned-routing.md): the harness is meant to be swappable, and memory is the
  most valuable asset the system accumulates. Putting the org's accumulated knowledge inside a
  replaceable runtime means switching harnesses forfeits it, which in practice means never
  switching. It also scopes memory to one harness when several may run concurrently.

- **Per-agent-profile memory only.** Rejected: the useful unit of learning is the *work*, not the
  worker. A pitfall discovered by the triage profile must reach the change-execution profile, and
  scoping memory to profiles prevents exactly the cross-actor transfer that makes it valuable.

## Consequences

- Memory is governed like any other capability: grants, clearance filtering, per-call audit through
  `McpCallRecord`, and metered context cost through `UsageRecord`.
- Losing Mnemos degrades quality, not availability — agents work without recall.
- The module is independently deployable and reusable against a different system of record, which
  is the practical test of whether the boundary is real.
- **Persistence turns two known risks into worse ones**, and this ADR accepts that cost explicitly:
  redaction must occur *before* extraction rather than after, because a durable store of
  model-written prose cannot be cleaned retroactively; and prompt injection gains a cross-ticket
  vector, so external-provenance content is excluded from extraction by default and multi-ticket
  evidence is required for promotion. See [`memory-module.md`](../03-components/memory-module.md) §6.
- A separate store means eventual consistency between a ticket's current state and memory derived
  from it. Source invalidation (§5) handles the important cases; perfect consistency is not
  attempted and is not needed, since memory is advisory rather than authoritative.

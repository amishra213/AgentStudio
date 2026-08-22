# ADR-0007: The Harness Pulls and Routes; Meridian Governs

## Status
Accepted

## Context
Once MCP is the substrate ([ADR-0002](0002-mcp-as-integration-substrate.md)), two questions
remain: how does work reach the harness, and who decides which MCP server handles a given ticket?

The tempting design is for Meridian to push-dispatch each ticket to a specific agent endpoint and
name the tool to use. It centralises control and makes routing inspectable. It also requires
Meridian to reason about ticket content in order to route — which means Meridian needs a model, a
prompt, and a tool-selection loop, i.e. Meridian becomes a second agent runtime competing with the
one it just integrated.

## Decision
**The harness acquires work and chooses tools. Meridian sets and enforces the boundary.**

| Decision | Owner |
|---|---|
| Which tickets are eligible | Meridian — `TriggerRule.filter`, inspectable in the UI, owned by a PM |
| Which agent profile handles it | Meridian — assignment, or the trigger rule's profile |
| Which MCP servers that profile *may* call | Meridian — `McpGrant`, enforced server-side |
| **Which server/tool to actually call** | **The harness** — a reasoning decision over ticket content |
| Whether the resulting state change is legal | Meridian — Workflow Engine |

Work reaches the harness two ways, both first-class and both supported simultaneously:

- **Event** — a matching mutation notifies registered harnesses (thin payload: identifiers only).
- **Scheduled sweep** — the harness re-queries the filter from scratch on a cron.

## Alternatives Considered
- **Push-dispatch with Meridian-chosen tools.** Rejected: it duplicates the harness's core
  competence inside Meridian, and it breaks the moment the right tool depends on ticket content
  that only a model reading the ticket can judge.
- **Events only.** Rejected. Event-only automation strands work silently, and the failure is
  invisible because the missing signal is the absence of a message — a harness outage, a partition,
  a rule created after the tickets it should match, or eligibility changing with no event (an SLA
  clock crossing a threshold, a blocker resolving elsewhere). The sweep is what makes the worked
  set equal the matching set.
- **Polling only.** Rejected: acceptable for delivery work, unacceptable for incidents where
  minutes matter.

## Consequences
- Both trigger paths active means duplicate pickup is a real risk, so **claim/lease is mandatory**,
  not an optimisation: atomic compare-and-set on the ticket, `lease_token` required on every
  mutation, expiry-based recovery from a dead harness
  ([`agent-harness.md`](../03-components/agent-harness.md) §4).
- Event payloads are deliberately thin — an identifier and a reason. The harness fetches content
  via `tickets.get`, so filtering and visibility are evaluated at read time against current state,
  and a queued event can never deliver stale or since-restricted data.
- Because routing is model-driven, the **grant set is the only real boundary**. This is what forces
  grants to be tool-level, default-closed, and re-validated on every call rather than only at
  catalogue assembly ([`permissions-rbac.md`](../03-components/permissions-rbac.md) §4).
- Routing quality becomes an observable rather than a configuration: `handoffs_per_ticket` and
  `denied_call_rate` ([`roi-analytics.md`](../03-components/roi-analytics.md) §4) are how a bad
  routing outcome is detected, since no static rule exists to inspect.
- Meridian holds no reference to any agent framework, so harnesses are swappable and several can
  run concurrently, each backing different profiles.

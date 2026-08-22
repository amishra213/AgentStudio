# ADR-0002: An Open Agent Protocol, Not a Meridian SDK Requirement

## Status
Accepted

## Context
For the marketplace (overview G3) to be genuinely open — any vendor, any internal team, any tech
stack — Meridian cannot require agents to be built with a specific SDK or run inside Meridian's own
process. At the same time, the Orchestrator needs a predictable, small set of things every agent
can be relied on to do, regardless of what's happening inside it.

## Decision
Define the **Agent Protocol**: a small HTTP + signed-webhook contract (dispatch, and four possible
outcomes — completed / blocked / handoff / rejected — see
[`04-api-contracts.md`](../04-api-contracts.md) §3) that any HTTP-capable service can implement.
Meridian does not ship a required client SDK; the protocol is documented as an open spec (request/
response JSON schemas + signing scheme) that any language can implement directly, the same way a
webhook-based payment gateway doesn't require a specific server framework.

## Alternatives Considered
- **Require agents to run inside Meridian via an embedded runtime** (e.g., only accept agents
  built on one specific agent SDK, hosted by Meridian). Rejected: this would make the marketplace
  a walled garden and contradicts the "any vendor" goal; it also makes Meridian responsible for
  agent runtime security and scaling, which is explicitly out of scope (see
  [`00-overview.md`](../00-overview.md) non-goals).
- **A synchronous-only protocol** (agent must respond within one HTTP request/response, no
  webhooks). Rejected: real agent work (especially anything involving its own tool loop) can take
  minutes to hours; forcing synchronous responses would mean either absurdly long-held HTTP
  connections or agents that can't do real work.

## Consequences
- Any team can build a Meridian-compatible agent without touching Meridian's codebase, satisfying
  overview G3 and SC-2 (5-minute install-to-assignable).
- The Orchestrator must handle the full space of failure modes an arbitrary external HTTP service
  can present (timeouts, malformed payloads, replayed webhooks) explicitly — see
  [`agent-execution-and-handoff.md`](../03-components/agent-execution-and-handoff.md) §7 and
  [`06-security.md`](../06-security.md) §3.
- Protocol versioning (`protocol_version` field) is required from v1 onward, since we cannot force
  every published agent to upgrade in lockstep with Meridian's own releases.

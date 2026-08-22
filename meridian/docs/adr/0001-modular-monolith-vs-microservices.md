# ADR-0001: Modular Monolith at MVP, Not Microservices

## Status
Accepted

## Context
[`01-architecture.md`](../01-architecture.md) defines eight service-shaped modules (Core PM,
Workflow Engine, Agent Marketplace, Agent Orchestrator, Collaboration/Realtime, ROI & Analytics,
Notification, Web UI). Standing these up as independently deployed microservices from day one adds
operational overhead (service discovery, distributed tracing, N deployment pipelines, network
failure handling between modules that are, at MVP scale, called synchronously anyway) before there
is traffic that justifies it.

## Decision
Ship as a **modular monolith**: one deployable backend process, with the module boundaries from
`01-architecture.md` §2 enforced in code (no module reaches into another's tables directly; all
cross-module calls go through an internal API layer identical in shape to what would later become
a network call). The Agent Orchestrator's calls to external agent processes are the one place real
network boundaries exist from day one, because those are genuinely external systems, not an
internal scaling decision.

## Consequences
- Splitting a module into its own service later is a deployment and networking change, not a
  data-model or business-logic rewrite, because the module never had implicit access to another
  module's internals to begin with.
- The most likely first split, when it comes, is the **Agent Orchestrator** — it has different
  scaling characteristics (I/O-bound on external agent latency) than Core PM (DB-bound,
  low-latency CRUD) and different failure isolation needs (an Orchestrator incident should not be
  able to degrade basic ticket CRUD).
- Until that split happens, all module-to-module "calls" are in-process function calls with the
  same input/output contracts they'd have over the network, so the discipline is paid for once.

# Meridian — Documentation Index

Read in this order. Each doc links forward to the components it depends on and back to the
concepts it builds on.

1. [`00-overview.md`](00-overview.md) — what Meridian is, the seven differentiators, personas,
   non-goals, and how success is measured.
2. [`01-architecture.md`](01-architecture.md) — the record plane vs. the execution plane, the
   service map, the trigger model, and who decides what.
3. [`02-data-model.md`](02-data-model.md) — every entity and relationship. Nearly every other doc
   refers back to this one.
4. **Components** (`03-components/`):

   | Doc | Covers |
   |---|---|
   | [`timeline.md`](03-components/timeline.md) | The primary surface: marks, status colour, swimlanes, dependencies, baseline vs actual |
   | [`delivery-modes.md`](03-components/delivery-modes.md) | Waterfall, agile, kanban, hybrid on one model |
   | [`ticketing.md`](03-components/ticketing.md) | Ticket types incl. incident/problem/change, status graphs, links, automations |
   | [`project-administration.md`](03-components/project-administration.md) | Project creation, templates, status definition, tracking configuration |
   | [`mcp-marketplace.md`](03-components/mcp-marketplace.md) | MCP catalog, manifests, effect classes, certification, private registration |
   | [`agent-harness.md`](03-components/agent-harness.md) | Trigger rules, claim/lease, MCP routing, outcomes, handoff, guardrails |
   | [`memory-module.md`](03-components/memory-module.md) | Mnemos: standalone self-learning memory — scopes, override, ingestion pipeline, decay, measured lift |
   | [`human-ai-collaboration.md`](03-components/human-ai-collaboration.md) | Co-assignment, ask-human, presence, live takeover, feedback signals |
   | [`roi-analytics.md`](03-components/roi-analytics.md) | Token accounting, cost split, efficiency metrics, budgets, ROI at task and project level |
   | [`permissions-rbac.md`](03-components/permissions-rbac.md) | Human roles, the three-layer MCP grant model, ticket visibility management |
   | [`notifications-and-integrations.md`](03-components/notifications-and-integrations.md) | Fan-out, digesting, inbound integrations |

5. [`04-api-contracts.md`](04-api-contracts.md) — the Meridian MCP tool surface, event stream,
   harness registration, REST, and realtime.
6. [`05-sequence-flows.md`](05-sequence-flows.md) — worked end-to-end examples.
7. [`06-security.md`](06-security.md) — tenancy, visibility enforcement, MCP trust, prompt
   injection, credentials, audit.
8. [`07-roadmap.md`](07-roadmap.md) — phased delivery plan.
9. [`08-design-critique.md`](08-design-critique.md) — adversarial review of this design: defects
   found and fixed, and known-open issues with the reasoning for accepting them. **Read this
   before building** — it is where the design says what it is bad at.
10. `adr/` — decision records:

   | ADR | Decision |
   |---|---|
   | [0001](adr/0001-modular-monolith-vs-microservices.md) | Modular monolith at MVP |
   | [0002](adr/0002-mcp-as-integration-substrate.md) | MCP is the sole integration substrate |
   | [0003](adr/0003-event-sourced-ticket-activity.md) | Ticket history is an append-only event log |
   | [0004](adr/0004-roi-attribution-model.md) | ROI attributed by time/cost share across legs |
   | [0005](adr/0005-handoff-loop-protection.md) | Four-layer handoff loop protection |
   | [0006](adr/0006-unified-waterfall-and-agile.md) | One model for all four delivery modes |
   | [0007](adr/0007-harness-owned-routing.md) | Harness pulls and routes; Meridian governs |
   | [0008](adr/0008-standalone-memory-module.md) | Memory is a standalone service consumed over MCP |
   | [0009](adr/0009-memory-learns-by-measured-lift.md) | Memory confidence comes from measured lift, not usage |

**Document status:** Living design document, no code yet. Intended to be concrete enough that
implementation can start directly from this tree.

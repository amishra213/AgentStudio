# Meridian — Documentation Index

Read in this order. Each doc links forward to the components/details it depends on and back to the concepts it builds on.

1. [`00-overview.md`](00-overview.md) — what Meridian is, who it's for, what it explicitly does not do, and how success is measured.
2. [`01-architecture.md`](01-architecture.md) — the services, how they talk to each other, and why.
3. [`02-data-model.md`](02-data-model.md) — every entity in the system and the relationships between them. Nearly every other doc refers back to this one.
4. **Components** (`03-components/`) — one file per subsystem:
   - [`timeline-and-sprints.md`](03-components/timeline-and-sprints.md)
   - [`ticketing.md`](03-components/ticketing.md)
   - [`agent-marketplace.md`](03-components/agent-marketplace.md)
   - [`agent-execution-and-handoff.md`](03-components/agent-execution-and-handoff.md)
   - [`human-ai-collaboration.md`](03-components/human-ai-collaboration.md)
   - [`roi-analytics.md`](03-components/roi-analytics.md)
   - [`permissions-rbac.md`](03-components/permissions-rbac.md)
   - [`notifications-and-integrations.md`](03-components/notifications-and-integrations.md)
5. [`04-api-contracts.md`](04-api-contracts.md) — REST/WebSocket surface and the Agent Protocol wire format.
6. [`05-sequence-flows.md`](05-sequence-flows.md) — worked end-to-end examples tying the components together.
7. [`06-security.md`](06-security.md) — tenancy, sandboxing, secrets, audit.
8. [`07-roadmap.md`](07-roadmap.md) — phased delivery plan.
9. `adr/` — standalone decision records, referenced from the docs above where relevant.

**Document status:** Living design document, no code yet. Intended to be concrete enough that implementation can start directly from this tree.

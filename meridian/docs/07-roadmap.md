# Roadmap

> Phased build plan. Each phase is usable on its own — Meridian is a real PM/ticketing tool at the
> end of Phase 1, before a single agent exists.

---

## Phase 0 — Foundations
- Workspace, project, user, RBAC roles (human-only) — [`permissions-rbac.md`](03-components/permissions-rbac.md) §1.
- Ticket data model, custom ticket types and field schemas — [`02-data-model.md`](02-data-model.md), [`ticketing.md`](03-components/ticketing.md) §1.
- Append-only `activity_event` log as the single write path — [ADR-0003](adr/0003-event-sourced-ticket-activity.md).

## Phase 1 — Core PM & Ticketing (humans only)
- Configurable Workflow Engine (status graphs, transition validation, automations) — [`ticketing.md`](03-components/ticketing.md) §2, §4.
- Timeline view (milestones, dependencies), Sprint lifecycle for `scrum` projects — [`timeline-and-sprints.md`](03-components/timeline-and-sprints.md).
- Board/backlog views, saved filters, comments — [`ticketing.md`](03-components/ticketing.md) §5–6.
- Notification Service (in-app + email) — [`notifications-and-integrations.md`](03-components/notifications-and-integrations.md) §1–2.

**Exit criteria:** a team can run a real sprint end-to-end with zero agents involved.

## Phase 2 — Agent Marketplace (catalog + install, no dispatch yet)
- Manifest schema + validation, listing/versioning — [`agent-marketplace.md`](03-components/agent-marketplace.md) §1–2.
- Certification pipeline (`unverified`→`community` tiers only at this phase) — §3.
- Install flow, `AgentInstallation` with `permission_scope`/`budget_ceiling` — §4.
- Agents appear in assignee pickers (manual assignment only, no auto-dispatch) — overview SC-1, SC-2.

**Exit criteria:** an admin can install a real agent and manually assign it a ticket; nothing runs automatically yet.

## Phase 3 — Agent Protocol & Single-Agent Execution
- Agent Protocol v1 (dispatch, complete, blocked, rejected — handoff deferred to Phase 4) — [`04-api-contracts.md`](04-api-contracts.md) §3, [ADR-0002](adr/0002-agent-protocol-standard.md).
- Orchestrator dispatch, payload filtering by permission scope + ticket-type contract — [`agent-execution-and-handoff.md`](03-components/agent-execution-and-handoff.md) §1–2.
- Ask-human blocking flow, SLA clock — §6, [`human-ai-collaboration.md`](03-components/human-ai-collaboration.md) §3.
- Timeout/failure handling — [`agent-execution-and-handoff.md`](03-components/agent-execution-and-handoff.md) §7.
- Webhook signing/verification — [`06-security.md`](06-security.md) §3.

**Exit criteria:** a single installed agent can be assigned a ticket, complete it or block on a human, unattended.

## Phase 4 — Multi-Agent Handoff
- `HandoffEvent`, `context_bundle` construction — [`agent-execution-and-handoff.md`](03-components/agent-execution-and-handoff.md) §3.
- Handoff routing (explicit target + capability-tag matching) — §4.
- Loop protection: hop ceiling, cycle detection, budget/wall-clock ceilings — §5, [ADR-0005](adr/0005-handoff-loop-protection.md).
- Execution trail UI (full leg-by-leg history on a ticket).

**Exit criteria:** a ticket can bounce between two or more agents and land correctly, and a deliberately looping test configuration is caught and escalated (overview SC-3, SC-4).

## Phase 5 — Human-AI Collaboration
- Co-assignment (`owner`/`reviewer`/`collaborator` roles), approval gates on transitions — [`human-ai-collaboration.md`](03-components/human-ai-collaboration.md) §2, [`permissions-rbac.md`](03-components/permissions-rbac.md) §4.
- Realtime Service: presence, live takeover/cancel, proposal editing — [`human-ai-collaboration.md`](03-components/human-ai-collaboration.md) §4.
- Slack bi-directional integration (including answering ask-human from Slack) — [`notifications-and-integrations.md`](03-components/notifications-and-integrations.md) §2–3.

**Exit criteria:** a human and an agent can co-work one ticket with visible live status and a working interrupt/override control (overview SC-5).

## Phase 6 — ROI & Analytics
- `RoiBaseline` (historical + manual), `RoiSummary` computation, attribution across legs — [`roi-analytics.md`](03-components/roi-analytics.md), [ADR-0004](adr/0004-roi-attribution-model.md).
- Ticket/sprint/project/portfolio dashboards — §5.
- Marketplace trust-signal feedback loop (edit distance, rejection rate → agent ratings) — [`agent-marketplace.md`](03-components/agent-marketplace.md) §5, [`human-ai-collaboration.md`](03-components/human-ai-collaboration.md) §5.

**Exit criteria:** a completed sprint produces a real $ / hours-saved report a PM would actually show leadership (overview SC-6, SC-7).

## Phase 7 — Enterprise Hardening
- `verified`/`enterprise` certification tiers, security review pipeline — [`agent-marketplace.md`](03-components/agent-marketplace.md) §3.
- Row-level tenant isolation, data residency config, retention policy — [`06-security.md`](06-security.md) §1, §6.
- Metered billing settlement integration (payments provider) — [`agent-marketplace.md`](03-components/agent-marketplace.md) §6.
- GitHub/GitLab integration, email-to-ticket, calendar feed — [`notifications-and-integrations.md`](03-components/notifications-and-integrations.md) §3.
- SSO/IdP.

**Exit criteria:** ready for a regulated-industry customer to onboard.

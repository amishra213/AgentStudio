# Roadmap

> Phased plan. Meridian is a genuinely useful PM and ticketing tool at the end of Phase 1, before
> any agent exists — that ordering is deliberate, since the record plane has to be trustworthy
> before anything automated writes to it.

---

## Phase 0 — Foundations
- Workspace, users, groups, human RBAC roles — [`permissions-rbac.md`](03-components/permissions-rbac.md) §1.
- Ticket entity, ticket types with field schemas and sensitivity.
- Append-only `activity_event` as the single write path — [ADR-0003](adr/0003-event-sourced-ticket-activity.md).

## Phase 1 — Core PM, Ticketing, and Administration *(humans only)*
- **Project creation**, templates, and delegated creation rights — [`project-administration.md`](03-components/project-administration.md) §1.
- **Status definition**: statuses, categories, transitions, versioned shared status schemes, impact preview and migration — §3.
- Workflow Engine: transition validation, approval roles, automations.
- **Tracking configuration**: estimate units, time tracking, required fields, definition of done — §4.
- Delivery modes: waterfall (phases, gates, baseline, critical path), agile (sprints, burndown), kanban — [`delivery-modes.md`](03-components/delivery-modes.md).
- **Timeline** as the primary surface: bars, points, diamonds, bands, swimlanes, dependencies — [`timeline.md`](03-components/timeline.md).
- Operational ticket types (incident, problem, change) with SLA clocks — [`ticketing.md`](03-components/ticketing.md) §1.
- Notifications (in-app + email).

**Exit:** a team runs a real waterfall programme and a real sprint, both on one timeline, with zero agents.

## Phase 2 — Visibility and Access Control
- Ticket visibility levels, `VisibilityRule`s, `TicketGrant`s — [`permissions-rbac.md`](03-components/permissions-rbac.md) §7.
- Field-level sensitivity and redaction.
- Leak-path closure: counts, search, notifications, links, exports, realtime.
- Configuration audit.

**Exit:** a confidential ticket is provably invisible across every surface (SC-13, Flow 8).

## Phase 3 — MCP Foundation
- **Meridian MCP Server**: `tickets.query/get/claim/comment/update_status` — [`04-api-contracts.md`](04-api-contracts.md) §1.
- MCP catalog: manifests, effect classes, versions, pinning; **private registration** — [`mcp-marketplace.md`](03-components/mcp-marketplace.md).
- Agent profiles and `McpGrant`s; `capabilities.list` resolution — [`permissions-rbac.md`](03-components/permissions-rbac.md) §3.
- Harness registration and heartbeat.

**Exit:** an admin enables an MCP server, grants it to a profile, and the profile appears in assignee pickers (SC-4).

## Phase 4 — Harness Execution
- Trigger rules with filter criteria; **scheduled sweeps** — [`agent-harness.md`](03-components/agent-harness.md) §2.
- Claim/lease with atomic CAS and expiry — §4.
- Single-agent execution: complete, reject, **ask-human** with SLA clock.
- OpenHands reference integration.

**Exit:** a scheduled sweep picks up matching tickets and works them unattended (SC-3).

## Phase 5 — Events, Routing, and Handoff
- Event stream (webhook/SSE) alongside schedules — the dual-trigger guarantee.
- Harness-side MCP routing over the resolved grant set — §5.
- Approval-gated tool calls.
- Handoff: context bundles, routing, and all four guardrails — §7, [ADR-0005](adr/0005-handoff-loop-protection.md).
- Execution-trail UI including MCP calls made.

**Exit:** an incident is triaged within seconds of creation and correctly handed off across profiles (SC-6, SC-7).

## Phase 6 — Human-AI Collaboration
- Co-assignment with roles and approval gates — [`human-ai-collaboration.md`](03-components/human-ai-collaboration.md) §2.
- Presence, live takeover, proposal editing with attribution — §4.
- Slack bi-directional, including answering ask-human from Slack.

**Exit:** a human and an agent co-work one ticket with a working interrupt (SC-8).

## Phase 7 — Token, Cost, Efficiency, and ROI
- `usage.report` and `UsageRecord`: tokens, cache, model, price snapshots — [`roi-analytics.md`](03-components/roi-analytics.md) §2.
- Cost split (model / MCP / human) through every rollup — §3.
- `UsageRollup` and `EfficiencyMetric` at ticket → sprint/phase → project → portfolio — §4.
- **Budgets** at every scope with thresholds and `on_breach` enforcement — §7.
- ROI baselines, per-leg attribution, project- and portfolio-level ROI — §5–6.
- Drill-through to harness traces via `harness_step_id`.

**Exit:** a closed sprint and its parent project both produce a defensible $ / hours-saved report (SC-10, SC-11).

## Phase 8 — Enterprise Hardening
- `verified` / `enterprise` MCP certification and security review pipeline.
- Prompt-injection controls: content provenance marking, default-closed grants review — [`06-security.md`](06-security.md) §4.
- Data residency, retention policy, row-level tenant isolation.
- Metered billing settlement; SSO/IdP with group→role mapping.
- GitHub/GitLab, email-to-ticket, calendar feed.

**Exit:** ready for a regulated-industry onboarding.

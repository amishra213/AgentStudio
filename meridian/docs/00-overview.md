# Meridian — Overview

> **Reading order position:** 1 of 9 — read this before any other doc in this tree.

---

## Table of Contents

1. [Project Purpose](#1-project-purpose)
2. [Differentiators](#2-differentiators)
3. [Personas](#3-personas)
4. [Goals](#4-goals)
5. [Non-Goals](#5-non-goals)
6. [Success Criteria](#6-success-criteria)

---

## 1. Project Purpose

Meridian is a work-management system in which **the timeline is the primary surface** and **an
agent harness is a first-class worker**. Projects run as waterfall (phases and gates), agile
(sprints), kanban, or a hybrid of these — all plotted on one timeline. Every unit of work is a
**ticket** — a story, a task, an **incident**, a **problem**, a **change**, a risk, a defect — and
every ticket appears on that timeline with its status expressed visually.

Tickets are worked by humans, by AI agents, or by both together. Agents do not run inside
Meridian. A pluggable **agent harness** (OpenHands or an equivalent MCP-speaking runtime) watches
Meridian for tickets matching configured **filter criteria** — triggered by events, or on a
schedule — and for each one decides **which MCP server to call** from a set of servers the
workspace has enabled and RBAC permits. It does the work through those servers and writes the
outcome back to Meridian through Meridian's own MCP server.

The consequence is that **agent capability is configuration, not code**: enabling a new MCP server
from the marketplace (or registering a private one) immediately widens what the harness can do on
the next sweep, with no Meridian deployment.

---

## 2. Differentiators

These are the specific reasons Meridian exists rather than a Jira configuration.

| # | Differentiator | Where it's specified |
|---|---|---|
| **D1** | **Status is tracked visually on a timeline** — the timeline is the default view, with status encoded in the bar itself, not a secondary roadmap add-on | [`timeline.md`](03-components/timeline.md) |
| **D2** | **Issues, problems, incidents, changes, risks and defects are all tickets on the same timeline** — one data model spanning delivery work and operational work | [`ticketing.md`](03-components/ticketing.md) §1 |
| **D3** | **Tickets are worked by agents, humans, or both** — one assignee model, one activity feed, one execution trail | [`human-ai-collaboration.md`](03-components/human-ai-collaboration.md) |
| **D4** | **The harness runs on events *and* on a schedule** — a status change wakes it immediately; a periodic sweep catches anything an event missed | [`agent-harness.md`](03-components/agent-harness.md) §2 |
| **D5** | **The harness decides which MCP server to call** from the enabled list, and that list is governed by RBAC | [`agent-harness.md`](03-components/agent-harness.md) §5, [`permissions-rbac.md`](03-components/permissions-rbac.md) §3 |
| **D6** | **Waterfall and agile are co-equal**, including hybrid projects where phases contain sprints | [`delivery-modes.md`](03-components/delivery-modes.md), [ADR-0006](adr/0006-unified-waterfall-and-agile.md) |
| **D7** | **New MCP servers are enabled from a marketplace or registered privately**, changing agent capability with no redeploy | [`mcp-marketplace.md`](03-components/mcp-marketplace.md) |

---

## 3. Personas

| Persona | What they do in Meridian |
|---|---|
| **Project Manager** | Owns the timeline; plans phases/gates or sprints; creates and prioritises tickets; monitors ROI; sets budgets. |
| **Architect** | Decomposes epics/phases into tickets; sets technical acceptance criteria; reviews agent output; can override the harness's MCP routing on a ticket. |
| **Consultant / Domain Expert** | Works tickets needing judgement; the usual target when an agent blocks on an ask-human. |
| **Engineer / Contributor** | Works tickets directly, or co-works with an agent (agent drafts, human finishes). |
| **Service Desk / Ops** | Raises and works incidents and problems; relies on event-triggered agent sweeps for first-response automation. |
| **Stakeholder / Viewer** | Read-only timeline, status, and ROI dashboards. |
| **Agent Profile** | A named, assignable AI worker: a harness + model config + a bound set of MCP servers/tools + a budget. Appears in assignee pickers alongside humans. See [`agent-harness.md`](03-components/agent-harness.md) §3. |
| **Workspace Admin** | Enables MCP servers, sets RBAC, manages billing, SSO, and security policy. |

---

## 4. Goals

- **G1 — Timeline as the primary surface.** Every ticket, phase, gate, sprint and milestone is
  plotted on a single timeline with status expressed visually, for both delivery and operational
  work. (D1, D2)

- **G2 — One ticket model for delivery and operations.** Stories, tasks, incidents, problems,
  changes, risks and defects share one entity, one workflow engine, and one timeline — differing
  by type schema and workflow, not by product. (D2)

- **G3 — Both methodologies, first-class.** Waterfall (phases, gates, WBS, baseline vs actual,
  critical path) and agile (sprints, backlog, velocity, burndown) are equally supported, and can
  coexist in one project. (D6)

- **G4 — Agents and humans as peer assignees.** An agent profile is assigned a ticket through the
  same path as a human, and can be co-assigned with one. (D3)

- **G5 — Harness-driven execution on events and schedules.** Ticket state changes emit events the
  harness can subscribe to; independently, the harness sweeps on a configured interval against
  filter criteria (status, type, labels, priority, phase/sprint). Neither path is a fallback for
  the other — both are supported and can be used together. (D4)

- **G6 — MCP as the sole tool substrate.** Every capability an agent can use — including reading
  and updating Meridian itself — is an MCP server. There is no bespoke agent protocol and no
  hard-coded connector. (D5, D7, [ADR-0002](adr/0002-mcp-as-integration-substrate.md))

- **G7 — RBAC over agent capability.** Which MCP servers (and which tools within them) an agent
  profile may call is an access-control decision, enforced server-side, distinct from what the
  marketplace offers or what the harness requests. (D5)

- **G8 — Capability change without redeploy.** Enabling a marketplace MCP server, or registering a
  private one, makes it available to permitted agent profiles on their next run. (D7)

- **G9 — Agent-to-agent and agent-to-human handoff.** An agent that finishes its stage, or lacks
  the capability for what remains, hands the ticket on — subject to loop, budget and time
  guardrails.

- **G10 — Token, cost, efficiency and ROI tracking above the harness.** Tokens (including cache
  reads), model cost, metered MCP cost, and human time accrue per execution leg and roll up
  through ticket → sprint/phase → project → portfolio. Efficiency indicators (cost per ticket,
  first-pass yield, rework rate, cache hit ratio, autonomy mix) and ROI against a baseline are
  computed at each level. Budgets attach at any scope with alert thresholds and enforcement. This
  is deliberately the layer *above* what a harness like OpenHands tracks inside a single run —
  see [`roi-analytics.md`](03-components/roi-analytics.md) §1.

- **G13 — Project creation, status definition and tracking as first-class administration.**
  Projects are provisioned from versioned templates; statuses and transitions are defined in
  reusable, versioned schemes shared across projects; what "tracked" means (estimate unit, time
  tracking, required fields, definition of done, agent eligibility) is per-project configuration.
  Configuration changes are audited and require impact preview before they move live tickets —
  see [`project-administration.md`](03-components/project-administration.md).

- **G14 — Ticket visibility management, separate from role permissions.** Roles answer "what may
  you do"; visibility answers "what may you see". Tickets carry `project` / `restricted` /
  `confidential` levels set automatically by rules rather than manual toggles, with per-field
  sensitivity, explicit time-boxed grants, and enforcement across every indirect surface — counts,
  search, notifications, links, exports, and the agent payload — see
  [`permissions-rbac.md`](03-components/permissions-rbac.md) §7.

- **G11 — Full auditability.** Every status change, assignment, handoff, and **every MCP call the
  harness makes on a ticket's behalf** is an immutable event. Nothing is overwritten.

- **G12 — Multi-tenancy from day one.** Projects, tickets, MCP installations, and cost records are
  scoped to a workspace, including in aggregated marketplace signals.

---

## 5. Non-Goals

- **Not an agent runtime.** Meridian does not execute agent reasoning loops. It defines the
  timeline, the tickets, the permissions, and the MCP surface; a harness such as OpenHands does
  the executing. Meridian ships a reference harness integration, not a proprietary agent
  framework.

- **Not an MCP server host.** The marketplace is a catalog and an enablement/permission layer.
  MCP servers run wherever their publisher or the customer runs them (vendor-hosted, self-hosted
  sidecar, or local stdio next to the harness).

- **Not a source-control or CI system.** Tickets link to PRs, commits and pipelines through MCP
  servers; Meridian hosts neither.

- **Not a general BI tool.** ROI reporting covers work tracked in Meridian; it is not a warehouse
  for arbitrary external metrics.

- **Not a payments processor.** Marketplace usage is metered and reported; settlement runs through
  a third-party provider. Meridian never custodies funds.

- **Not opinionated about methodology.** Waterfall, agile, kanban and hybrid are configuration.
  Meridian does not push a team toward one.

---

## 6. Success Criteria

| ID | Criterion | Measurement | Target |
|----|-----------|-------------|--------|
| SC-1 | Timeline completeness | Every ticket type — including incidents and problems — renders on the project timeline with visually distinguishable status | 100% of types; no type requires a separate view |
| SC-2 | Unified assignment | A ticket is assignable to a human, an agent profile, or both via one API path | 100% of assignee surfaces list both in one picker |
| SC-3 | Dual trigger coverage | A ticket entering a matching status is picked up by an event trigger; a ticket that missed its event is picked up by the next scheduled sweep | Event pickup ≤ 10s; scheduled sweep finds 100% of missed matches |
| SC-4 | MCP enablement latency | Time from enabling an MCP server to a permitted agent profile being able to call it | ≤ 60s, no redeploy (D7) |
| SC-5 | RBAC enforcement | An agent profile attempting a tool on a server it is not permitted for | Denied server-side and logged, 100% of attempts, regardless of harness behaviour |
| SC-6 | Routing quality | % of harness MCP-routing decisions that lead to ticket progress rather than an immediate reject/handoff | ≥ 85% |
| SC-7 | Loop protection | Synthetic circular-handoff configuration | Detected and escalated within the configured hop limit, 100% of the time |
| SC-8 | Ask-human round trip | Agent blocks → human notified → agent resumes | Notify ≤ 5s; resume ≤ 2s after the answer posts |
| SC-9 | Methodology coexistence | One project running phases with sprints inside them, plus a pure-waterfall and a pure-agile project in the same workspace | Config-only; shared timeline renders all three |
| SC-10 | ROI completeness | Every agent-touched ticket has a computed cost and cycle time at completion | 100%, or an explicit `cost_unavailable` flag with reason |
| SC-11 | Attribution accuracy | Multi-leg ticket cost apportioned per leg | Sum of attributed cost equals total, ±0.5% |
| SC-12 | Audit completeness | Every ticket mutation, MCP call, and configuration change produces an immutable event | 100%, verified by contract test on the write path |
| SC-13 | Multi-tenant isolation | No cross-tenant ticket, MCP-call, or cost data reachable via API, UI, or marketplace aggregates | Zero leakage in the tenancy test suite |
| SC-14 | Visibility enforcement | A `confidential` ticket is absent from lists, boards, timelines, search, counts, rollups, notifications, exports, and agent payloads for non-grantees | Zero disclosures across all surfaces in the visibility test suite |
| SC-15 | Token/cost attribution | Sum of `UsageRecord` cost + MCP call cost + human time equals the ticket's `total_cost`, and ticket totals sum to the project rollup | Reconciles ±0.5% (rounding only) |
| SC-16 | Budget enforcement | A scope reaching its ceiling with `on_breach: block_agent_dispatch` | No new agent run starts; humans unaffected; breach attributable to scope and tickets, ≥ 99% of runs |
| SC-17 | Project provisioning | Creating a project from a template yields workflows, roles, visibility rules, MCP scope, budget and baseline with no manual follow-up | ≤ 1 creation call; zero post-creation configuration steps required |
| SC-18 | Safe workflow change | Removing a status that live tickets occupy | Blocked without a migration map; with one, all affected tickets move in one transaction, each emitting a `status_changed` event |

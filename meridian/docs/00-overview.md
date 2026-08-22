# Meridian — Overview

> **Reading order position:** 1 of 9 — read this before any other doc in this tree.

---

## Table of Contents

1. [Project Purpose](#1-project-purpose)
2. [Personas](#2-personas)
3. [Goals](#3-goals)
4. [Non-Goals](#4-non-goals)
5. [Success Criteria](#5-success-criteria)

---

## 1. Project Purpose

Meridian is a project and ticket management system in which the pool of "people" who can be
assigned work includes both humans and AI agents drawn from an open marketplace. A project is
represented as a **timeline** — optionally divided into **sprints** — populated with **tickets**
that move through a customizable status workflow. Any ticket can be assigned to a human, to an
installed agent, or to both at once. Agents complete tickets directly, ask a human for input when
blocked, or **hand off** the ticket to a different agent better suited to what's left — and every
step of that chain is recorded so the organization can see exactly who (or what) did the work, how
long it took, what it cost, and what it would have cost without AI involvement.

Meridian is deliberately **one system, not three integrated ones**: the project timeline, the
ticket tracker, and the agent execution log all read and write the same ticket record, so there is
never a sync problem between "the PM tool" and "the agent tool" — there is only one tool.

---

## 2. Personas

| Persona | What they do in Meridian |
|---|---|
| **Project Manager (PM)** | Owns the timeline and sprint plan; creates and prioritizes tickets; sets acceptance criteria; monitors ROI dashboards; approves agent installs and budgets for their project. |
| **Architect** | Breaks down epics into tasks; defines technical acceptance criteria; reviews agent-produced designs/code before merge; can override agent handoff routing. |
| **Consultant / Domain Expert** | Assigned tickets requiring specialized judgment; frequently the "ask-human" target when an agent is blocked on domain knowledge. |
| **Engineer / Contributor** | Works tickets directly, or co-works them with an assigned agent (agent drafts, human finishes). |
| **Stakeholder / Viewer** | Read-only access to timeline, ticket status, and ROI dashboards. No assignment or edit rights. |
| **Agent (marketplace)** | A configured, installed agent instance. Appears in assignee pickers exactly like a human. Has a permission scope, a budget, and a capability manifest (see [`agent-marketplace.md`](03-components/agent-marketplace.md)). |
| **Workspace Admin** | Manages org-level settings: billing, marketplace install approvals, RBAC roles, security policy. |

---

## 3. Goals

- **G1 — Unified timeline + ticketing.** One system for both Gantt-style project timelines
  (milestones, dependencies, cross-project rollups) and Kanban/Scrum-style ticket tracking
  (backlog, sprints, board views), so PMs stop reconciling two tools.

- **G2 — Agents as first-class assignees.** An agent installed from the marketplace can be
  assigned a ticket through the exact same UI/API path as assigning a human. No "AI mode" toggle;
  agents are peers in the assignee list.

- **G3 — Open agent marketplace.** Anyone can publish an agent that conforms to the
  [Agent Protocol](03-components/agent-execution-and-handoff.md); workspaces install agents like
  they'd install a Slack app, with declared capabilities, required tool access, and pricing.

- **G4 — Agent-to-agent handoff.** An agent that determines a ticket needs different expertise
  (or has finished its part of a multi-stage task) can hand the ticket to another installed agent
  without human intervention, subject to loop protection and budget ceilings.

- **G5 — First-class human-AI collaboration.** Humans and agents can be co-assigned to the same
  ticket, see the same activity feed, and hand work back and forth mid-ticket. An agent can block
  and ask a human a question at any point ("ask-human"); a human can steer, override, or take over
  an in-flight agent run at any point.

- **G6 — ROI and benefit measurement built in, not bolted on.** Every ticket accrues cost (agent
  run cost + human hours × rate) and cycle time automatically. The system computes ROI against a
  baseline (historical human-only velocity or a manual estimate) at the ticket, sprint, and
  portfolio level, without a separate BI project.

- **G7 — Full auditability.** Every status change, assignment, handoff, comment, and agent action
  is an immutable event on the ticket's activity log. Nothing is overwritten; corrections are new
  events.

- **G8 — Configurable workflow.** Ticket types and status graphs (the workflow) are configured per
  project, not hardcoded — a support-ticket project and a software-delivery project can have
  entirely different states and transitions inside the same Meridian instance.

- **G9 — Multi-tenancy from day one.** Every project, ticket, agent installation, and cost record
  is scoped to a workspace/tenant. No cross-tenant data is ever visible, including in aggregated
  marketplace ratings.

---

## 4. Non-Goals

- **Not a replacement for a full agent development framework.** Meridian does not tell you how to
  build an agent's internal reasoning loop. It defines the **contract** an agent must speak
  (the Agent Protocol) to participate in the marketplace — what the agent does inside its own
  process, with its own tools and its own LLM provider, is out of scope. (An organization building
  Meridian-compatible agents may well use something like a Claude Agent SDK–based runtime
  internally — that is an implementation choice for the agent author, not part of Meridian itself.)

- **Not a source-control or CI system.** Meridian tickets can *link* to PRs, commits, and CI runs
  via integrations, but Meridian does not host git repositories or run pipelines itself.

- **Not a general-purpose BI tool.** ROI/benefit dashboards are scoped to work tracked inside
  Meridian. It is not a data warehouse and does not ingest arbitrary external metrics.

- **Not a payments processor.** Marketplace billing is metered and reported by Meridian, but
  settlement runs through a third-party payments provider (e.g., Stripe Connect) — Meridian never
  holds funds.

- **Not opinionated about methodology.** Meridian supports Scrum (sprints), Kanban (continuous
  flow, no sprints), and pure Gantt/timeline-only projects as first-class, equally-supported modes
  — it does not force one methodology.

---

## 5. Success Criteria

| ID | Criterion | Measurement method | Target |
|----|-----------|--------------------|--------|
| SC-1 | Unified assignment | A ticket can be assigned to a human, an agent, or both, via one API/UI path with no special-casing | 100% of assignee-picker surfaces list agents and humans in one list |
| SC-2 | Agent onboarding time | Time from "publish agent manifest" to "assignable in a workspace that installs it" | ≤ 5 minutes, no Meridian redeploy |
| SC-3 | Handoff success rate | % of agent-initiated handoffs that land on an agent/human able to make progress (not immediately re-handed-off or rejected) | ≥ 85% |
| SC-4 | Handoff loop protection | Synthetic test that creates a circular handoff configuration | System detects the cycle and escalates to a human within the configured hop limit, 100% of the time |
| SC-5 | Ask-human round trip | From an agent emitting an ask-human block to the agent resuming after a human answers | Notification delivered ≤ 5s; agent resumes ≤ 2s after the answer is posted |
| SC-6 | ROI data completeness | Every ticket touched by ≥ 1 agent has a computed cost and cycle-time record at completion | 100% of agent-touched tickets, or an explicit `cost_unavailable` flag with reason |
| SC-7 | ROI attribution accuracy | On a ticket with N handoff legs across humans and agents, cost/time is apportioned per leg | Sum of per-leg attributed cost equals total ticket cost, ±0.5% (rounding only) |
| SC-8 | Workflow configurability | Two projects in the same workspace run different ticket types and status graphs with no code change | Verified via config-only project setup |
| SC-9 | Multi-tenant isolation | No cross-tenant ticket, agent-run, or cost data visible via API, UI, or marketplace aggregate ratings | Zero leakage events in automated tenancy test suite |
| SC-10 | Audit completeness | Every mutation to a ticket produces a corresponding immutable activity event | 100% event coverage verified by contract test on the ticket write path |

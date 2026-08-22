# Security

> Cross-cutting concerns referenced from [`permissions-rbac.md`](03-components/permissions-rbac.md)
> and [`agent-execution-and-handoff.md`](03-components/agent-execution-and-handoff.md).

---

## 1. Multi-Tenancy

Every row in every table introduced in [`02-data-model.md`](02-data-model.md) carries (directly or
via its parent) a `workspace_id`. Enforcement is defense-in-depth:

- **Query layer**: every data-access function requires an explicit tenant context; there is no
  "query all tickets" code path without a workspace filter.
- **Row-level security** at the database (Postgres RLS or equivalent) as a second, independent
  enforcement layer, so an application bug cannot alone cause cross-tenant leakage.
- **Marketplace aggregates** (ratings, benchmarking signals in
  [`agent-marketplace.md`](03-components/agent-marketplace.md) §5) are computed by an offline
  aggregation job that reads per-tenant data but writes only de-identified, aggregated output —
  the live query path never joins across tenants.

---

## 2. Agent Sandboxing and Scope Enforcement

Covered in depth in [`permissions-rbac.md`](03-components/permissions-rbac.md) §2–3; the security
summary:

- Agents are external processes; Meridian never executes agent code in-process.
- Agents never receive a database credential or a general-purpose API token — only scoped,
  short-lived tokens tied to one `run_id` and one `AgentInstallation.permission_scope`.
- A run's token is invalidated the moment the run reaches a terminal state (`completed`,
  `handoff`, `rejected`, `timed_out`) — a delayed or replayed callback with an expired token is
  rejected.
- Outbound dispatch calls to agent `endpoint_url`s are made from an egress path that enforces
  per-installation rate limits, so a misbehaving or compromised agent installation cannot be used
  to amplify traffic elsewhere.

---

## 3. Webhook Authentication

Every callback from an agent (`run-completed`, `run-blocked`, `run-handoff`, `run-rejected`) is
HMAC-signed using the `webhook_secret` generated at install time and rotatable by the workspace
admin without reinstalling. The Orchestrator verifies the signature and a timestamp freshness
window before processing — an unsigned, mis-signed, or stale-timestamped callback is dropped and
logged, never applied to ticket state (referenced in
[`04-api-contracts.md`](04-api-contracts.md) §3).

---

## 4. Secrets

- Agent-side secrets (the workspace's credentials for calling a specific paid agent, if any) and
  Meridian-side secrets (`webhook_secret` per installation, SSO client secrets, payments provider
  keys) are held in a secrets backend, never in plaintext config or in the database in cleartext.
- Ticket field data flagged sensitive (e.g., a `contract_value` field marked confidential at the
  ticket-type schema level) is excluded from agent payloads by default even if the installation's
  `permission_scope` would otherwise allow the field — an explicit second flag is required to
  include genuinely sensitive fields in what leaves Meridian's boundary to an external agent
  process.

---

## 5. Audit

- The `activity_event` table (see [ADR-0003](adr/0003-event-sourced-ticket-activity.md)) is
  append-only at the database level (no `UPDATE`/`DELETE` grants on that table for the application
  role) — corrections are new events, never edits to history.
- Every RBAC-gated action, every agent dispatch, every handoff routing decision, and every
  budget/loop-protection trip (per
  [`agent-execution-and-handoff.md`](03-components/agent-execution-and-handoff.md) §5) is logged
  with enough detail to reconstruct *why* a decision was made, not just *what* happened — this is
  what makes a handoff-loop escalation (Flow 3 in
  [`05-sequence-flows.md`](05-sequence-flows.md)) explainable to a human after the fact.

---

## 6. Data Residency and Retention

- Workspace-level configuration can pin data residency (which region a workspace's data and
  agent-dispatch egress originate from) for regulated customers.
- Retention of `ActivityEvent`, `ExecutionLeg`, and `CostEntry` is configurable per workspace plan
  tier, with a minimum floor sufficient to support the ROI reporting windows described in
  [`roi-analytics.md`](03-components/roi-analytics.md) — deleting history early enough to break a
  quarter's ROI rollup is not permitted regardless of plan tier.

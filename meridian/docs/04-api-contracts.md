# API & Protocol Contracts

> Four surfaces: the **Meridian MCP Server** (what the harness calls), the **event stream** (what
> wakes it), the **REST API** (humans and admin), and the **realtime channel** (live UI).

---

## 1. The Meridian MCP Server

This is the harness's entire interface to Meridian. Exposed over streamable HTTP; authenticated
per agent profile. Every tool is subject to RBAC, ticket visibility, and workflow validation
server-side ([`permissions-rbac.md`](03-components/permissions-rbac.md)).

### Discovery and work acquisition

| Tool | Purpose |
|---|---|
| `tickets.query` | Fetch tickets matching filter criteria (`ticket_types`, `statuses`, `labels`, `priorities`, `severities`, `phase_ids`, `sprint_ids`, `unassigned_only`, `claimable_only`). Returns only tickets the calling profile may see |
| `tickets.get` | Full payload for one ticket, field-filtered by the profile's scope and field sensitivity |
| `tickets.claim` | Atomic claim; returns `{lease_token, leased_until}` or fails if already leased |
| `tickets.renew_claim` | Extend the lease during long work |
| `tickets.release_claim` | Release without a terminal outcome |

### Capability discovery

| Tool | Purpose |
|---|---|
| `capabilities.list` | **The resolved MCP grant set for this profile and ticket** — servers, tools, schemas, `capability_tags`, health, and which tools are approval-gated. Ungranted servers are absent, not marked forbidden |

This is the call that makes D5 work: the harness reasons over what this returns to choose where to
route, and cannot see or request anything outside it.

### Progress and outcomes

| Tool | Purpose |
|---|---|
| `tickets.comment` | Post a `note` / `proposal` comment |
| `tickets.update_status` | Request a transition — validated by the Workflow Engine, rejected if illegal or approval-gated |
| `tickets.update_fields` | Patch fields the profile may write |
| `tickets.complete` | Attach artifacts, close the leg as `completed` |
| `tickets.ask_human` | Post a question, move to a blocked state, start the SLA clock; **leg stays open** |
| `tickets.handoff` | Close the leg, create a `HandoffEvent` with a `context_bundle` |
| `tickets.reject` | Close the leg as `rejected` with a reason |
| `usage.report` | Submit `UsageRecord` rows (tokens, cache, model, `harness_step_id`) and MCP call costs for the leg |

### Contract notes

- Every mutating tool requires the `lease_token` from `claim`; a stale token is rejected, so a
  resumed harness cannot clobber a reassigned ticket.
- Every call carries an idempotency key; retries never double-apply an artifact or double-charge a
  cost entry.
- Tool errors are typed (`not_permitted`, `invalid_transition`, `lease_lost`, `budget_exceeded`,
  `not_visible`) so the harness can react correctly instead of guessing from a message string.

---

## 2. The Event Stream

Meridian pushes to registered harnesses when a `TriggerRule` matches. Transport is per
`HarnessRegistration.event_transport`: `webhook`, `sse`, or `poll_only` (no push at all).

```json
{
  "event": "ticket.matched_rule",
  "rule_id": "…", "rule_name": "Auto-triage P1 incidents",
  "ticket_id": "…", "ticket_key": "OPS-142",
  "agent_profile_id": "…",
  "occurred_at": "2026-08-22T02:14:03Z"
}
```

Deliberately **thin** — an identifier and a reason, not the ticket. The harness calls
`tickets.get` to fetch content, so payload filtering and visibility checks happen at read time
against current state, and an event sitting in a retry queue can never deliver stale or
since-restricted data.

Other events: `ticket.answer_posted` (resume a blocked run), `ticket.claim_revoked`,
`run.cancel_requested` (human takeover), `budget.threshold_crossed`.

Webhook deliveries are HMAC-signed with the registration's shared secret and carry a timestamp
freshness window.

---

## 3. Harness Registration

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/harnesses` | Register: name, kind, `callback_url`, `event_transport` |
| `POST` | `/v1/harnesses/{id}/heartbeat` | Liveness; missed heartbeats release leases in bulk |
| `GET` | `/v1/harnesses/{id}/profiles` | Agent profiles bound to this harness |

Credentials are issued per **agent profile**, not per harness, so one harness backing several
profiles cannot use one profile's grants while acting as another.

---

## 4. REST API (humans and admin)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/projects` | Create project (template, delivery mode, status scheme, budget, visibility defaults) |
| `POST` | `/v1/projects/{id}/phases` \| `/sprints` \| `/gates` | Planning containers |
| `POST` | `/v1/gates/{id}/decision` | Approve / reject / waive |
| `GET` | `/v1/projects/{id}/timeline?from=&to=&group_by=` | Server-aggregated timeline data |
| `POST` | `/v1/tickets` · `PATCH` `/v1/tickets/{id}` | Ticket CRUD |
| `POST` | `/v1/tickets/{id}/assign` | `{assignee_type, assignee_id, role}` — one path for human or agent profile |
| `PUT` | `/v1/tickets/{id}/visibility` · `POST` `/grants` | Visibility level and explicit shares |
| `GET` | `/v1/tickets/{id}/execution-trail` | Legs, handoffs, and MCP calls made |
| **Admin** | | |
| `POST` | `/v1/status-schemes` · `POST` `/{id}/versions` | Define and version status schemes |
| `POST` | `/v1/status-schemes/{id}/impact-preview` | Which tickets a proposed change would move |
| `POST` | `/v1/ticket-types` | Field schemas, sensitivity, SLA, agent I/O contract |
| `POST` | `/v1/projects/{id}/visibility-rules` · `/trigger-rules` | Automation and confidentiality policy |
| `POST` | `/v1/mcp/installations` · `/v1/mcp/private-registrations` | Enable marketplace or private MCP servers |
| `POST` | `/v1/agent-profiles` · `/{id}/grants` | Define profiles and grant MCP tools |
| `POST` | `/v1/budgets` | Budgets at any scope |
| **Analytics** | | |
| `GET` | `/v1/analytics/usage?scope_type=&scope_id=&from=&to=` | Token and cost rollups |
| `GET` | `/v1/analytics/efficiency?scope_type=&scope_id=` | Efficiency metrics |
| `GET` | `/v1/analytics/roi?scope_type=project\|sprint\|phase\|portfolio` | ROI rollups |

All reads apply the visibility predicate; all writes apply RBAC before the Workflow Engine sees
the request.

---

## 5. Realtime Channel

WebSocket subscriptions to `ticket:{id}`, `timeline:{project_id}`, `board:{project_id}`,
`presence:{project_id}`. Carries persisted `ActivityEvent`s plus ephemeral presence
(`presence.agent_running`, `presence.mcp_call` — "calling `itsm.search_similar`") that is not
written to ticket history.

Clients apply events by sequence, not arrival order, so out-of-order fan-out never renders a stale
status over a newer one. Subscriptions are visibility-filtered at the server: a client is never
sent an event for a ticket it may not see.

# Meridian — Data Model

> **Reading order position:** 3 of 9. Builds on [`01-architecture.md`](01-architecture.md).
> Every other doc refers back to the entities defined here.

---

## 1. Entity Overview

```mermaid
erDiagram
    WORKSPACE ||--o{ PROJECT : contains
    WORKSPACE ||--o{ USER : has
    WORKSPACE ||--o{ MCP_INSTALLATION : enables
    WORKSPACE ||--o{ AGENT_PROFILE : defines
    WORKSPACE ||--o{ HARNESS_REGISTRATION : registers

    PROJECT ||--o{ PHASE : waterfall
    PROJECT ||--o{ SPRINT : agile
    PROJECT ||--o{ TICKET : contains
    PROJECT ||--o{ TRIGGER_RULE : automates
    PHASE ||--o{ GATE : ends_with
    PHASE ||--o{ SPRINT : may_contain
    PHASE ||--o{ TICKET : scopes
    SPRINT ||--o{ TICKET : scopes

    TICKET_TYPE ||--|| WORKFLOW : uses
    WORKFLOW ||--o{ STATUS : defines
    TICKET }o--|| TICKET_TYPE : of
    TICKET }o--|| STATUS : currently
    TICKET ||--o{ TICKET_LINK : links
    TICKET ||--o{ ACTIVITY_EVENT : logs
    TICKET ||--o{ ASSIGNMENT : has
    TICKET ||--o{ COMMENT : has
    TICKET ||--o{ EXECUTION_LEG : worked_by

    ASSIGNMENT }o--|| USER : human
    ASSIGNMENT }o--|| AGENT_PROFILE : agent

    AGENT_PROFILE }o--|| HARNESS_REGISTRATION : runs_on
    AGENT_PROFILE ||--o{ MCP_GRANT : permitted
    MCP_GRANT }o--|| MCP_INSTALLATION : to
    MCP_INSTALLATION }o--|| MCP_LISTING : instance_of
    MCP_LISTING ||--o{ MCP_VERSION : has

    EXECUTION_LEG ||--o{ MCP_CALL_RECORD : made
    EXECUTION_LEG ||--o{ COST_ENTRY : accrues
    EXECUTION_LEG ||--o{ HANDOFF_EVENT : ends_in
    MCP_CALL_RECORD }o--|| MCP_INSTALLATION : against
    TICKET ||--|| ROI_SUMMARY : rolls_up_to
```

---

## 2. Planning Entities

### Workspace
Tenancy boundary. Everything below belongs to exactly one.

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | uuid, string | |
| `plan` | enum | `free`, `team`, `enterprise` — gates MCP certification tiers, retention, agent count |
| `default_currency` | string | ROI rollups |

### Project
| Field | Type | Notes |
|---|---|---|
| `id`, `workspace_id`, `name`, `key` | | `key` prefixes ticket keys, e.g. `OPS` → `OPS-142` |
| `delivery_mode` | enum | `waterfall`, `agile`, `kanban`, `hybrid` — see [`delivery-modes.md`](03-components/delivery-modes.md) |
| `template_id` | uuid, nullable | `ProjectTemplate` this project was created from |
| `status_scheme_id` | uuid | the reusable status/workflow scheme in force — see [`project-administration.md`](03-components/project-administration.md) §3 |
| `default_ticket_visibility` | enum | `project`, `restricted`, `confidential` — the default applied to new tickets |
| `baseline_locked_at` | timestamp, nullable | waterfall/hybrid: when the schedule baseline was frozen |
| `roi_baseline_id` | uuid, nullable | |
| `budget_id` | uuid, nullable | project-level cost ceiling and alert thresholds |

### ProjectTemplate
A reusable bundle that makes project creation a one-step act rather than a week of configuration.

| Field | Type | Notes |
|---|---|---|
| `id`, `workspace_id`, `name`, `description` | | |
| `delivery_mode` | enum | preset mode |
| `ticket_type_ids`, `status_scheme_id` | uuid[] , uuid | types and workflows to install |
| `phase_blueprint` / `sprint_cadence` | jsonb | starter phases + gates, or sprint length/cadence |
| `trigger_rule_blueprints` | jsonb | starter automation rules, agent profiles referenced by tag |
| `role_seed` | jsonb | which workspace groups get which project roles on creation |
| `mcp_scope_seed` | uuid[] | MCP installations pre-scoped to projects from this template |
| `budget_defaults`, `roi_baseline_defaults` | jsonb | |
| `visibility_rule_blueprints` | jsonb | default ticket visibility policy per type |

### StatusScheme
A named, versioned, **reusable** set of statuses and transitions, shared across projects so
governance is defined once. See [`project-administration.md`](03-components/project-administration.md) §3.

| Field | Type | Notes |
|---|---|---|
| `id`, `workspace_id`, `name`, `version` | | schemes are versioned; projects pin a version |
| `workflows` | Workflow[] | one per ticket type |
| `is_shared` | bool | shared schemes are edited centrally; a project may fork to a local copy |
| `locked_by_policy` | bool | prevents project-level divergence where compliance requires uniform states |

### Budget
Attachable at workspace, project, phase, or sprint level. Enforced before agent dispatch and on
each cost report; see [`roi-analytics.md`](03-components/roi-analytics.md) §7.

| Field | Type | Notes |
|---|---|---|
| `id`, `scope_type`, `scope_id` | | `workspace` \| `project` \| `phase` \| `sprint` |
| `period` | enum | `total`, `monthly`, `per_sprint` |
| `amount` | Money | ceiling |
| `token_ceiling` | number, nullable | optional hard cap on tokens independent of money |
| `alert_thresholds` | number[] | e.g. `[0.5, 0.8, 0.95]` — notify at these fractions |
| `on_breach` | enum | `warn`, `block_agent_dispatch`, `block_all_agent_work` |

### Phase *(waterfall / hybrid)*
| Field | Type | Notes |
|---|---|---|
| `id`, `project_id`, `name` | | e.g. Discovery, Design, Build, UAT, Cutover |
| `sequence` | integer | phase order |
| `planned_start`, `planned_end` | date | the **baseline** once locked |
| `actual_start`, `actual_end` | date, nullable | drives baseline-vs-actual variance on the timeline |
| `predecessor_phase_ids` | uuid[] | supports finish-to-start etc. |
| `percent_complete` | number | rolled up from child tickets |

### Gate *(waterfall / hybrid)*
A phase-exit checkpoint. Unlike a milestone, a gate can **block** progression.

| Field | Type | Notes |
|---|---|---|
| `id`, `phase_id`, `name` | | e.g. "Design Sign-off" |
| `criteria` | Criterion[] | `{description, satisfied_by_ticket_id?, satisfied}` |
| `approver_role` | enum | which RBAC role must approve |
| `status` | enum | `pending`, `approved`, `rejected`, `waived` |
| `blocks_phase_ids` | uuid[] | phases that cannot start until this gate is approved |

### Sprint *(agile / hybrid)*
| Field | Type | Notes |
|---|---|---|
| `id`, `project_id`, `name`, `goal` | | |
| `phase_id` | uuid, nullable | **non-null in hybrid projects** — a sprint inside a phase |
| `starts_at`, `ends_at` | timestamp | |
| `status` | enum | `planned`, `active`, `completed` |
| `capacity` | Capacity | `{human_hours, agent_budget}` — agent throughput is bounded by budget, not hours |

### Milestone
Lightweight date marker (`{name, target_date, ticket_ids[]}`) usable in any delivery mode. Unlike a
Gate it is informational — it never blocks.

---

## 3. Ticket Entities

### TicketType
Configuration, not code — this is what lets delivery and operational work share one system (D2).

| Field | Type | Notes |
|---|---|---|
| `id`, `workspace_id`, `name` | | `epic`, `story`, `task`, `defect`, `incident`, `problem`, `change`, `risk`, or custom |
| `category` | enum | `delivery`, `operational`, `governance` — drives default timeline rendering |
| `field_schema` | jsonb | e.g. `incident` adds `severity`, `detected_at`, `service`; `change` adds `change_window`, `rollback_plan`. Each field may declare `sensitivity: normal \| restricted \| secret`, driving per-field redaction and exclusion from agent payloads |
| `workflow_id` | uuid | the status graph for this type |
| `timeline_render` | enum | `bar` (has duration), `point` (instantaneous, e.g. incident), `diamond` (milestone/gate) |
| `agent_io_contract` | jsonb | the input shape an agent receives and output it must return for this type |
| `sla_policy` | jsonb, nullable | response/resolution targets, used by `incident`/`change` |

### Workflow / Status
| Field | Type | Notes |
|---|---|---|
| `Workflow.id`, `.ticket_type_id` | | one graph per type per project override |
| `Status.name` | string | project-defined, e.g. `Triaged`, `Awaiting CAB`, `In Review` |
| `Status.category` | enum | `not_started`, `active`, `blocked`, `done`, `cancelled` — fixed set, so cross-project rollups and timeline colouring work regardless of custom names |
| `Status.transitions_to` | uuid[] | allowed next states |
| `Status.approval_role` | enum, nullable | transition requires this role's approval (used for gate-like control on individual tickets) |
| `Status.automations` | Automation[] | `on_enter`/`on_exit` actions from a fixed vocabulary |

### Ticket
| Field | Type | Notes |
|---|---|---|
| `id`, `project_id`, `key` | | |
| `ticket_type_id`, `status_id` | uuid | |
| `phase_id`, `sprint_id` | uuid, nullable | a ticket can sit in a phase, a sprint, both (hybrid), or neither (backlog) |
| `title`, `description`, `acceptance_criteria` | text/markdown | |
| `fields` | jsonb | validated against the type's `field_schema` |
| `priority`, `severity` | enum | severity used by operational types |
| `estimate` | number + unit | points or hours per project config |
| `planned_start`, `due_date` | date, nullable | drives timeline placement for `bar`-rendered types |
| `labels` | string[] | |
| `parent_id` | uuid, nullable | epic → story → task, or phase-level WBS nesting |
| `current_assignments` | Assignment[] | up to one human + one agent (co-assignment) |
| `claim` | Claim, nullable | `{harness_id, agent_profile_id, leased_until}` — see [`agent-harness.md`](03-components/agent-harness.md) §4 |
| `visibility` | enum | `project` (all project members), `restricted` (members + explicit grants), `confidential` (explicit grants only) — see [`permissions-rbac.md`](03-components/permissions-rbac.md) §7 |
| `visibility_reason` | string, nullable | why it's restricted — surfaced to those who *can* see it, for audit |

### VisibilityRule
Project-level policy that sets a ticket's visibility automatically at creation or on field change,
so confidentiality does not depend on someone remembering to click a toggle.

| Field | Type | Notes |
|---|---|---|
| `id`, `project_id`, `name`, `enabled` | | |
| `match` | jsonb | `{ticket_types[], labels[], severities[], field_predicates[]}` |
| `set_visibility` | enum | `project` \| `restricted` \| `confidential` |
| `grant_to` | jsonb | `{roles[], groups[], users[], agent_profiles[]}` automatically granted when the rule fires |
| `precedence` | integer | first match wins; a rule can never *widen* visibility set by a higher-precedence rule |

### TicketGrant
An explicit share of one restricted/confidential ticket.

| Field | Type | Notes |
|---|---|---|
| `ticket_id`, `grantee_type`, `grantee_id` | | `user` \| `group` \| `role` \| `agent_profile` |
| `access` | enum | `view`, `comment`, `work` |
| `granted_by`, `granted_at`, `expires_at` | | time-boxed shares are supported and preferred for external reviewers |

### TicketLink
| Field | Type | Notes |
|---|---|---|
| `from_ticket_id`, `to_ticket_id`, `relation` | | `blocks`, `blocked_by`, `relates_to`, `duplicates`, `caused_by`, `resolved_by`, `implements` |

`caused_by` and `resolved_by` carry the ITSM semantics: several `incident` tickets `caused_by` one
`problem`; a `problem` `resolved_by` a `change`.

### Assignment
*Who is currently responsible* — distinct from ExecutionLeg (*who actually did work*).

| Field | Type | Notes |
|---|---|---|
| `ticket_id`, `assignee_type` | | `human` \| `agent` |
| `user_id` / `agent_profile_id` | uuid | |
| `role` | enum | `owner`, `reviewer`, `collaborator` |
| `assigned_at`, `unassigned_at` | timestamp | |

### Comment
| Field | Type | Notes |
|---|---|---|
| `ticket_id`, `author_type`, `author_id` | | author may be a human, an agent profile, or `system` |
| `kind` | enum | `note`, `question` (ask-human), `proposal`, `answer`, `system` |
| `body` | markdown | |

### ActivityEvent *(append-only — [ADR-0003](adr/0003-event-sourced-ticket-activity.md))*
| Field | Type | Notes |
|---|---|---|
| `ticket_id`, `type` | | `created`, `status_changed`, `assigned`, `commented`, `claimed`, `handoff`, `blocked`, `linked`, `field_changed`, `gate_decided` |
| `actor_type`, `actor_id` | | `human` \| `agent` \| `system` |
| `payload` | jsonb | type-specific |
| `occurred_at` | timestamp | immutable |

---

## 4. Agent, Harness & MCP Entities

### McpListing / McpVersion *(marketplace catalog)*
| Field | Type | Notes |
|---|---|---|
| `McpListing.id`, `.publisher_id`, `.name` | | |
| `.capability_tags` | string[] | `["itsm","incident"]`, `["git","code-review"]` — the harness routes on these |
| `.certification_tier` | enum | `unverified`, `community`, `verified`, `enterprise` |
| `.source` | enum | `marketplace`, `private` — private servers are registered directly, never listed publicly (D7's "or otherwise") |
| `McpVersion.semver`, `.manifest` | | manifest declares tools, their schemas, required secrets, transport |
| `McpVersion.transport` | enum | `stdio`, `streamable_http`, `sse` |
| `McpVersion.endpoint` | string, nullable | for HTTP transports |

### McpInstallation *(this server, enabled in this workspace)*
| Field | Type | Notes |
|---|---|---|
| `id`, `workspace_id`, `mcp_version_id` | | version is **pinned**; upgrades are explicit |
| `display_name` | string | |
| `project_scope` | uuid[] | which projects it may be used in (empty = all) |
| `secret_refs` | jsonb | names resolved from the secrets backend at call time, never stored inline |
| `health` | enum | `healthy`, `degraded`, `unreachable` |
| `status` | enum | `enabled`, `paused`, `revoked` |

### HarnessRegistration
| Field | Type | Notes |
|---|---|---|
| `id`, `workspace_id`, `name` | | e.g. "OpenHands prod" |
| `kind` | string | `openhands`, `claude-agent-sdk`, `custom` — informational; the contract is identical |
| `callback_url` | string, nullable | for event-driven push; null = poll-only harness |
| `event_transport` | enum | `webhook`, `sse`, `poll_only` |
| `shared_secret_ref` | string | for signing event deliveries |
| `heartbeat_at` | timestamp | a harness that stops heartbeating is marked stale and its leases are released |

### AgentProfile
**This is what appears in the assignee picker.** It binds a harness, a model configuration, a
prompt/policy, and a permitted MCP surface into one named, assignable worker.

| Field | Type | Notes |
|---|---|---|
| `id`, `workspace_id`, `display_name` | | e.g. "Incident First Responder" |
| `harness_registration_id` | uuid | where it runs |
| `model_config` | jsonb | provider/model/params — opaque to Meridian, passed to the harness |
| `system_policy` | text | the profile's standing instructions |
| `capability_tags` | string[] | used for auto-assignment in TriggerRules |
| `accepts_ticket_types` | uuid[] | |
| `budget` | Budget | `{per_run, per_day, per_ticket}` ceilings enforced before dispatch and on each cost report |
| `max_hops` | integer | handoff hop ceiling for tickets this profile starts |
| `status` | enum | `active`, `paused` |

### McpGrant
The RBAC join that answers "may this agent profile call this server, and which of its tools?"

| Field | Type | Notes |
|---|---|---|
| `agent_profile_id`, `mcp_installation_id` | uuid | |
| `tool_allowlist` | string[] | empty = all tools in the manifest; otherwise an explicit subset |
| `requires_approval` | string[] | tools that trigger a human approval gate before execution |
| `granted_by`, `granted_at` | | |

A profile can only ever call servers it holds a grant for — see
[`permissions-rbac.md`](03-components/permissions-rbac.md) §3.

### TriggerRule
The filter criteria that make a ticket eligible for agent pickup (D4).

| Field | Type | Notes |
|---|---|---|
| `id`, `project_id`, `name`, `enabled` | | |
| `filter` | jsonb | `{ticket_types[], statuses[], labels[], priorities[], severities[], phase_ids[], sprint_ids[], unassigned_only}` |
| `mode` | enum | `event`, `scheduled`, `both` |
| `schedule` | cron, nullable | for `scheduled`/`both` |
| `agent_profile_id` | uuid, nullable | profile to assign; null = use the ticket's existing agent assignment only |
| `max_concurrent` | integer | throttle on how many tickets this rule may have in flight |

### ExecutionLeg
One actor's unit of work on a ticket — the atom of the execution trail.

| Field | Type | Notes |
|---|---|---|
| `id`, `ticket_id`, `sequence` | | |
| `actor_type`, `actor_id` | | `human` (user) or `agent` (agent profile) |
| `harness_run_id` | string, nullable | the harness's own run identifier, for cross-system tracing |
| `started_at`, `ended_at` | timestamp | |
| `outcome` | enum | `completed`, `handed_off`, `blocked_on_human`, `rejected`, `timed_out`, `budget_exceeded`, `policy_denied` |
| `artifacts` | jsonb | per the ticket type's `agent_io_contract` |
| `confidence` | number, nullable | agent-reported, 0–1 |

### McpCallRecord *(append-only)*
Every tool call the harness makes on a ticket's behalf. This is the audit spine for D5 and a cost
input for ROI.

| Field | Type | Notes |
|---|---|---|
| `id`, `execution_leg_id`, `mcp_installation_id` | | |
| `tool_name` | string | |
| `arguments_digest` | string | hash + redacted preview; full arguments retained only if the installation permits argument logging |
| `outcome` | enum | `ok`, `error`, `denied_by_policy`, `timeout` |
| `latency_ms`, `cost` | number, Money | |
| `called_at` | timestamp | immutable |

### HandoffEvent
| Field | Type | Notes |
|---|---|---|
| `from_leg_id` | uuid | |
| `to_actor_type`, `to_actor_id` | | may be unresolved at creation if routing is required |
| `reason_code` | enum | `needs_different_capability`, `stage_complete`, `low_confidence`, `out_of_scope`, `budget_would_exceed`, `missing_mcp_grant` |
| `context_bundle` | jsonb | curated summary passed forward — *not* the full ticket |
| `hop_count` | integer | loop protection reads this |

`missing_mcp_grant` is worth calling out: an agent that determines it needs a tool it holds no
grant for hands off rather than failing — often to a profile that does hold the grant, which is a
routine and healthy outcome rather than an error.

### UsageRecord *(append-only)*
Token-level telemetry, reported by the harness. This is the **finest granularity Meridian stores** —
the harness's own per-step trace stays in the harness; Meridian keeps one record per model
invocation and correlates back by `harness_step_id`. See
[`roi-analytics.md`](03-components/roi-analytics.md) §1 for the layering rationale.

| Field | Type | Notes |
|---|---|---|
| `id`, `execution_leg_id` | uuid | |
| `harness_run_id`, `harness_step_id` | string | correlation keys for drill-through into the harness UI |
| `provider`, `model` | string | |
| `tokens_in`, `tokens_out` | integer | |
| `cache_read_tokens`, `cache_write_tokens` | integer | prompt-caching detail — the main lever on agent unit cost, so it is tracked separately rather than folded into `tokens_in` |
| `reasoning_tokens` | integer, nullable | where the provider reports them separately |
| `unit_prices` | jsonb | snapshot of the per-1K rates applied, so historical cost stays reproducible when pricing changes |
| `computed_cost` | Money | derived from tokens × `unit_prices` |
| `occurred_at` | timestamp | immutable |

An MCP server that is itself LLM-backed reports its own usage through `McpCallRecord.cost`; those
are **not** double-counted as `UsageRecord` rows, which are strictly the harness's own inference.

---

## 5. ROI Entities

### RoiBaseline
| Field | Type | Notes |
|---|---|---|
| `project_id`, `ticket_type_id` | | baseline can be per-type |
| `source` | enum | `historical_velocity`, `manual_estimate` |
| `baseline_hours`, `baseline_cost` | | |

### CostEntry
The normalised money view. Token detail lives in `UsageRecord`; `CostEntry` is what rolls up.

| Field | Type | Notes |
|---|---|---|
| `execution_leg_id`, `kind` | | `agent_model` (inference), `mcp_call` (metered server usage), `human_time` |
| `amount` | Money | |
| `raw_metric` | jsonb | `{tokens_in, tokens_out, cache_read}`, `{calls, unit_price}`, or `{hours, hourly_rate}` |

### UsageRollup
Materialised aggregates so dashboards never scan raw usage. One row per
`(scope_type, scope_id, period)`, recomputed incrementally as legs close.

| Field | Type | Notes |
|---|---|---|
| `scope_type` | enum | `ticket`, `sprint`, `phase`, `project`, `portfolio`, `agent_profile`, `mcp_installation` |
| `scope_id`, `period_start`, `period_end` | | |
| `tokens_in`, `tokens_out`, `cache_read_tokens` | integer | |
| `cost_model`, `cost_mcp`, `cost_human`, `cost_total` | Money | cost split by source — the split is what makes it actionable |
| `tickets_completed`, `legs`, `handoffs`, `mcp_calls` | integer | |
| `human_hours` | number | |

### EfficiencyMetric
Derived indicators computed from `UsageRollup` at each scope — see
[`roi-analytics.md`](03-components/roi-analytics.md) §4.

| Field | Type | Notes |
|---|---|---|
| `scope_type`, `scope_id`, `period_*` | | mirrors `UsageRollup` |
| `cost_per_ticket`, `tokens_per_ticket` | | |
| `cost_per_story_point` / `cost_per_hour_saved` | | normalises across differently-sized work |
| `first_pass_yield` | number | fraction completed with no rework and no rejected approval |
| `rework_rate` | number | returns from a review/`blocked` state per completed ticket |
| `handoffs_per_ticket` | number | routing efficiency |
| `cache_hit_ratio` | number | `cache_read_tokens / tokens_in` — the single biggest cost lever |
| `autonomy_mix` | jsonb | share of tickets by `fully_autonomous` / `human_assisted` / `human_only` |
| `denied_call_rate` | number | `denied_by_policy` share — diagnoses mis-scoped grants, not bad agents |

### RoiSummary
| Field | Type | Notes |
|---|---|---|
| `ticket_id`, `total_cost`, `total_cycle_time` | | |
| `baseline_cost_used` | Money | snapshot, so history stays reproducible |
| `roi_pct`, `time_saved` | | |
| `autonomy_level` | enum | `fully_autonomous`, `human_assisted`, `human_only` |
| `attributed_legs` | AttributedLeg[] | `{execution_leg_id, cost_share, time_share}` — [ADR-0004](adr/0004-roi-attribution-model.md) |

---

## 6. Notes on Design Choices

- **AgentProfile, not "installed agent".** The thing you assign is not an MCP server and not a
  harness — it's a *configured worker* that happens to run on a harness and hold grants to some
  servers. This is what makes "the harness decides which MCP server to call" (D5) expressible:
  the profile defines the permitted set, the harness picks within it.

- **McpGrant is separate from McpInstallation.** Enabling a server for the workspace (D7) and
  permitting a specific agent profile to use it (D5) are different decisions made by different
  people at different times. Collapsing them would mean enabling a server silently widens every
  agent's capability.

- **`claim` lives on the ticket.** With both event and scheduled triggers active, and possibly
  multiple harness replicas, the claim/lease is the only thing preventing duplicate work. Putting
  it on the ticket row makes the check atomic with the read.

- **Phase and Sprint coexist rather than being alternatives.** In `hybrid` mode a sprint has a
  `phase_id`, so the same ticket can roll up into both a sprint burndown and a phase percent-
  complete without duplicate tracking — see [ADR-0006](adr/0006-unified-waterfall-and-agile.md).

- **`Status.category` is a fixed enum alongside a free-text name.** Custom per-project status
  names (a governance requirement in enterprise rollouts) must not break timeline colouring,
  burndown, or ROI cycle-time — so every custom status still maps to one of five categories.

- **`UsageRecord` is the floor, not the whole trace.** Storing every harness step, tool
  deliberation, and intermediate message would make Meridian a duplicate observability platform
  for the harness. One record per model invocation, plus correlation keys, is enough to answer
  every cost, token, and efficiency question at ticket level and above, while drill-through to the
  harness answers "what happened inside step 7".

- **`UsageRollup` and `EfficiencyMetric` are materialised, not computed on read.** Project- and
  portfolio-level dashboards would otherwise aggregate millions of usage rows per page view. They
  are recomputed incrementally when a leg closes and when a period boundary passes.

- **Visibility is a property of the ticket, driven by rules.** Making confidentiality a manual
  per-ticket toggle guarantees leaks; `VisibilityRule` sets it from the ticket's own content at
  creation, and a rule may only narrow — never widen — what a higher-precedence rule decided.

- **`StatusScheme` is separate from `Workflow`.** Enterprises need statuses defined once and
  reused (often mandated), while individual projects still need latitude. The scheme is the
  shareable, versioned unit; a project pins a version and may fork if policy allows.

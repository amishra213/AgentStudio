# Component: Project Administration

> Project creation, status definition, and tracking configuration. Builds on
> [`02-data-model.md`](../02-data-model.md) (`Project`, `ProjectTemplate`, `StatusScheme`,
> `Budget`) and pairs with [`permissions-rbac.md`](permissions-rbac.md).

---

## 1. Project Creation

Creating a project provisions eight things at once. Doing them as one guided act — rather than
leaving an empty project and a checklist — is what keeps configuration consistent across an
organisation.

| Provisioned | Source |
|---|---|
| Project key + name | Entered; key is validated unique and becomes the ticket prefix (`OPS-142`) |
| Delivery mode | `waterfall` / `agile` / `kanban` / `hybrid` — see [`delivery-modes.md`](delivery-modes.md) |
| Status scheme | Picked from shared schemes, or forked to a project-local copy (§3) |
| Ticket types | Which types this project uses, from the workspace catalogue |
| Role assignments | Groups/users mapped to project roles, seeded from the template's `role_seed` |
| Default ticket visibility | Plus any `VisibilityRule`s from the template ([`permissions-rbac.md`](permissions-rbac.md) §7) |
| MCP scope | Which enabled MCP installations are usable in this project — *scope only, not grants* |
| Budget + ROI baseline | Cost ceiling, alert thresholds, and the baseline ROI compares against |

### From a template

A `ProjectTemplate` bundles all of the above plus starter phases/gates or a sprint cadence, and
starter `TriggerRule` blueprints. A programme running twenty similar client engagements defines
the shape once; each new engagement is a single creation call that arrives already governed,
already budgeted, and already wired for agent pickup.

Templates are versioned. Updating a template does **not** retroactively alter projects created
from it — an admin can see which projects have drifted from their template and choose to
re-apply specific parts, but nothing changes under a running project silently.

### Creation is permission-gated

Only `workspace_admin` can create projects by default. Workspaces may delegate creation to a named
group, optionally restricted to specific templates — which is how an organisation allows teams to
self-serve without allowing them to invent their own governance.

---

## 2. Ticket Type Configuration

Per workspace, with per-project selection of which types are active. A type defines its field
schema (including each field's `sensitivity`), its timeline render mode, its SLA policy, and its
agent I/O contract — see [`ticketing.md`](ticketing.md) §1.

Field schema changes are additive-safe: adding an optional field is immediate; making a field
required, or removing one, requires an explicit migration step showing how many existing tickets
are affected and what happens to their data.

---

## 3. Status Definition

### Statuses

A status is more than a name. Each carries:

| Property | Purpose |
|---|---|
| `name` | Project/organisation vocabulary — `Awaiting CAB`, `In UAT`, `Triaged` |
| `category` | Fixed enum: `not_started`, `active`, `blocked`, `done`, `cancelled` |
| `colour` + non-colour cue | Timeline and board rendering ([`timeline.md`](timeline.md) §2) |
| `transitions_to` | Which statuses may follow |
| `approval_role` | Role whose approval is required to enter |
| `sla_behaviour` | Whether SLA clocks run, pause, or stop here |
| `wip_limit` | Kanban column limit |
| `automations` | `on_enter` / `on_exit` actions from a fixed vocabulary |

**The `category` is mandatory and is the reason custom statuses are safe.** Everything
cross-cutting — timeline colour, burndown, SLA pause, ROI cycle-time, trigger-rule matching —
reads the category, never the name. A project can therefore invent whatever vocabulary its
auditors require without breaking a single rollup.

### Status schemes

Statuses and transitions are grouped into a versioned `StatusScheme` that is **shared across
projects**. This is the difference between a tool that scales to an enterprise and one that
doesn't: without a shareable scheme, thirty projects invent thirty near-identical workflows and
portfolio reporting becomes guesswork.

- A scheme contains one `Workflow` per ticket type.
- Projects **pin a scheme version**. Publishing a new version does not disturb pinned projects;
  admins migrate deliberately.
- `is_shared` schemes are edited centrally. A project may **fork** to a local copy unless
  `locked_by_policy` is set — which is how compliance-mandated states are kept uniform while
  everything else stays flexible.

### Editing a live workflow

Removing or renaming a status that tickets currently occupy is the classic way to corrupt a
tracker. The editor therefore requires:

1. **Impact preview** — how many tickets, in which projects, sit in each affected status.
2. **A migration map** — every removed status must name its replacement; tickets are moved in one
   transaction, each move producing an ordinary `status_changed` `ActivityEvent` attributed to the
   admin, so history stays truthful.
3. **Transition validation** — the resulting graph must leave every ticket in a state with at
   least one legal exit; unreachable or dead-end states are rejected before save.

---

## 4. Tracking Configuration

What "tracked" means is itself configuration, set per project:

| Setting | Options |
|---|---|
| Estimate unit | Story points, hours, or none |
| Time tracking | Off, optional, or required on human legs (affects ROI `human_time` accuracy) |
| Required fields per transition | e.g. `rollback_plan` required to enter `Approved` on a `change` |
| Definition of done | A checklist enforced on entry to a `done`-category status |
| Rework counting | Which transitions count as rework for [`roi-analytics.md`](roi-analytics.md) §4 |
| Baseline locking | Whether re-baselining requires PM or admin authority |
| Agent eligibility | Which statuses may be picked up by the harness at all — a coarse safety switch above individual `TriggerRule`s |

That last row is worth its own note: it lets an organisation say "agents never touch anything past
`In Review`" as a single project-level statement, independent of however many trigger rules exist.

---

## 5. Audit of Configuration Itself

Configuration changes are versioned and logged with the same rigour as ticket changes: who changed
which scheme, when, what the previous value was, and which projects were affected. A workflow that
silently changed three months ago is otherwise indistinguishable from a workflow that was always
wrong — and in regulated programmes the configuration history is exactly what gets audited.

# Component: Permissions & RBAC

> Builds on [`02-data-model.md`](../02-data-model.md). See also [`06-security.md`](../06-security.md) for the sandboxing this section assumes at the transport level.

---

## 1. Human Roles (Workspace and Project Scoped)

| Role | Scope | Can do |
|---|---|---|
| `workspace_admin` | Workspace | Billing, marketplace install approval, SSO config, create/archive projects, manage all RBAC |
| `project_pm` | Project | Manage timeline/sprints, create/edit/assign tickets, approve agent installs *for this project*, set ROI baselines |
| `architect` | Project | Same ticket rights as `project_pm` minus sprint/timeline admin; can override handoff routing on a ticket |
| `contributor` | Project | Create/edit/assign tickets to self or others, comment, cannot change workflow config |
| `viewer` | Project or Workspace | Read-only: timeline, board, ROI dashboards |

Roles are additive across projects: a user can be `project_pm` on one project and `viewer` on
another within the same workspace.

---

## 2. Agents Are Not a Role — They Hold a Permission Scope

An agent does not get a role from the table above. Instead, each `AgentInstallation` carries a
`permission_scope`, granted by whoever installs it, that is strictly narrower than what any human
role can do by default:

| Scope dimension | Example | Enforced by |
|---|---|---|
| Project scope | Which projects this installation may be assigned tickets in | Orchestrator, on dispatch |
| Ticket field scope | Which fields it may read (e.g., not `contract_value` unless explicitly granted) | Orchestrator, when building the ticket payload sent to the agent |
| Tool scope | Subset of the manifest's `required_tool_scopes` actually granted (`read:comments`, `write:attachments`, etc.) | Orchestrator, per API call the agent makes back into Meridian |
| Handoff scope | `allowed_handoff_targets` | Orchestrator, on handoff routing |
| Spend scope | `budget_ceiling`, per-run and cumulative | Orchestrator, before dispatch and on each cost report |

**An agent can never see or do more than its installation's scope allows, regardless of what its
manifest claims it wants.** The manifest declares a maximum; the installation grants an actual,
possibly smaller, subset. This is the same pattern as an OAuth app's requested scopes vs. the
scopes a user actually consents to.

---

## 3. Enforcement Point

All of the above is enforced in exactly one place: the Agent Orchestrator's dispatch and callback
handling. Agents never get a database credential or a general API token — every read the agent
receives is a payload the Orchestrator assembled by filtering the ticket through the installation's
`permission_scope`, and every write the agent attempts is a scoped API call validated against that
same scope before Core PM Service ever sees it. This means:

- A tightened scope takes effect on the *next* dispatch with no agent-side changes needed.
- A compromised or misbehaving agent endpoint cannot exceed its scope even if it ignores the
  contract — the enforcement is server-side, not a trust-the-agent convention.

---

## 4. Co-Assignment and Approval Gates

When a ticket is co-assigned (human + agent, see
[`human-ai-collaboration.md`](human-ai-collaboration.md)), certain transitions can be configured to
require the human's explicit approval regardless of the agent's own confidence — e.g., an agent
may produce a `Done`-ready artifact, but the transition to the `done` status category is gated on
the human `reviewer`-role assignment approving it. This is a per-workflow configuration
(`Status.transitions_to` can require `approval_role: reviewer`), not a hardcoded rule, so a fully
autonomous project can disable it entirely while a regulated one can require it on every ticket
type.

---

## 5. Delegated Human Access via Agents

An agent acting on a ticket inherits **no** ambient human permission — it only ever gets the
scope its installation was granted, even if the human who assigned the ticket to it has broader
access. This avoids the common "agent runs with the permissions of whoever clicked the button"
privilege-escalation pattern; scopes are set once at install time by an admin/PM, not implicitly
inherited per assignment.

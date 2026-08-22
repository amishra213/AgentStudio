# Component: Notifications & Integrations

> Builds on [`02-data-model.md`](../02-data-model.md) — `ActivityEvent` is the source every
> notification derives from — and honours the visibility rules in
> [`permissions-rbac.md`](permissions-rbac.md) §7.

---

## 1. Derived From the Event Log

Every notification traces back to an `ActivityEvent`. The Notification Service subscribes to the
event stream and applies per-user, per-project preferences to decide fan-out. There is no second
code path that "also" sends a Slack message on assignment — assignment produces one event, and the
service decides who hears about it and how.

Two benefits: notification content can never contradict the audit log, and adding a channel is a
new fan-out target rather than new emission calls scattered through the codebase.

---

## 2. Visibility Is Applied Before Fan-Out

A notification is a leak path, so the visibility predicate runs **before** delivery, not after:

- A recipient without access to a ticket receives **nothing** — the notification is suppressed
  entirely rather than sent as a redacted stub, since "OPS-203 was updated" already discloses that
  the ticket exists.
- Fields of `sensitivity: restricted`/`secret` are omitted from previews even for recipients who
  can see the ticket, because email and push previews land on lock screens and in inboxes outside
  the org's control.
- Deep links resolve against the recipient's own permissions at click time, so access revoked
  between send and click is honoured.

---

## 3. Channels

| Channel | Typical triggers | Notes |
|---|---|---|
| In-app | Everything relevant to the user | Always on; the only channel without opt-out |
| Email | Digested (default hourly), immediate for ask-human and SLA-risk | Per-user frequency preference |
| Slack | Project→channel mapping | **Bi-directional**: thread replies post comments, including answering an agent's ask-human without leaving Slack |
| Webhook | Workspace-configured endpoint | For custom downstream integrations |
| Push | High-urgency only — SLA breach, budget ceiling hit, P1 incident | Preview text is visibility-filtered per §2 |

---

## 4. Inbound Integrations

| Integration | Direction | Purpose |
|---|---|---|
| **Email-to-ticket** | In | A project inbox address creates tickets from email — the standard path for incidents and support cases. Content is marked as externally-sourced provenance ([`06-security.md`](../06-security.md) §4) |
| **Slack** | Both | `/meridian create`; thread replies as comments; ask-human answers |
| **Monitoring / alerting** | In | Alert webhooks create `incident` tickets, which then match event trigger rules for immediate agent triage |
| **GitHub / GitLab** | Both | Link tickets to PRs and commits; a merge can auto-transition status via a configured automation |
| **Calendar (ICS)** | Out | Sprint boundaries, phase dates, and gate dates for stakeholders who live in a calendar |
| **SSO / IdP** | In | SAML/OIDC login; group mappings seed project roles at project creation ([`project-administration.md`](project-administration.md) §1) |

No integration bypasses the Workflow Engine or the permission model: a merge-triggered transition
is validated exactly like a human's click, and an email-created ticket is subject to the same field
schema, workflow, and `VisibilityRule`s as one created in the UI.

---

## 5. Digesting and Noise Control

An agent-heavy project can generate events far faster than a human can read them, so the service:

- **De-duplicates** repeated event types on one ticket within a short window into a single
  notification.
- Applies a **noise budget** per user per project: routine agent progress (leg started, MCP call
  made, intermediate artifact posted) is in-app only by default; only terminal or
  attention-requiring states — ask-human, handoff to a human, completion on a human-owned ticket,
  budget thresholds, SLA risk — escalate to email/Slack/push.

The default is deliberately quiet. An automation platform that notifies on every agent action
trains people to ignore it, which defeats the ask-human path that actually needs a fast human
response.

# Component: Notifications & Integrations

> Builds on [`02-data-model.md`](../02-data-model.md) (`ActivityEvent` is the source every notification is derived from).

---

## 1. Notifications Are Derived From the Event Log, Not Authored Separately

Every notification traces back to an `ActivityEvent` (see [`02-data-model.md`](../02-data-model.md)
§2). The Notification Service subscribes to the event stream and applies per-user, per-project
preferences to decide fan-out — there is no second code path that "also" sends a Slack message on
assignment; assignment produces one event, and the Notification Service decides who hears about it
and how. This keeps notification content trustworthy (it can never say something the audit log
disagrees with) and keeps adding a new channel (e.g., Teams) a matter of adding a new fan-out
target, not a new event-emission call scattered through the codebase.

---

## 2. Channels

| Channel | Trigger examples | Notes |
|---|---|---|
| In-app | All events relevant to the user (assigned, mentioned, ask-human on their ticket) | Always on; the only channel with no user opt-out |
| Email | Digested (default: hourly) or immediate for `NeedsInput`/SLA-risk events | Per-user frequency preference |
| Slack | Configurable per-project channel mapping (e.g., ticket events in `#eng-project-x`) | Two-way: replying in the Slack thread posts a `Comment` back on the ticket, including answering an ask-human question from Slack |
| Webhook | Arbitrary workspace-configured HTTP endpoint | For custom integrations not covered below |
| Push (mobile, future) | High-urgency only (`NeedsInput` SLA breach, budget ceiling hit) | Deferred to a later phase |

---

## 3. Inbound Integrations

| Integration | Direction | Purpose |
|---|---|---|
| **Email-to-ticket** | Inbound | A configured project inbox address creates a new ticket from an incoming email (subject → title, body → description); used heavily by support/consulting-style projects |
| **Slack** | Bi-directional | `/meridian create` slash command creates a ticket; thread replies post comments; also the ask-human answer channel (§2) |
| **GitHub / GitLab** | Bi-directional | Link a ticket to a PR/commit; PR merge can auto-transition a ticket's status (configurable automation, per [`ticketing.md`](ticketing.md) §4); PR review comments can optionally mirror into ticket comments |
| **Calendar** | Outbound | Sprint start/end and milestone dates can publish to a calendar feed (ICS) for stakeholders who live in their calendar, not the tool |
| **SSO / IdP** | Inbound (auth) | SAML/OIDC for workspace login; group mappings can drive default project role assignment |

None of these integrations bypass the Workflow Engine or the permission model — a GitHub-triggered
status transition is validated by the same Workflow Engine as a human clicking a button, and an
email-created ticket is subject to the same field schema and workflow as one created in the UI.

---

## 4. Digesting and De-duplication

To avoid an agent-heavy project drowning humans in notifications (an agent can generate many
events quickly), the Notification Service:

- De-duplicates repeated events of the same type on the same ticket within a short window into one
  notification ("3 status changes on ENG-142 in the last 2 minutes" collapses to one line).
- Applies a **noise budget** per user per project — routine agent progress events (leg started,
  intermediate artifact posted) are in-app only by default; only terminal states (`blocked`,
  `handoff` to a human, `completed` on a human-owned ticket) escalate to email/Slack by default.
  Users can widen this per project if they want more visibility.

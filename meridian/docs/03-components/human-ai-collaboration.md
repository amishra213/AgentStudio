# Component: Human-AI Collaboration

> Builds on [`agent-execution-and-handoff.md`](agent-execution-and-handoff.md) (ask-human mechanics) and
> [`02-data-model.md`](../02-data-model.md) (`Assignment`, `Comment`).

---

## 1. One Shared Surface, Not Two Tools Bolted Together

A ticket has exactly one activity feed, one comment thread, one status. Whether the last three
actions were two human comments and an agent's proposal, or three consecutive agent handoffs, the
UI renders them in the same chronological stream with actor avatars distinguishing human vs. agent
(and which agent). There is no separate "AI panel" a human has to switch to — this is what makes
handoff *to a human* feel like a normal reassignment rather than an escape hatch into a different
system.

---

## 2. Co-Assignment

A ticket may carry both a human `Assignment` and an agent `Assignment` simultaneously, each with a
`role` (`owner`, `reviewer`, `collaborator`) that defines the responsibility split:

| Pattern | Human role | Agent role | Typical use |
|---|---|---|---|
| Agent drafts, human approves | `reviewer` | `owner` (does the work) | Agent produces a first-pass artifact; ticket cannot leave `In Review` without the human reviewer's approval (see [`permissions-rbac.md`](permissions-rbac.md) §4) |
| Human leads, agent assists | `owner` | `collaborator` | Human does the primary work; agent is on hand for lookups/drafting sub-pieces on request, posted as `proposal` comments the human can pull in |
| Agent leads, human on standby | `owner` | — | Human is a watcher only, pulled in solely via ask-human; the common case for fully-autonomous-capable ticket types |

The split is set at assignment time and is visible on the ticket card (board view shows both
avatars with role badges), so "who's actually doing this" is never ambiguous at a glance.

---

## 3. Ask-Human, From the Human's Side

When an agent blocks (see [`agent-execution-and-handoff.md`](agent-execution-and-handoff.md) §6),
the human experience is:

1. Ticket visibly changes status to `Needs Input` (or the project's equivalent-category status)
   on the board — it stands out from ordinary `In Progress` tickets.
2. A notification arrives (in-app, and via Slack/email per the human's preferences —
   see [`notifications-and-integrations.md`](notifications-and-integrations.md)) with the agent's
   question inline, deep-linking to the ticket.
3. The human answers directly in the ticket's comment thread (an `answer`-kind comment) — no
   separate approval UI, no context switch.
4. The moment the answer posts, the ticket flips back to `In Progress` and the human sees a live
   "agent resumed" indicator (via the Realtime Service) confirming the loop closed.

If the human doesn't answer within the configured SLA, escalation follows the same path as any
other unattended `Needs Input` ticket (project-configurable: reassign, notify a broader group, or
notify the PM).

---

## 4. Presence and Live Steering

The Realtime Service tracks, per ticket, who/what is currently active:

- **Presence indicators**: "Agent X is working" (from run start to completion/handoff/block),
  "Jane is viewing", shown on the ticket detail view the same way collaborative editors show
  cursors.
- **Live takeover.** A human with `owner` or `architect` rights can interrupt an in-flight agent
  run at any time (a `pause`/`cancel` control on the ticket), which sends a cancel signal to the
  agent's run and immediately creates a system comment recording the interruption and why (a
  free-text reason the human provides). This does not require the agent to have blocked itself —
  it's an unconditional human override, consistent with treating humans as always able to steer
  (overview G5).
- **Live edit of agent output.** A `proposal`-kind comment (an agent's draft artifact) can be
  edited directly by a human with appropriate role, producing a new comment version attributed to
  the human but linked to the original proposal — so "the agent proposed X, the human changed it
  to Y" is preserved rather than the edit silently overwriting the agent's contribution.

---

## 5. Feedback Loop Into the Marketplace

When a human overrides, rejects, or heavily edits an agent's output, that signal is recorded
(`ExecutionLeg.outcome = rejected`, or a `human_edit_distance` metric computed on accepted-but-
edited proposals) and rolled into the objective trust signals surfaced in the marketplace
(see [`agent-marketplace.md`](agent-marketplace.md) §5) — high edit-distance or rejection rates on
a given agent/ticket-type combination are visible to workspace admins deciding whether to keep an
agent auto-assigning to that ticket type.

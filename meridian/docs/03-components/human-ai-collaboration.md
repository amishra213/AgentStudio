# Component: Human-AI Collaboration

> Differentiator **D3** — tickets worked by agents, humans, or both. Builds on
> [`agent-harness.md`](agent-harness.md) (ask-human, outcomes) and
> [`02-data-model.md`](../02-data-model.md) (`Assignment`, `Comment`).

---

## 1. One Surface

A ticket has one activity feed, one comment thread, one status. Whether the last three entries are
two human notes and an agent proposal, or three consecutive agent legs, they render in the same
chronological stream with actor avatars distinguishing human from agent profile. There is no
separate "AI panel" to switch to.

This is what makes handoff *to a human* feel like an ordinary reassignment rather than an escape
hatch out of an automation system — and it is why the harness's ask-human is just a typed comment
rather than a bespoke UI.

---

## 2. Co-Assignment

A ticket may carry one human and one agent `Assignment` at once, each with a `role`:

| Pattern | Human role | Agent role | Use |
|---|---|---|---|
| **Agent drafts, human approves** | `reviewer` | `owner` | Agent produces the artifact; the terminal transition carries `Status.approval_role: reviewer`, so it cannot close without sign-off ([`permissions-rbac.md`](permissions-rbac.md) §5) |
| **Human leads, agent assists** | `owner` | `collaborator` | Human does the work; the agent posts `proposal` comments on request — lookups, drafts, checks |
| **Agent leads, human on standby** | — (watcher) | `owner` | Human is pulled in only via ask-human; the common shape for event-triggered operational work |

The split is set at assignment and shown on the ticket card and timeline bar (both avatars, with
role badges), so "who is actually doing this" is never ambiguous.

Capacity planning counts a co-assigned ticket partially against both human hours and agent budget,
split by the declared responsibility (see [`delivery-modes.md`](delivery-modes.md) §3).

---

## 3. Ask-Human From the Human's Side

When the harness calls `tickets.ask_human`:

1. The ticket moves to a `blocked`-category status — visually distinct on both the board and the
   timeline, so stalled agent work doesn't hide among active work.
2. A `question` comment appears with the agent's question and any partial artifacts.
3. A notification goes out per the recipient's preferences, with the question inline and a deep
   link ([`notifications-and-integrations.md`](notifications-and-integrations.md)).
4. The human replies in the normal comment box — an `answer`-kind comment. No separate approval UI.
5. The status returns to active and a live "agent resumed" indicator confirms the loop closed.

The agent's `ExecutionLeg` stays open across the whole round trip, so the wait is attributed to
that leg for cycle-time purposes and the exchange does **not** count as a handoff hop.

If nobody answers within the SLA, escalation follows project policy: widen the notification,
reassign, or alert the PM.

---

## 4. Presence and Live Steering

The realtime layer tracks, per ticket:

- **Presence** — "Incident First Responder is working" (from claim to terminal outcome), "Jane is
  viewing", shown like collaborative-editor cursors. The agent's current MCP call can optionally be
  surfaced ("calling `itsm.search_similar`"), which turns an opaque wait into something a human can
  judge.
- **Live takeover.** A human with `owner` or `architect` rights can pause or cancel an in-flight
  run at any point, without waiting for the agent to block. This releases the claim, closes the leg,
  and records a system comment with the human's stated reason. It is an unconditional override —
  humans are always able to steer.
- **Editing agent output.** A `proposal` comment can be edited by a human, producing a new version
  attributed to the human and linked to the original. The agent's contribution is preserved rather
  than silently overwritten, which is what makes the edit-distance signal in §5 meaningful.

---

## 5. Feedback Into Routing and the Marketplace

Human reactions are recorded as signal, not just as edits:

| Signal | Source | Used for |
|---|---|---|
| Rejection rate | `ExecutionLeg.outcome = rejected` after human review | Agent profile quality; trigger-rule tuning |
| Edit distance | Human edits to accepted `proposal` comments | Whether a profile's output is genuinely usable |
| Override rate | Live takeovers per profile | Whether a profile is trusted in practice |
| Denied-tool rate | `McpCallRecord.outcome = denied_by_policy` | Whether a profile's **grants** are mis-scoped — a distinct diagnosis from poor output ([`permissions-rbac.md`](permissions-rbac.md) §4) |

These surface on the agent profile's own detail page and, in anonymised aggregate, as MCP server
trust signals ([`mcp-marketplace.md`](mcp-marketplace.md) §6). The last row matters most in
practice: an agent that looks unreliable is often correctly reasoning about work it simply lacks a
grant to perform, and separating those two diagnoses is the difference between revoking a useful
profile and fixing one line of policy.

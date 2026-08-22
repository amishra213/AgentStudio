# ADR-0003: Ticket History Is an Append-Only Event Log

## Status
Accepted

## Context
A ticket's current state (status, assignee, fields) needs to be queried cheaply and often (every
board render). Its **history** needs to be complete, ordered, and immutable — for audit
(overview G7), for ROI cycle-time computation (time-in-status per leg), and for reconstructing why
an automated decision happened (e.g., a handoff-loop escalation, per
[`agent-harness.md`](../03-components/agent-harness.md) §7). A
mutable-row-with-an-audit-log-on-the-side design tends to let the two drift — an audit log that's a
side effect of a mutation is easy to accidentally skip in one code path.

## Decision
The `activity_event` table (see [`02-data-model.md`](../02-data-model.md) §2) is the **single
source of truth** for everything that has ever happened to a ticket, and it is append-only at the
database grant level — the application role has no `UPDATE`/`DELETE` on it. Current ticket state
(the `ticket` row's `status_id`, `current_assignments`, etc.) is a **materialized projection**,
updated synchronously in the same transaction as the event append, so reads stay cheap while the
event log stays the authoritative record.

## Consequences
- Every mutation to a ticket must go through the one code path that appends an event and updates
  the projection together — this is enforced by Core PM Service being the only module with write
  access to either table (see [`01-architecture.md`](../01-architecture.md) §4).
- ROI cycle-time and time-in-status metrics (used throughout
  [`roi-analytics.md`](../03-components/roi-analytics.md)) are computed directly from the event
  log rather than from separately-tracked timers, so they can never disagree with the audit trail.
- A ticket's projection can, in principle, be rebuilt entirely from its event log — useful for
  fixing a projection bug without any data loss, since the log itself was never the thing that had
  the bug.
- Cost: every read of "current state" requires the projection to exist and be correct; a bug in
  the projection-update code is a availability/correctness bug even though the underlying events
  are safe. This is judged an acceptable tradeoff for the audit guarantees the log provides.

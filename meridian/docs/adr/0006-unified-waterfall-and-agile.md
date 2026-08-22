# ADR-0006: One Model for Waterfall, Agile, Kanban, and Hybrid

## Status
Accepted

## Context
Differentiator D6 requires waterfall and agile to be co-equal. Most trackers are agile-first and
treat phases, gates, baselines, and critical path as plugin territory — which is why enterprise
programmes end up running the governance layer in a spreadsheet and the delivery layer in the
tool, reconciled by hand.

The naive implementations both fail:

- **Separate entities per methodology** (a `WaterfallTask` and an `AgileStory`) duplicates the
  workflow engine, the timeline, the permission model, and the agent integration — four times.
- **One methodology with the other emulated** (phases as labels, gates as tickets) means rollups,
  blocking behaviour, and baseline variance have to be reimplemented in reporting, where they
  drift.

## Decision
One `Ticket` entity, one `Workflow` engine, one timeline. Methodology differences live entirely in
**planning containers** and which views are primary:

- `Phase` and `Gate` exist for waterfall/hybrid; `Sprint` exists for agile/hybrid.
- A `Ticket` may reference a phase, a sprint, **both**, or neither.
- In `hybrid`, a `Sprint` carries a `phase_id` — so one ticket rolls up to both a sprint burndown
  and a phase percent-complete with no duplicate tracking.
- `Status.category` is a fixed five-value enum behind free-text status names, so burndown, timeline
  colouring, SLA logic, and ROI cycle-time work identically in every mode.
- `Gate` is distinct from `Milestone` specifically because a gate **blocks** — that behaviour is
  enforced by the Workflow Engine, not by reporting.

## Consequences
- The agent harness is methodology-agnostic: it works tickets, and a ticket looks the same in every
  mode. One harness integration covers all four, with `TriggerRule.filter` optionally scoping by
  `phase_ids` or `sprint_ids`.
- Mode changes on a live project are migrations with explicit rules, not reinterpretations;
  archived containers keep their history and their contribution to closed ROI periods
  ([`delivery-modes.md`](../03-components/delivery-modes.md) §6).
- Baseline-vs-actual has to be modelled from the start (`Project.baseline_locked_at` plus
  `planned_*`/`actual_*` on phases), since retrofitting a baseline onto a system that only stores
  current dates is not possible — the history simply isn't there.
- Cost: agile-only teams carry a schema containing phase and gate concepts they never use. Judged
  clearly worth it — the alternative is the two-tools-and-a-spreadsheet outcome this ADR exists to
  prevent.

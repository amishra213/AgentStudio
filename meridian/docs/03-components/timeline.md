# Component: The Timeline

> Differentiators **D1** (status tracked visually on a timeline) and **D2** (all ticket types on
> that timeline). Builds on [`02-data-model.md`](../02-data-model.md).

---

## 1. The Timeline Is the Default View

In most trackers the board is primary and the roadmap is a reporting afterthought — usually a
separate, often separately-licensed module fed by a subset of fields. Meridian inverts this: the
timeline is where work is **created, viewed, and status-tracked**, and the board and backlog are
alternate projections of the same data.

Two consequences follow, and they're the point of the whole design:

1. **Status is a visual property, not a column.** A ticket's bar is coloured by its
   `Status.category` and annotated with its specific status name, so "where is everything" is
   answered by looking, not by filtering.
2. **Time is always present.** Every ticket has a position in time — planned, actual, or both —
   which is what makes waterfall variance, sprint pacing, and incident clustering visible in the
   same picture.

---

## 2. What Renders, and How

`TicketType.timeline_render` (see [`02-data-model.md`](../02-data-model.md) §3) determines the
mark:

| Mark | Used by | Renders as |
|---|---|---|
| **Band** | Phase, Sprint | A horizontal container spanning its date range; child tickets nest inside it |
| **Bar** | Story, Task, Defect, Change | A bar from `planned_start` to `due_date`, coloured by status category |
| **Point** | Incident, Problem (at detection) | A marker at `detected_at`; if it has a resolution time it extends into a thin bar showing time-to-resolve |
| **Diamond** | Milestone, Gate | A point marker; **gates** additionally render a blocking indicator when unapproved and downstream phases are due to start |

Status colour uses the fixed `Status.category` set (`not_started`, `active`, `blocked`, `done`,
`cancelled`) rather than the project's custom status names — so two projects with entirely
different workflows still read identically at a glance, while hover/detail shows the specific
status. Colour is paired with a non-colour cue (fill pattern for `blocked`, outline for
`not_started`) so status remains readable for colour-vision-deficient users and in print/export.

---

## 3. Swimlanes

The timeline can be grouped into swimlanes by any of:

- **Phase** (default for waterfall/hybrid)
- **Sprint** (default for agile)
- **Assignee** — and critically, **assignee type**: a `Human / Agent / Both / Unassigned` grouping
  makes the AI contribution to a delivery immediately visible, which is the qualitative companion
  to the quantitative ROI dashboards in [`roi-analytics.md`](roi-analytics.md)
- **Ticket type category** — separates `delivery` work from `operational` work (incidents,
  problems) when both are active in one project
- **Service / component** — a custom field grouping, common for ops teams

---

## 4. Dependencies, Critical Path, and Baseline

- **Dependency arrows** come from `TicketLink` (`blocks`/`blocked_by`) and from
  `Phase.predecessor_phase_ids`. A blocked item shows the blocking cue described in §2.
- **Critical path** (waterfall/hybrid) is computed across phases and their dependency-linked
  tickets, and can be toggled on to highlight the chain where slippage moves the end date.
- **Baseline vs actual.** Once `Project.baseline_locked_at` is set, each phase and dated ticket
  renders a thin baseline bar beneath its actual bar. Variance is then visible as a shape rather
  than a number in a report — the single most requested thing in waterfall governance, and
  something an agile-first tool typically can't express at all.
- **At-risk computation.** A phase, gate, or milestone is flagged at-risk when its dependents'
  projected completion crosses the target date. Projection uses actual throughput — and because
  agent-worked tickets often complete far faster than human-worked ones, the projection uses
  separate throughput rates per assignee type rather than one blended average, which would
  otherwise make mixed teams' forecasts systematically wrong in both directions.

---

## 5. Creating and Editing on the Timeline

Direct manipulation, since the timeline is the working surface (D2):

- Drag on empty canvas within a phase/sprint band → create a ticket with those dates prefilled and
  that phase/sprint assigned.
- Drag a bar → change dates (validated against dependencies; a move that violates a `blocks` link
  warns and offers to cascade).
- Drag between swimlanes → reassign (to a human **or an agent profile** — the same picker, per D3).
- Right-click a gate → record an approval decision (subject to `Gate.approver_role`).

Every one of these produces an `ActivityEvent` through the same Core write path as a UI form edit
or an MCP call from the harness — the timeline has no privileged mutation route.

---

## 6. Portfolio View

Projects sharing a portfolio group render on one timeline, collapsed to phase/sprint bands with
per-project rollup status. Editing is disabled at portfolio level — changes are made in the owning
project — which keeps a single, unambiguous source of truth for every date.

---

## 7. Performance Considerations

A timeline over a large portfolio can address tens of thousands of marks. The intended approach:
server-side aggregation into the requested time buckets and zoom level (returning rollups rather
than raw tickets above a density threshold), with virtualised rendering client-side and
progressive detail on zoom-in. The materialised ticket projection described in
[ADR-0003](../adr/0003-event-sourced-ticket-activity.md) is what makes these range queries cheap —
timeline reads never replay the event log.

# Component: Delivery Modes — Waterfall, Agile, Kanban, Hybrid

> Differentiator **D6**. Builds on [`02-data-model.md`](../02-data-model.md) (`Project`, `Phase`,
> `Gate`, `Sprint`) and [ADR-0006](../adr/0006-unified-waterfall-and-agile.md).

---

## 1. Four Modes, One Model

`Project.delivery_mode` selects the mode. All four share the same `Ticket`, `Workflow`, timeline,
and agent-harness machinery — the mode changes which *planning containers* exist and which views
are primary, not how work is represented.

| Mode | Containers | Primary view | Ceremony |
|---|---|---|---|
| `waterfall` | Phases + Gates | Timeline (baseline vs actual, critical path) | Gate approvals |
| `agile` | Sprints | Board + burndown | Sprint planning, close |
| `kanban` | None (continuous flow, WIP limits) | Board | Pull-based |
| `hybrid` | Phases **containing** Sprints | Timeline, drillable to sprint boards | Both gates and sprint ceremonies |

The reason to support all four rather than pick one: enterprises rarely run purely either way. A
regulated programme has fixed phases and sign-off gates imposed from outside the delivery team,
while the build phase inside it is run in sprints. Tools that force a choice get worked around
with spreadsheets for whichever half they don't model.

---

## 2. Waterfall

**Phases** are sequenced containers with planned dates, predecessors, and a rolled-up
`percent_complete` derived from child ticket status — not hand-maintained.

**Gates** are what distinguish a phase boundary from a milestone: a gate has `criteria`, an
`approver_role`, and `blocks_phase_ids`. An unapproved gate whose downstream phase is due to start
raises the at-risk indicator described in [`timeline.md`](timeline.md) §4, and — depending on
project policy — can hard-block transitions on tickets in the downstream phase via the Workflow
Engine.

**Baseline vs actual.** Locking `Project.baseline_locked_at` snapshots every phase's planned dates.
Subsequent replanning changes `planned_*` values while the baseline stays fixed, so variance is
always computable. Re-baselining is an explicit, logged action requiring PM authority — otherwise
"we were always going to finish in November" becomes unfalsifiable.

**WBS.** Ticket `parent_id` nesting provides work-breakdown structure within a phase; the timeline
renders it as an expandable hierarchy and rolls estimates and percent-complete upward.

---

## 3. Agile

**Sprints** carry a goal, dates, and a two-part `capacity`: `human_hours` and `agent_budget`. Two
numbers rather than one because agent throughput is bounded by spend and concurrency, not by
hours in a day — a sprint can be human-capacity-full and agent-capacity-empty at the same time,
and planning needs to show that.

**Burndown** splits the remaining line by assignee type (human-assigned vs agent-assigned
remaining). A single blended line hides the most decision-relevant fact in a mixed team: whether
the sprint is on track *because* of agent throughput, which tells you something very different
about risk than the same trajectory achieved by people.

**Scope change** mid-sprint is recorded rather than silently absorbed, so velocity and the sprint's
ROI rollup stay honest.

**Close** snapshots velocity and triggers the sprint ROI rollup
([`roi-analytics.md`](roi-analytics.md) §5).

---

## 4. Kanban

No sprints. WIP limits per status column, pull-based flow, and cycle-time/throughput metrics
instead of velocity. This is the natural mode for the operational ticket types — an incident queue
has no meaningful sprint boundary — and it is frequently the mode for a project that exists mainly
to receive event-triggered agent work.

---

## 5. Hybrid

A `Sprint` with a non-null `phase_id` sits inside a phase. A ticket in that sprint therefore rolls
up to **both** the sprint's burndown and the phase's percent-complete, with no double entry and no
reconciliation step.

```mermaid
gantt
    title Hybrid project — phases containing sprints
    dateFormat YYYY-MM-DD
    section Discovery
    Discovery phase        :done, d1, 2026-01-05, 30d
    Gate: Discovery Signoff:milestone, done, 2026-02-04, 0d
    section Build
    Sprint 1               :active, s1, 2026-02-05, 14d
    Sprint 2               :s2, after s1, 14d
    Sprint 3               :s3, after s2, 14d
    Gate: Code Freeze      :milestone, 2026-03-19, 0d
    section UAT
    UAT phase              :u1, 2026-03-20, 21d
    Gate: Go-Live Approval :milestone, 2026-04-10, 0d
```

The governance layer (phases, gates, baseline) answers to the programme; the delivery layer
(sprints, burndown) answers to the team. Neither has to fake the other's artefacts.

---

## 6. Switching Modes

Changing `delivery_mode` on a live project is allowed, with explicit migration rules rather than
silent reinterpretation:

| Change | What happens |
|---|---|
| `agile` → `hybrid` | Existing sprints are retained and must be assigned to a phase (or placed in a default "Delivery" phase) |
| `waterfall` → `hybrid` | Phases retained; sprints may then be created inside them |
| any → `kanban` | Sprints/phases are archived, not deleted; their tickets move to the backlog retaining history |
| `kanban` → `agile` | Tickets stay in the backlog until pulled into a first sprint |

Archived containers keep their `ActivityEvent` history and their contribution to past ROI rollups
— a mode change never rewrites what already happened.

---

## 7. How the Harness Sees Delivery Mode

Almost not at all, deliberately. `TriggerRule.filter` can scope by `phase_ids` or `sprint_ids`
(see [`agent-harness.md`](agent-harness.md) §2), but the harness works *tickets*, and a ticket
looks the same whichever container it sits in. This is what keeps one harness integration working
across all four modes rather than needing methodology-specific logic.

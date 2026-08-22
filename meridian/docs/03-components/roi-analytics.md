# Component: ROI & Benefit Analytics

> Builds on [`02-data-model.md`](../02-data-model.md) (`RoiBaseline`, `RoiSummary`, `CostEntry`) and
> [ADR-0004](../adr/0004-roi-attribution-model.md) for the attribution rules this section applies.

---

## 1. What Gets Measured, Per Ticket

Every ticket accrues, over its execution trail:

- **Cost.** Sum of `CostEntry` across every leg — agent runs (token/API cost from the agent's
  cost report on `run-completed`) and human time (hours logged or inferred from leg duration ×
  the assignee's configured hourly rate).
- **Cycle time.** Wall-clock from ticket creation (or from `Ready`, configurable) to entering the
  `done` status category.
- **Quality signals.** Rework count (how many times the ticket re-entered `In Progress` from
  `In Review`), human edit distance on agent-produced artifacts (§5 of
  [`human-ai-collaboration.md`](human-ai-collaboration.md)), and review pass/fail count.

These roll into one `RoiSummary` per ticket, computed on completion and recomputable if a
baseline changes.

---

## 2. Baselines: What Would This Have Cost Without AI?

ROI needs a denominator — "compared to what?" `RoiBaseline` is derived one of two ways, chosen per
project or per ticket type:

| Source | How it's computed | Best for |
|---|---|---|
| `historical_velocity` | Average cost/time of the **last N human-only tickets** of the same type in this project (before any agent was installed, or from tickets explicitly run human-only for calibration) | Projects with enough history |
| `manual_estimate` | PM enters an explicit estimate at project setup ("a ticket like this normally takes a consultant 4 hours at $150/hr") | New projects, or ticket types with too little history to average |

A baseline is a **snapshot at the time it's applied** (`RoiSummary.baseline_cost_used`) — if the
baseline is later revised, past `RoiSummary` rows are not silently rewritten; a recompute is an
explicit, logged action, so historical ROI reporting stays reproducible.

---

## 3. The ROI Formula

For a completed ticket:

```
roi_pct     = (baseline_cost - total_cost) / total_cost
time_saved  = baseline_hours - actual_human_hours
```

`actual_human_hours` counts only human legs' time — an agent-only ticket has `actual_human_hours
≈ 0`, so `time_saved ≈ baseline_hours`, reflecting that no human time was spent at all (the
`autonomy_level` field, `fully_autonomous`, is exactly this case).

For a **co-assigned or handed-off** ticket spanning multiple legs, `total_cost` and
`actual_human_hours` are sums across `attributed_legs` — see §4.

---

## 4. Attribution Across Multiple Actors

A ticket touched by three agents and one human reviewer needs its cost/benefit split across all
four, not credited wholesale to whichever leg closed it. Per [ADR-0004](../adr/0004-roi-attribution-model.md),
attribution is by **actual time and cost contribution per leg**:

```
attributed_legs[i].cost_share = CostEntry sum for leg i / total_cost
attributed_legs[i].time_share = leg i duration / total_cycle_time
```

This lets a portfolio-level report answer both "how much did AI save us" (sum `roi_pct`-weighted
savings across all tickets) and "which agents/humans are actually doing the work" (sum
`cost_share` per actor across tickets) without double-counting a ticket's benefit across every
actor who touched it.

---

## 5. Dashboards

| Level | Shows |
|---|---|
| **Ticket** | Its own `RoiSummary`: cost, time saved, baseline used, per-leg attribution, autonomy level |
| **Sprint** | Aggregate $ saved, hours saved, ticket count by `autonomy_level`, cost per ticket type, sprint velocity vs. agent throughput split (feeds off the burndown split in [`timeline-and-sprints.md`](timeline-and-sprints.md) §3) |
| **Project** | Trend over time (ROI improving/degrading per sprint), cost per ticket type, agent vs. human cost mix |
| **Portfolio / Workspace** | Cross-project rollup: total $ saved, total hours saved, top-performing agents by ROI contribution, tickets stuck in `fully_autonomous` failure (high handoff/rejection rate — a signal an agent is mis-scoped, cross-referenced with [`agent-marketplace.md`](agent-marketplace.md) §5 trust signals) |

All dashboards are scoped by the RBAC roles in [`permissions-rbac.md`](permissions-rbac.md) — a
`viewer` sees rollups, not necessarily per-ticket cost detail if the workspace configures cost
visibility as PM/admin-only (common in consulting contexts where cost data is sensitive even
internally).

---

## 6. Handling Missing or Uncertain Data

- **Agent cost not reported** (a manifest that doesn't report token/cost detail): `CostEntry` is
  recorded with `kind = agent_run` and `amount = null`; the ticket's `RoiSummary` is flagged
  `cost_unavailable` rather than silently computed as zero-cost, which would inflate ROI
  incorrectly (overview SC-6).
- **No baseline configured**: `RoiSummary` still records actual cost/time, but `roi_pct` and
  `time_saved` are left null with a `baseline_missing` flag — the dashboard shows raw cost/time
  data without fabricating a comparison.
- **Ticket abandoned/cancelled**: no `RoiSummary` is computed; cost incurred up to cancellation is
  still retained in `CostEntry` for cost accounting, surfaced separately as "sunk cost on
  cancelled work," not blended into completed-ticket ROI averages.

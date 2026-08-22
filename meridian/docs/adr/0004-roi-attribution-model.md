# ADR-0004: Attribute ROI by Time/Cost Share Across Execution Legs

## Status
Accepted

## Context
A ticket can be worked by several actors in sequence (handoffs) or in parallel (co-assignment).
"How much did AI save us" needs an answer that's both (a) correct in aggregate — total attributed
cost across all legs must equal total ticket cost — and (b) useful at the actor level — a
workspace admin wants to know which specific agents are actually driving savings, not just a
per-ticket blended number.

## Decision
Attribute a ticket's cost and time to each `ExecutionLeg` by that leg's **actual share** of total
cost and total cycle time (see [`roi-analytics.md`](../03-components/roi-analytics.md) §4):

```
cost_share[leg] = CostEntry sum for leg / total_cost
time_share[leg] = leg duration / total_cycle_time
```

This is computed and stored per ticket in `RoiSummary.attributed_legs`, not derived on the fly at
dashboard-query time, so historical rollups stay stable even if, e.g., an agent's later
`CostEntry` reporting behavior changes.

## Alternatives Considered
- **Credit the whole ticket to whichever leg closed it.** Rejected: this would make a human
  reviewer who approves a ticket after three agent legs look like they "did" the whole ticket in
  portfolio rollups, and conversely make an agent that did 90% of the work but handed off for a
  final human sign-off show zero credit — actively misleading for the exact "which agents are
  worth their license fee" decision the marketplace trust signals exist to support.
- **Credit the whole ticket to every leg (no splitting).** Rejected: this would make
  `sum(attributed cost across legs)` exceed actual total cost whenever a ticket has more than one
  leg, breaking the portfolio-level "total $ spent" number, which must reconcile with actual
  billing.

## Consequences
- Every `RoiSummary` computation must have complete `CostEntry` data for every leg before it can
  produce trustworthy attribution; a leg with `cost_unavailable` (see
  [`roi-analytics.md`](../03-components/roi-analytics.md) §6) degrades that ticket's attribution
  precision, which is surfaced explicitly rather than silently averaged over.
- Marketplace-level agent trust signals (aggregate ROI contribution per agent, per
  [`agent-marketplace.md`](../03-components/agent-marketplace.md) §5) can be computed by summing
  `cost_share`-weighted savings per agent across all tickets it touched, with the reconciliation
  guarantee from this ADR making that sum meaningful rather than double-counted.

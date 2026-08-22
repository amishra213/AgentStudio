# Component: Token, Cost, Efficiency & ROI Analytics

> Goal **G10**. Builds on [`02-data-model.md`](../02-data-model.md) (`UsageRecord`, `CostEntry`,
> `UsageRollup`, `EfficiencyMetric`, `Budget`, `RoiBaseline`, `RoiSummary`) and
> [ADR-0004](../adr/0004-roi-attribution-model.md).

---

## 1. Where Meridian Sits Relative to the Harness

A harness like OpenHands already tracks cost and tokens **inside a run**: per step, per tool call,
per message. Duplicating that would make Meridian a second, worse observability platform for
something it does not execute. Meridian's job is the layer the harness cannot see — the one that
spans runs, tickets, sprints, phases, projects and portfolios, and that knows what the work was
*for*.

| Layer | Owner | Granularity | Answers |
|---|---|---|---|
| Step / tool call | **Harness** | Per agent step | "Why did this run cost $4?" |
| Model invocation | **Meridian** (`UsageRecord`) | Per inference | "How many tokens did this leg burn, and how much was cached?" |
| Execution leg | **Meridian** (`CostEntry`) | Per actor's unit of work | "What did this agent's turn cost, in model + MCP + human time?" |
| Ticket | **Meridian** (`RoiSummary`) | Per work item | "What did this ticket cost vs. what it would have cost?" |
| Sprint / phase | **Meridian** (`UsageRollup`) | Per period | "Are we inside budget this sprint?" |
| Project / portfolio | **Meridian** (`UsageRollup`, `EfficiencyMetric`) | Per programme | "Is AI actually paying for itself here?" |

The join is `harness_run_id` + `harness_step_id` on every `UsageRecord`, so a project-level number
drills all the way down to a specific step in the harness's own UI without Meridian storing the
trace. Each system keeps what it is best placed to keep.

---

## 2. Token Accounting

`UsageRecord` captures one row per model invocation:

- `tokens_in` / `tokens_out`
- `cache_read_tokens` / `cache_write_tokens` — tracked separately, not folded into `tokens_in`
- `reasoning_tokens` where the provider reports them
- `unit_prices` — **a snapshot of the rates applied at the time**, so a later price change never
  silently rewrites historical cost
- `computed_cost` — derived, stored

Cache tokens get first-class treatment because prompt caching is usually the largest single lever
on agent unit economics: two profiles with identical token counts can differ severalfold in cost
purely on cache behaviour, and a blended `tokens_in` figure hides that completely. `cache_hit_ratio`
is therefore a headline efficiency metric, not a footnote.

Tokens roll up on exactly the same scope ladder as money, so "tokens per ticket" and "tokens per
story point" are available at project level without a separate pipeline.

---

## 3. Cost Tracking

Three cost sources, kept separate all the way up the ladder:

| Kind | Source |
|---|---|
| `agent_model` | Inference — summed from `UsageRecord` |
| `mcp_call` | Metered MCP server usage — summed from `McpCallRecord.cost` |
| `human_time` | Hours × the assignee's configured rate |

Keeping the split intact through every rollup is what makes the numbers actionable. A project
running hot might be paying for reasoning, for an expensive metered vendor server called too
often, or for human rework — three completely different fixes, indistinguishable in a single
"AI spend" figure.

### Rates and currency

Human rates are configurable per user, per role, or per project (blended rates are common in
consulting). Model rates come from the `unit_prices` snapshot. Everything converts to the
workspace's `default_currency` at the rate in force when the cost was recorded, so historical
totals don't move with FX.

---

## 4. Efficiency Metrics

`EfficiencyMetric` is computed at every scope — ticket, sprint, phase, project, portfolio, agent
profile, and MCP installation:

| Metric | Definition | What it tells you |
|---|---|---|
| `cost_per_ticket` / `tokens_per_ticket` | Totals ÷ tickets completed | Baseline unit economics |
| `cost_per_story_point` / `cost_per_hour_saved` | Normalised by work size | Comparable across teams doing differently-sized work |
| `first_pass_yield` | Share completed with no rework and no rejected approval | The quality number that actually predicts trust |
| `rework_rate` | Returns from review/blocked per completed ticket | Where cost is being spent twice |
| `handoffs_per_ticket` | Mean hop count | Routing quality; rising values mean profiles are mis-scoped |
| `cache_hit_ratio` | `cache_read_tokens / tokens_in` | The main cost lever (§2) |
| `autonomy_mix` | Share by `fully_autonomous` / `human_assisted` / `human_only` | Adoption, and usually more actionable than headline ROI |
| `denied_call_rate` | Share of `denied_by_policy` MCP calls | Mis-scoped **grants**, not bad agents — a policy fix, not a model fix |

The last row is the one that most often prevents a wrong conclusion: a profile with poor
completion rates and a high denied-call rate is not failing at reasoning, it is being asked to do
work it holds no grant for. Separating those diagnoses is the difference between revoking a useful
profile and adjusting one line of policy.

Metrics are materialised (`UsageRollup` → `EfficiencyMetric`), recomputed incrementally as legs
close and as periods roll over, so a portfolio dashboard never aggregates millions of raw rows on
page load.

---

## 5. ROI at Task Level

Per ticket, on completion:

```
roi_pct    = (baseline_cost - total_cost) / total_cost
time_saved = baseline_hours - actual_human_hours
```

`actual_human_hours` counts human legs only, so a `fully_autonomous` ticket saves essentially the
whole baseline.

### Baselines — compared to what?

This is where AI-ROI reporting usually goes wrong, so the mechanism is specified defensively.

| Source | Method | Best for |
|---|---|---|
| `holdout_sample` | A randomised share of eligible tickets is deliberately routed **human-only**; their cost/time is the live control. The default and the only source that survives scrutiny | Any project with steady ticket flow |
| `historical_velocity` | Mean cost/time of comparable human-only tickets **within the same complexity stratum** (§5.1) | Projects with history but no appetite for a holdout |
| `manual_estimate` | An explicit PM figure ("a change like this takes a consultant 4h at $150/h") | New projects; types with too little history |

#### 5.1 Selection bias is the default failure mode

Agents get the tractable work. Trigger rules select on type, status, labels and severity — which
correlate strongly with difficulty — so the tickets agents complete are systematically easier than
the population a naive `historical_velocity` baseline averages over. Comparing them yields a
flattering number that is simply wrong, and it is wrong in the direction everybody wants to
believe.

Three controls, in order of strength:

1. **Holdout sampling (default).** `RoiBaseline.holdout_pct` (default 10%) routes a random share of
   *otherwise-eligible* tickets to humans. Randomisation is at the point of eligibility, after the
   trigger filter matches, so the control group is drawn from exactly the population the agent
   would have worked. This is the only construction that supports a causal claim.
2. **Complexity stratification.** Where no holdout is run, baselines are computed per stratum
   (`estimate` band × ticket type × priority) and a ticket is compared only against its own
   stratum. `RoiBaseline.stratum_key` records which was used.
3. **Comparability flagging.** If an agent-completed ticket has no populated stratum with at least
   `min_sample` (default 5) human comparators, its `RoiSummary` is flagged
   `baseline_low_confidence` and excluded from headline rollups — reported separately rather than
   silently averaged in.

Rollups carry the resulting quality band (`baseline_quality: holdout | stratified | unstratified |
estimate_only`) so a reader knows what the number is worth. A dashboard that cannot say how its
baseline was constructed should not be shown to a CFO.

#### 5.2 Snapshots

Baselines are **snapshotted** onto each `RoiSummary` (`baseline_cost_used`). Revising a baseline
never silently rewrites past summaries; recomputation is explicit and logged, so a quarter's
reported ROI stays reproducible. Without a live holdout, a baseline also ages into the pre-AI era
and reported ROI inflates over time for no real reason — which is why the holdout is the default.

---

## 5A. Waste, Abandonment, and Negative Outcomes

An ROI system that can only record successes is a marketing instrument. The cases that matter most
are the ones where agent involvement **cost more than it returned**, and they must be first-class
rather than absorbed into averages.

| Case | How it is recorded |
|---|---|
| Agent attempted, rejected, human redid the work | Agent legs' cost is retained and tagged `wasted_cost`; ticket `autonomy_level` is `human_only_after_agent_attempt`, *not* `human_assisted` |
| Agent completed, human reverted or reworked substantially | Cost of the superseded leg tagged `wasted_cost`; `rework_rate` incremented |
| Handoff chain escalated on a guardrail | All legs before escalation tagged `wasted_cost` unless their artifacts were actually used |
| Ticket cancelled after agent work | Costs retained, reported as sunk cost on cancelled work, excluded from completed-ticket averages |

Consequences for reporting:

- **`net_savings = Σ(baseline_cost) − Σ(total_cost)` is computed over *all* agent-touched tickets,
  including the failures.** A rollup that silently drops rejected attempts overstates savings by
  exactly the amount that matters most.
- **`waste_ratio = wasted_cost / total_agent_cost`** is a headline metric alongside ROI. A rising
  waste ratio with flat ROI means the wins are subsidising an increasing number of failed attempts.
- **Negative-ROI tickets are reported, not clipped.** `roi_pct` may be negative; rollups show the
  distribution, not only the mean, because a mean over a long tail of small wins and a few large
  losses is uninformative.

This is also what makes shadow mode ([`agent-harness.md`](agent-harness.md) §3A) valuable: it
produces the counterfactual without spending real budget on failures.

### Attribution across legs

Per [ADR-0004](../adr/0004-roi-attribution-model.md), a ticket touched by three agents and a human
reviewer splits cost and effort by actual contribution.

**Elapsed time and effort are different quantities and must not be conflated.** An agent leg is
usually wall-clock-bounded and effort-equals-elapsed. A human leg is not: a reviewer who holds a
ticket for three days and spends forty minutes on it has an elapsed of 3d and an effort of 0:40.
Attributing by elapsed would inflate human contribution roughly by the ratio of working hours to
calendar hours — and correspondingly understate every agent on the ticket.

Each `ExecutionLeg` therefore carries both:

| Quantity | Agent leg | Human leg |
|---|---|---|
| `elapsed` | claim → terminal outcome | assignment → terminal outcome |
| `effort` | equals `elapsed` minus time blocked on a human answer | logged time, or `elapsed` clamped to the project's working calendar **and** to a configured `max_inferred_effort` per leg (default 25% of elapsed), flagged `effort_inferred` |

```
cost_share[leg]   = CostEntry sum for leg / total_cost
effort_share[leg] = leg effort / Σ(leg effort)
```

Cycle time remains reported separately at ticket level — it answers "how long did this take to get
done", which is a genuinely different question from "who did the work" and should never be used as
a proxy for it.

Where `effort_inferred` is set on any leg, the ticket's attribution is flagged as estimated. Turning
on required time tracking ([`project-administration.md`](project-administration.md) §4) is what
converts these into measured values; organisations that decline to do so get attribution with a
stated error bar rather than a false precision.

Shares are stored, not recomputed at query time. The sum across legs equals the ticket total,
which is what lets portfolio spend reconcile with actual billing while per-agent contribution
stays meaningful.

---

## 6. ROI at Project and Portfolio Level

Project ROI is **not** simply the mean of its tickets' `roi_pct` — that would over-weight cheap
tickets. It is computed from summed totals:

```
project_roi_pct = (Σ baseline_cost - Σ total_cost) / Σ total_cost
```

Alongside it, the project view reports:

- **Spend vs. budget** — burn against the project `Budget`, with a projected end-of-period figure
- **Cost split** — model / MCP / human, trended across sprints or phases
- **Hours returned** — total `time_saved`, and what that represents in FTE terms
- **Autonomy trend** — is the `fully_autonomous` share growing?
- **Efficiency trend** — `cost_per_ticket` and `first_pass_yield` over time; improving unit
  economics matter more than a single good quarter
- **Coverage** — share of tickets that were even *eligible* for agent pickup, which bounds how much
  ROI is achievable and is usually the real constraint early on

Portfolio level adds cross-project comparison, top agent profiles by contributed savings, top MCP
installations by cost, and outlier projects whose efficiency is diverging.

Phase- and gate-level rollups exist for waterfall programmes, so a gate review can include cost to
date against phase budget as a first-class artefact rather than an exported spreadsheet.

---

## 7. Budgets and Enforcement

`Budget` attaches at workspace, project, phase, or sprint scope with `alert_thresholds` and an
`on_breach` behaviour:

| `on_breach` | Effect |
|---|---|
| `warn` | Notify budget owners at each threshold; work continues |
| `block_agent_dispatch` | No new agent runs start; in-flight runs finish; humans unaffected |
| `block_all_agent_work` | In-flight runs are halted at their next checkpoint and legs close as `budget_exceeded` |

Checks run **before dispatch** and **on each cost report during a run**, so a single expensive run
cannot blow through a ceiling between checks. Budgets compose: the tightest applicable ceiling
across workspace, project, phase/sprint, and agent profile wins. `token_ceiling` can be set
independently of money for organisations that prefer to govern consumption directly.

A breach is always visible and attributable — which budget, which scope, which tickets were
stopped — never a silent slowdown.

---

## 8. Missing and Uncertain Data

Reporting honestly about gaps beats a clean number that is wrong:

- **Usage not reported by the harness** → `CostEntry` recorded with `amount = null`, summary
  flagged `cost_unavailable`. Never treated as zero, which would inflate ROI.
- **No baseline configured** → actual cost and time still recorded; `roi_pct` and `time_saved` left
  null with `baseline_missing`. The dashboard shows real data rather than a fabricated comparison.
- **Ticket cancelled** → no `RoiSummary`; costs are retained and reported separately as sunk cost
  on cancelled work, not blended into completed-ticket averages.
- **Period closed mid-leg** → the leg's cost rolls into the next period rather than retroactively
  altering a closed period's reported figures.
- **Provider pricing changed** → historical records keep their `unit_prices` snapshot; only future
  usage prices at the new rate.

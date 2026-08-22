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

| Source | Method | Best for |
|---|---|---|
| `historical_velocity` | Mean cost/time of the last N **human-only** tickets of this type in this project — from before agents were enabled, or from tickets deliberately run human-only for calibration | Projects with history |
| `manual_estimate` | An explicit PM figure ("a change like this takes a consultant 4h at $150/h") | New projects; types with too little history |

Baselines are **snapshotted** onto each `RoiSummary` (`baseline_cost_used`). Revising a baseline
never silently rewrites past summaries; recomputation is explicit and logged, so a quarter's
reported ROI stays reproducible.

Keeping a small human-only control stream running deliberately is the honest way to keep
`historical_velocity` current. Otherwise the baseline ages into the pre-AI era and reported ROI
inflates over time for no real reason — the most common way these numbers become fiction.

### Attribution across legs

Per [ADR-0004](../adr/0004-roi-attribution-model.md), a ticket touched by three agents and a human
reviewer splits cost and time by actual contribution:

```
cost_share[leg] = CostEntry sum for leg / total_cost
time_share[leg] = leg duration / total_cycle_time
```

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

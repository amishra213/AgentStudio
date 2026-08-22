# Design Critique and Open Issues

> **Reading order position:** 9 of 10. An adversarial review of this design against itself.
> Findings marked **Fixed** have been applied to the specs; **Open** items are known and
> deliberately unresolved, with the reasoning recorded so they are not rediscovered as surprises.

A design document that contains no admitted weaknesses is either trivial or dishonest. This one
records both the defects found on review and the ones consciously accepted.

---

## Severity Key

| | Meaning |
|---|---|
| **Critical** | Would produce materially wrong behaviour or wrong numbers in normal operation |
| **High** | Will be hit in the first real deployment |
| **Medium** | Real, but survivable with a workaround |

---

## Critical — Fixed

### C1 · ROI baselines were vulnerable to selection bias
**Was:** `historical_velocity` compared agent-completed tickets against an average over *all*
human-completed tickets of that type.

**Why wrong:** trigger rules select on type, status, label and severity, all of which correlate
with difficulty. Agents therefore work systematically easier tickets than the baseline population,
and the comparison flatters them by an unknown margin. This is the single most likely route to
Meridian's headline number being fiction — and it fails in the direction everyone wants to believe,
so nobody checks it.

**Fixed:** holdout sampling is now the default baseline source — a randomised share of *eligible*
tickets is routed human-only, drawn from exactly the population the agent would have worked.
Complexity stratification and a `min_sample` confidence floor back it up, and every rollup carries
a `baseline_quality` band. → [`roi-analytics.md`](03-components/roi-analytics.md) §5.1

### C2 · Failed agent attempts were scored as successes
**Was:** a ticket where an agent burned budget, gave up, and a human redid the work was recorded as
`human_assisted` with its agent cost quietly folded into the total.

**Why wrong:** the failure case is the one that determines whether an AI programme is actually
worth running. Absorbing it into a mean over successes is how a negative-ROI deployment reports
positive ROI.

**Fixed:** `wasted_cost` on legs, a distinct `human_only_after_agent_attempt` autonomy level, a
`waste_ratio` headline metric, and rollups that report the **distribution** of `roi_pct` including
negatives rather than only the mean. → [`roi-analytics.md`](03-components/roi-analytics.md) §5A

### C3 · Attribution conflated elapsed time with effort
**Was:** `time_share[leg] = leg duration / total_cycle_time`.

**Why wrong:** an agent leg's elapsed ≈ its effort. A human leg's does not — a reviewer holding a
ticket three days and spending forty minutes would be credited three days. Human contribution was
therefore inflated by roughly the calendar-to-working-hours ratio, and every agent on the ticket
correspondingly understated. Since these shares drive per-actor ROI, the numbers used to judge
agents were biased against them by construction.

**Fixed:** `ExecutionLeg` carries `elapsed` and `effort` separately; only `effort` drives
attribution; inferred effort is flagged and capped. Cycle time is reported separately as its own
metric. → [ADR-0004](adr/0004-roi-attribution-model.md), [`roi-analytics.md`](03-components/roi-analytics.md) §5

### C4 · Ask-human paused the customer-facing SLA clock
**Was:** `ask_human` moved the ticket to a `blocked`-category status, and blocked-category statuses
paused the SLA clock.

**Why wrong:** an agent asking your own team a question is an *internal* dependency. Pausing a
customer commitment for it means resolution SLA improves precisely when your automation gets stuck
— a metric that rewards the wrong outcome and is trivially gameable once anyone notices.

**Fixed:** two SLA clock classes (`external` / `internal`); ask-human pauses neither, and its wait
is attributed to `blocked_on_internal` so the cost stays visible without laundering the commitment.
→ [`ticketing.md`](03-components/ticketing.md) §1

### C5 · The handoff bundle defeated field-level redaction
**Was:** field `sensitivity` filtered agent payloads, but `HandoffEvent.context_bundle.summary` is
**prose written by the handing-off agent** after reading those fields, and was passed to the next
agent unexamined.

**Why wrong:** a two-hop handoff silently launders every `secret` field into plain text, defeating
the entire field-sensitivity mechanism. Payload filtering is meaningless if the model can restate
the payload in a field nobody filters.

**Fixed:** bundles carry a clearance label; delivery to a lower-clearance recipient triggers
regeneration under a redaction constraint or escalation to a human. Because regeneration is itself
a model call and cannot be guaranteed, the stronger control is stated plainly: don't configure
cross-clearance handoff targets for types with `secret` fields, and the admin UI flags such
configurations. → [`agent-harness.md`](03-components/agent-harness.md) §7

---

## High — Fixed

### H1 · No shadow or propose mode
There was no way to introduce an agent into a live tracker without letting it write. That makes the
first deployment also the first incident, and it removes the cheapest source of the counterfactual
data C1 needs.

**Fixed:** three execution modes — `shadow` (read-only, output stored and scored against what the
human subsequently did), `propose` (output as a proposal, no writes), `autonomous`. Shadow spend is
reported as evaluation cost, not charged against delivery ROI.
→ [`agent-harness.md`](03-components/agent-harness.md) §3A

### H2 · Agent profiles were unversioned
Changing a profile's model or policy silently changed what "Agent X's ROI trend" was measuring.

**Fixed:** `AgentProfileVersion`, referenced by every `ExecutionLeg`; trends plot per version with
change markers, and shadow-vs-live becomes the natural A/B.
→ [`agent-harness.md`](03-components/agent-harness.md) §3B

### H3 · No circuit breaker on a failing profile
MCP *installations* could be marked degraded, but a profile that was connected and simply wrong
about everything would keep taking tickets.

**Fixed:** auto-pause on rolling-window thresholds for rejection rate, denied-call rate, handoff
rate, override rate, and cost deviation — each naming the tripped condition, since these have
different causes and different fixes.
→ [`agent-harness.md`](03-components/agent-harness.md) §3C

### H4 · Visibility-filtered financial rollups did not reconcile
Excluding confidential tickets from cost rollups means two viewers see different project totals and
neither matches the invoice; including them leaks the existence and size of confidential work.

**Fixed** by choosing per surface rather than pretending the tension away: operational views are
strictly filtered; financial rollups are computed unfiltered and shown only to holders of
`view_full_cost`, and withheld entirely otherwise. A filtered financial total is worse than none,
because it looks authoritative and is silently wrong. Budget enforcement always uses the unfiltered
figure.
→ [`permissions-rbac.md`](03-components/permissions-rbac.md) §7

### H5 · No working calendars or timezones
SLA targets and waterfall date maths were specified in wall-clock durations, which is wrong across
weekends, holidays, and regions.

**Fixed:** `WorkingCalendar` at workspace/project scope, referenced by SLA clocks, phase
scheduling, and human effort inference. → [`02-data-model.md`](02-data-model.md) §5

---

## Open — Accepted, Not Yet Resolved

### O1 · Prompt injection is mitigated, not solved · *Critical, inherent*
Grants bound what an injected agent can reach, and approval gates cover external and destructive
effects. But **within its granted, non-gated tool set, a successfully injected agent can act.**
This is a property of giving a model tools, not a gap in this design, and no amount of prompting
closes it. The honest posture is default-closed grants, narrow tool allowlists, and detection after
the fact via `McpCallRecord`. Stated in [`06-security.md`](06-security.md) §4 and repeated here so
it is not mistaken for solved.

### O2 · Claim/lease versus human reassignment precedence is unspecified · *Medium*
If a human reassigns a ticket while an agent holds a live lease, the intended behaviour is
presumably "human wins, lease revoked, leg closed" — but the interaction with an in-flight MCP call
that has already had external effect is not specified. Needs a decision on whether revocation is
immediate or at the next checkpoint.

### O3 · Grant revocation mid-session relies on unspecified propagation · *Medium*
`capabilities.list` resolves grants per ticket, and enforcement re-validates on every call, so
revocation is *enforced* correctly. But a harness holding a long-lived MCP session may keep
offering the model a stale tool list, producing avoidable denied calls. MCP's
`notifications/tools/list_changed` is the obvious mechanism; the propagation contract is not
written down. → [`04-api-contracts.md`](04-api-contracts.md) §1

### O4 · `cost_per_story_point` is undefined for two of three estimate modes · *Medium*
Projects may use points, hours, or no estimates. The metric is specified as though points always
exist. Needs either a per-project normalisation choice or explicit suppression of the metric where
no estimate unit is configured.

### O5 · Attachments and files are not modelled · *Medium*
Referenced obliquely in the security doc's provenance discussion, but there is no entity, no size
or retention policy, and no statement of whether attachment content enters agent payloads. For
incident and change tickets this is not an edge case — logs and screenshots are the primary
evidence.

### O6 · Concurrent human and agent writes to the same ticket · *Medium*
Co-assignment permits a human editing while an agent's leg is open. Lease tokens protect
agent-versus-agent, not human-versus-agent. Field-level conflict resolution is unspecified;
last-write-wins is the likely default and is probably wrong for `description` and
`acceptance_criteria`.

### O7 · Portfolio membership is assumed exclusive · *Low*
If a project belongs to two portfolio groups, its cost is counted in both. Fine for viewing,
wrong for any summed total across portfolios. Needs either an exclusivity constraint or explicit
de-duplication at rollup.

### O8 · Timeline aggregation under per-user visibility filtering is expensive · *Medium*
Server-side timeline aggregation was specified for performance, but the visibility predicate is
per-user, so aggregates cannot be cached per project — the natural cache key is
`(project, time-bucket, viewer's visibility set)`. For large portfolios this may not hold up.
Likely resolution is caching per *visibility class* rather than per user, but that requires
classes to be coarse enough to be reusable and is unproven here.

### O9 · No evaluation of agent output against acceptance criteria · *High for adoption*
Quality signals are all indirect — human edit distance, rejection rate, override rate. None checks
the artifact against the ticket's own `acceptance_criteria`. Shadow mode (H1) makes this tractable
by producing scoreable output cheaply, but the scoring mechanism itself is not designed.

---

## Structural Observations

Three things about the design as a whole rather than any one part:

1. **The record/execution split is the load-bearing decision.** Most of what makes this design
   coherent — swappable harness, capability-as-configuration, server-side enforcement, auditability
   — follows from Meridian never executing agent logic. If that boundary is ever crossed for
   expedience (e.g. Meridian "just" doing routing to save a round trip), most of the above
   unravels. It should be treated as an invariant, not a preference.

2. **The grant set is doing more security work than it looks.** Because routing is model-driven,
   grants are not one control among several — they are the *only* boundary between a reasoning
   system and the organisation's tools. That justifies their cost: tool-level rather than
   server-level, default-closed, re-validated per call, and separate from enablement. Any pressure
   to simplify them (server-level grants, grant-on-enable) should be read as pressure to remove the
   security model.

3. **The ROI feature is the most likely thing to be quietly wrong.** C1, C2 and C3 were all in this
   area, all produced numbers biased in the same flattering direction, and none would have thrown
   an error. The fixes help, but the standing risk is that these figures get quoted in a board deck
   long before anyone stress-tests how they were derived. The `baseline_quality` band and the
   `flags` array on `RoiSummary` exist so that a number always travels with its own caveats
   attached — they should never be dropped from a presentation layer for looking untidy.

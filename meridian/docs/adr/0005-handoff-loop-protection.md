# ADR-0005: Multi-Layer Handoff Loop Protection

## Status
Accepted

## Context
Overview G4 requires agents to hand off to each other without human intervention on the common
path — but an autonomous handoff chain with no circuit breaker can, in the worst case, bounce a
ticket between two mis-configured or genuinely mismatched agents indefinitely, burning budget and
never reaching a human who could actually fix the underlying mismatch. A single check (e.g., "no
more than 5 handoffs") is easy to reason about but can still let a slow-but-expensive loop run for
a long time before tripping, or let a fast-and-cheap loop spin many times before the hop count
alone would matter.

## Decision
Layer four independent checks at every handoff, per
[`agent-harness.md`](../03-components/agent-harness.md) §7, any one of
which is sufficient to force escalation to a human:

1. **Hop ceiling** (default 5) — bounds chain length outright.
2. **Cycle detection** — an actor appearing a second time in the same ticket's trail is allowed
   once (legitimate: an agent can reasonably get a ticket back after an intervening step), but a
   second repeat trips escalation regardless of hop count, catching short A↔B loops fast.
3. **Budget ceiling** — bounds cost exposure independent of chain length, catching an expensive
   agent looping even a small number of times.
4. **Wall-clock ceiling** — bounds elapsed time independent of cost, catching a cheap-but-slow loop
   (e.g., agents each waiting near their max response SLA) that neither of the above would catch
   quickly.

Any trip produces the same outcome: reassign to a human with a system comment naming exactly which
check fired and the data behind it (hop count, repeat actor, cost so far, elapsed time) — see
[`05-sequence-flows.md`](../05-sequence-flows.md) Flow 3.

## Alternatives Considered
- **Hop ceiling only.** Rejected as insufficient on its own per the scenarios above — a low ceiling
  hurts legitimate long chains (e.g., a five-stage document pipeline), a high ceiling lets a loop
  run expensively before catching it.
- **Global handoff rate limit per workspace** (rather than per-ticket). Considered as a
  supplementary future control but rejected as the *primary* mechanism here: it protects workspace
  budget in aggregate but doesn't help a PM understand or fix any one specific stuck ticket, which
  is the actual failure mode being designed against.

## Consequences
- Configuring hop ceiling, budget ceilings, and wall-clock ceilings is exposed as project-level
  and installation-level settings (`AgentInstallation.budget_ceiling`, project-level hop/time
  config) rather than hardcoded, so a project with genuinely long legitimate pipelines can raise
  the hop ceiling deliberately, with the other three checks still providing a floor.
- Every escalation is fully explainable after the fact (per
  [`06-security.md`](../06-security.md) §5), which is what makes it safe to let handoff run
  unattended by default (overview G4) — the failure mode is "stops and asks a human with a clear
  reason," never "silently burns budget."

#!/usr/bin/env python3
"""Cost model for OpenHands context-management policies.

This is a *policy simulator*, not a harness around the OpenHands SDK. It
re-implements the trigger arithmetic of
``openhands.sdk.context.condenser.LLMSummarizingCondenser`` (as read at
software-agent-sdk @ 88afa9a) over a synthetic event stream so that the
per-request token cost of different condensation policies can be compared
without burning real API credits.

What is faithful to the source:

* Condensation fires when ``len(view) > max_size`` (soft) or when the token
  count of the view exceeds ``max_tokens`` (hard).
* On an event-count trigger the view keeps ``max_size // 2 - keep_first - 1``
  events from the tail; on a token trigger it drops the shortest prefix whose
  removal brings the view under ``max_tokens // 2``.
* ``keep_first`` events survive at the head, and one summary event is inserted
  at the cut point.
* The summarizer is fed a 500-character preview of each forgotten event
  (``N_CHAR_PREVIEW``), so its input is bounded by event *count*, not by event
  size.

What is modelled rather than measured:

* Event token sizes are drawn from a distribution chosen to resemble a coding
  session (mostly small events, a long tail of large tool observations clipped
  at the tool-level truncation caps).
* Prompt-cache accounting uses Anthropic-style multipliers: 0.1x for a cache
  read, 1.25x for a cache write, 1.0x for uncached input. Any condensation
  invalidates the whole prefix, because condensation rewrites the head of the
  message list.
* Rediscovery cost (the agent re-reading files whose contents were summarised
  away) is modelled as a configurable probability of an extra step after each
  condensation. This is the model's softest assumption and is reported
  separately.

Run: ``python3 openhands-context-cost-model.py``
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


# --------------------------------------------------------------------------
# Pricing / cache multipliers (Claude Sonnet-class list pricing, USD per token)
# --------------------------------------------------------------------------
INPUT_PRICE = 3.0 / 1_000_000
OUTPUT_PRICE = 15.0 / 1_000_000
CACHE_READ_MULT = 0.1
CACHE_WRITE_MULT = 1.25

CONTEXT_WINDOW = 200_000
SYSTEM_AND_TOOLS_TOKENS = 12_000  # system prompt + tool schemas, always resident
OUTPUT_TOKENS_PER_STEP = 700


# --------------------------------------------------------------------------
# Event-size distribution
# --------------------------------------------------------------------------
def sample_event_tokens(rng: random.Random) -> tuple[int, int]:
    """Return (action_tokens, observation_tokens) for one agent step.

    Actions are small (a thought plus tool arguments). Observations are
    heavy-tailed: most are short, but file reads and command output routinely
    hit the tool truncation caps (16k chars ~ 4k tokens for the file editor,
    30k chars ~ 7.5k tokens for the terminal).
    """
    action = rng.randint(60, 400)
    roll = rng.random()
    if roll < 0.55:
        observation = rng.randint(20, 400)      # short command / small edit
    elif roll < 0.85:
        observation = rng.randint(400, 2_500)   # a grep hit list, a small file
    elif roll < 0.97:
        observation = rng.randint(2_500, 4_000)  # file-editor cap
    else:
        observation = rng.randint(4_000, 7_500)  # terminal cap
    return action, observation


# --------------------------------------------------------------------------
# Policies
# --------------------------------------------------------------------------
@dataclass
class Policy:
    name: str
    max_size: int                     # event-count trigger
    keep_first: int
    token_trigger_ratio: float        # fraction of the window that fires condensation
    token_target_ratio: float         # fraction of the window to condense down to
    # Proposed mechanisms (all off for the as-shipped policies):
    observation_age_limit: int = 0    # steps after which an observation is digested
    observation_digest_tokens: int = 120
    isolated_step_fraction: float = 0.0  # chance a step opens a delegation
    delegated_unit_steps: int = 6     # steps absorbed by one delegation
    rediscovery_prob: float = 0.0     # extra steps caused by a lossy summary


@dataclass
class RunResult:
    policy: str
    steps: int
    condensations: int
    peak_context: int
    mean_context: int
    billed_input_tokens: float
    cost_usd: float
    cache_hit_rate: float
    extra: dict = field(default_factory=dict)


@dataclass
class _Event:
    tokens: int
    born_at: int
    is_observation: bool
    digested: bool = False

    def effective_tokens(self, now: int, policy: Policy) -> int:
        if (
            policy.observation_age_limit
            and self.is_observation
            and now - self.born_at > policy.observation_age_limit
        ):
            return min(self.tokens, policy.observation_digest_tokens)
        return self.tokens


def simulate(policy: Policy, steps: int, seed: int = 7) -> RunResult:
    rng = random.Random(seed)
    events: list[_Event] = []
    summary_tokens = 0  # the condensation summary event, if any

    billed = 0.0
    cache_hits = 0
    contexts: list[int] = []
    condensations = 0
    summariser_input_tokens = 0
    isolated_steps = 0
    rediscovery_steps = 0
    prev_context: int | None = None
    cache_valid = False

    step = 0
    remaining = steps
    while remaining > 0:
        step += 1
        remaining -= 1

        def view_tokens() -> int:
            return (
                SYSTEM_AND_TOOLS_TOKENS
                + summary_tokens
                + sum(e.effective_tokens(step, policy) for e in events)
            )

        # ---- condensation check (runs before the request, as in Agent.step)
        token_trigger = int(CONTEXT_WINDOW * policy.token_trigger_ratio)
        token_target = int(CONTEXT_WINDOW * policy.token_target_ratio)
        needs_condense = (
            len(events) > policy.max_size or view_tokens() > token_trigger
        )
        if needs_condense and len(events) > policy.keep_first + 2:
            # Feed the summariser a 500-char preview per forgotten event
            # (~130 tokens), as the real condenser does.
            if len(events) > policy.max_size:
                keep_tail = max(policy.max_size // 2 - policy.keep_first - 1, 1)
            else:
                keep_tail = 0
                running = SYSTEM_AND_TOOLS_TOKENS + summary_tokens
                for idx in range(len(events) - 1, -1, -1):
                    cost_of_event = events[idx].effective_tokens(step, policy)
                    if running + cost_of_event > token_target:
                        break
                    running += cost_of_event
                    keep_tail = len(events) - idx
                keep_tail = min(keep_tail, len(events) - policy.keep_first - 1)
                keep_tail = max(keep_tail, 1)

            head = events[: policy.keep_first]
            tail = events[len(events) - keep_tail :]
            forgotten = events[policy.keep_first : len(events) - keep_tail]
            if forgotten:
                condensations += 1
                preview_tokens = len(forgotten) * 130 + 400
                summariser_input_tokens += preview_tokens
                billed += preview_tokens  # uncached one-shot prompt
                summary_tokens = 900
                events = head + tail
                cache_valid = False
                if rng.random() < policy.rediscovery_prob:
                    rediscovery_steps += 1
                    remaining -= 1  # a step spent re-reading what was dropped

        # ---- the request itself
        context = view_tokens()
        contexts.append(context)

        if cache_valid and prev_context is not None:
            cached = min(prev_context, context)
            fresh = max(context - cached, 0)
            billed += cached * CACHE_READ_MULT + fresh * CACHE_WRITE_MULT
            cache_hits += 1
        else:
            billed += context * CACHE_WRITE_MULT
        cache_valid = True
        prev_context = context

        # ---- the step's own output, appended to the view
        action, observation = sample_event_tokens(rng)
        delegate = (
            policy.isolated_step_fraction
            and remaining > policy.delegated_unit_steps
            and rng.random() < policy.isolated_step_fraction
        )
        if delegate:
            # A delegation absorbs the next `delegated_unit_steps` units of work
            # into a sub-conversation that starts from an empty history. Those
            # steps are still billed, but against a context that begins at the
            # system-prompt baseline instead of the parent's accumulated one.
            # Only a short report lands in the parent view.
            k = policy.delegated_unit_steps
            remaining -= k
            isolated_steps += k
            sub_events = 0
            sub_prev: int | None = None
            for _ in range(k):
                sub_ctx = SYSTEM_AND_TOOLS_TOKENS + sub_events
                if sub_prev is None:
                    billed += sub_ctx * CACHE_WRITE_MULT
                else:
                    billed += (
                        sub_prev * CACHE_READ_MULT
                        + (sub_ctx - sub_prev) * CACHE_WRITE_MULT
                    )
                sub_prev = sub_ctx
                sub_a, sub_o = sample_event_tokens(rng)
                sub_events += sub_a + sub_o
            events.append(_Event(action, step, is_observation=False))
            events.append(_Event(rng.randint(200, 600), step, is_observation=True))
        else:
            events.append(_Event(action, step, is_observation=False))
            events.append(_Event(observation, step, is_observation=True))

    total_steps = len(contexts)
    cost = billed * INPUT_PRICE + total_steps * OUTPUT_TOKENS_PER_STEP * OUTPUT_PRICE
    return RunResult(
        policy=policy.name,
        steps=total_steps,
        condensations=condensations,
        peak_context=max(contexts),
        mean_context=int(sum(contexts) / len(contexts)),
        billed_input_tokens=billed,
        cost_usd=cost,
        cache_hit_rate=cache_hits / total_steps,
        extra={
            "summariser_input_tokens": summariser_input_tokens,
            "isolated_steps": isolated_steps,
            "rediscovery_steps": rediscovery_steps,
        },
    )


POLICIES = [
    Policy(
        name="A. Product default (settings.CondenserSettings)",
        max_size=240,
        keep_first=2,
        token_trigger_ratio=1.0,   # max_tokens = llm.effective_max_input_tokens
        token_target_ratio=0.5,    # condense down to max_tokens // 2
        rediscovery_prob=0.5,
    ),
    Policy(
        name="B. SDK preset default (default_condenser)",
        max_size=80,
        keep_first=4,
        token_trigger_ratio=1.0,
        token_target_ratio=0.5,
        rediscovery_prob=0.5,
    ),
    Policy(
        name="C. Token-budgeted condensation only",
        max_size=10_000,           # event count no longer the binding constraint
        keep_first=4,
        token_trigger_ratio=0.30,
        token_target_ratio=0.12,
        rediscovery_prob=0.5,
    ),
    Policy(
        name="D. C + observation ageing",
        max_size=10_000,
        keep_first=4,
        token_trigger_ratio=0.30,
        token_target_ratio=0.12,
        observation_age_limit=12,
        rediscovery_prob=0.25,     # digests keep a pointer, so less rediscovery
    ),
    Policy(
        name="E. D + sub-agent isolation",
        max_size=10_000,
        keep_first=4,
        token_trigger_ratio=0.30,
        token_target_ratio=0.12,
        observation_age_limit=12,
        isolated_step_fraction=0.12,
        rediscovery_prob=0.25,
    ),
]


def sweep(steps: int = 200, seeds: tuple[int, ...] = (1, 7, 13, 29, 101)) -> None:
    """Sweep the condensation trigger/target thresholds.

    Condensing earlier lowers the mean context (cheaper requests) but costs a
    prompt-cache reset and a summariser call each time. The sweep locates the
    trade-off point under this model's assumptions.
    """
    print("\nThreshold sweep (no ageing, no isolation) — cost in USD\n")
    targets = [0.08, 0.12, 0.20, 0.30, 0.50]
    print(f"{'trigger':>9}" + "".join(f"{f'target {t:.0%}':>13}" for t in targets))
    for trigger in (0.20, 0.30, 0.40, 0.55, 0.75, 1.00):
        row = f"{trigger:>9.0%}"
        for target in targets:
            if target >= trigger:
                row += f"{'-':>13}"
                continue
            p = Policy(
                name="sweep",
                max_size=10_000,
                keep_first=4,
                token_trigger_ratio=trigger,
                token_target_ratio=target,
                rediscovery_prob=0.5,
            )
            cost = sum(simulate(p, steps, seed=s).cost_usd for s in seeds) / len(seeds)
            row += f"{cost:>13.2f}"
        print(row)


def main() -> None:
    steps = 200
    seeds = [1, 7, 13, 29, 101]
    print(f"Synthetic coding session: {steps} agent steps, "
          f"{CONTEXT_WINDOW:,}-token window, averaged over {len(seeds)} seeds\n")
    header = (
        f"{'Policy':<46}{'mean ctx':>10}{'peak ctx':>10}"
        f"{'cond.':>7}{'cache':>8}{'billed in':>12}{'cost':>9}"
    )
    print(header)
    print("-" * len(header))
    baseline_cost = None
    for policy in POLICIES:
        runs = [simulate(policy, steps, seed=s) for s in seeds]
        mean_ctx = sum(r.mean_context for r in runs) // len(runs)
        peak_ctx = sum(r.peak_context for r in runs) // len(runs)
        cond = sum(r.condensations for r in runs) / len(runs)
        hit = sum(r.cache_hit_rate for r in runs) / len(runs)
        billed = sum(r.billed_input_tokens for r in runs) / len(runs)
        cost = sum(r.cost_usd for r in runs) / len(runs)
        if baseline_cost is None:
            baseline_cost = cost
        print(
            f"{policy.name:<46}{mean_ctx:>10,}{peak_ctx:>10,}"
            f"{cond:>7.1f}{hit:>8.0%}{billed:>12,.0f}{cost:>9.2f}"
        )
    assert baseline_cost is not None
    print()
    for policy in POLICIES[1:]:
        runs = [simulate(policy, steps, seed=s) for s in seeds]
        cost = sum(r.cost_usd for r in runs) / len(runs)
        print(f"  {policy.name}: {1 - cost / baseline_cost:+.0%} vs policy A")
    sweep(steps)


if __name__ == "__main__":
    main()

# ADR-0009: Memory Confidence Comes From Measured Lift, Not Usage

## Status
Accepted

## Context
"Self-learning" memory needs a definition of what it learns *from*. The tempting signals are the
cheap ones:

- **Model self-assessment** — the extractor states a confidence.
- **Usage frequency** — items retrieved often are treated as good.
- **Outcome correlation** — items retrieved on tickets that succeeded gain confidence.

Each is available for free and each is wrong in a way that compounds. Model self-assessment is
uncalibrated and rewards confident phrasing. Usage frequency is circular: an item ranked highly is
retrieved more, which raises its rank. Outcome correlation is the subtlest and most damaging — most
tickets succeed, so almost every retrieved item accrues positive evidence regardless of whether it
contributed anything. A store tuned on correlation converges on serving whatever is most retrievable,
not whatever is most useful, and its reported confidence rises steadily while its actual value does
not.

This is structurally the same error as the ROI baseline selection bias
([`08-design-critique.md`](../08-design-critique.md) C1), and it deserves the same treatment.

## Decision
Item confidence has two independent inputs, and neither is a model's opinion:

1. **Evidence** — the count and diversity of distinct, redacted source occurrences supporting the
   item, with promotion thresholds rising as scope widens. An item without evidence pointers cannot
   be promoted at all.
2. **Measured lift** — a **retrieval holdout** (default 10% of eligible runs execute with recall
   disabled) provides a control arm. Lift is the difference in first-pass yield, rework rate, and
   cost per ticket between served and held-out runs, computed per scope and per memory kind.

Correlation signals are still collected, but they adjust *ranking* only. They never establish
confidence, and they never drive promotion.

## Consequences

- **Memory can be shown not to work.** A scope or kind whose lift is indistinguishable from zero
  has its recall budget cut, and the module reports this rather than continuing to consume context.
  This is the point: a memory system that cannot report its own uselessness will never be turned
  off, and will quietly tax every run indefinitely.
- The holdout costs measurable quality on ~10% of runs. Accepted — the alternative is spending
  context budget forever on an unfalsifiable claim.
- Lift measurement needs sufficient volume per scope. Low-traffic scopes will not reach
  significance, so they inherit the lift estimate of their parent scope and are flagged
  `lift_unmeasured` rather than being assigned a fabricated figure.
- Per-kind measurement will likely show sharply uneven results — `pitfall` and `entity` items
  earning their cost while `procedure` items do not. Designing for that outcome from the start is
  why kind is a first-class field rather than a tag.
- Extractors are versioned and attributable so their individual yield can be measured and throttled
  ([`memory-module.md`](../03-components/memory-module.md) §4.8). Without attribution, a bad
  extractor is invisible inside an aggregate.

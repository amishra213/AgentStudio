# Sequence Flows

> Worked end-to-end examples tying together the components in `03-components/`. Each flow
> references the specific docs/entities it exercises.

---

## Flow 1 — Ticket Created by a PM, Auto-Assigned to an Agent

Exercises: [`ticketing.md`](03-components/ticketing.md), [`agent-marketplace.md`](03-components/agent-marketplace.md), [`agent-execution-and-handoff.md`](03-components/agent-execution-and-handoff.md).

```mermaid
sequenceDiagram
    participant PM
    participant Core
    participant Wf as Workflow Engine
    participant Orch as Orchestrator
    participant Agent

    PM->>Core: create ticket (type=Bug, labels=[frontend])
    Core->>Wf: initialize status = Backlog
    PM->>Core: move to Ready
    Core->>Wf: validate + apply automation "auto-assign by capability_tags"
    Wf->>Core: assign(agent_installation matching "frontend")
    Core->>Orch: dispatch
    Orch->>Agent: POST /v1/runs
    Agent-->>Orch: 202 accepted
    Core->>Core: status -> InProgress
    Agent-->>Orch: run-completed {artifacts, cost}
    Orch->>Core: apply artifacts, status -> InReview
    Core->>Core: RoiBaseline check pending review approval before Done
```

---

## Flow 2 — Multi-Agent Handoff Ending in Ask-Human

Exercises: [`agent-execution-and-handoff.md`](03-components/agent-execution-and-handoff.md) §3–6, [`human-ai-collaboration.md`](03-components/human-ai-collaboration.md) §3.

```mermaid
sequenceDiagram
    participant AgentA as Drafting Agent
    participant Orch
    participant AgentB as Legal Review Agent
    participant Human as Consultant

    Orch->>AgentA: dispatch (leg 1)
    AgentA-->>Orch: run-handoff {reason: needs_different_capability, tags: [legal-review]}
    Orch->>Orch: match capability_tags -> AgentB, hop_count=1 (ok), budget check (ok)
    Orch->>AgentB: dispatch (leg 2), context_bundle from leg 1
    AgentB-->>Orch: run-blocked {question: "Is this clause enforceable in NY?"}
    Orch->>Core: status -> NeedsInput, post question Comment, notify Human
    Human->>Core: post answer Comment
    Core->>Orch: resume(run_id, answer)
    Orch->>AgentB: POST /v1/runs/{run_id}/resume
    AgentB-->>Orch: run-completed {artifacts}
    Orch->>Core: apply artifacts, status -> InReview
```

Note leg 2 is a single `ExecutionLeg` spanning the block/resume — the ask-human round trip does not
create a new hop (per [`agent-execution-and-handoff.md`](03-components/agent-execution-and-handoff.md) §6).

---

## Flow 3 — Handoff Loop Detected, Escalated

Exercises: [ADR-0005](adr/0005-handoff-loop-protection.md), [`agent-execution-and-handoff.md`](03-components/agent-execution-and-handoff.md) §5.

```mermaid
sequenceDiagram
    participant AgentA
    participant Orch
    participant AgentB
    participant PM

    Orch->>AgentA: dispatch (leg 1)
    AgentA-->>Orch: handoff -> AgentB (hop=1)
    Orch->>AgentB: dispatch (leg 2)
    AgentB-->>Orch: handoff -> AgentA (hop=2)
    Orch->>Orch: cycle check: AgentA already in trail -> allow once
    Orch->>AgentA: dispatch (leg 3)
    AgentA-->>Orch: handoff -> AgentB (hop=3)
    Orch->>Orch: cycle check: AgentB repeat AND hop=3 -> escalate
    Orch->>PM: assign ticket, status -> NeedsInput, system comment: "Handoff loop detected between Agent A and Agent B after 3 hops"
```

---

## Flow 4 — Sprint Close and ROI Rollup

Exercises: [`timeline-and-sprints.md`](03-components/timeline-and-sprints.md) §3, [`roi-analytics.md`](03-components/roi-analytics.md) §1–4.

```mermaid
sequenceDiagram
    participant PM
    participant Core
    participant Roi as ROI Service

    PM->>Core: close sprint
    Core->>Core: snapshot velocity (points completed)
    Core->>Roi: compute RoiSummary for every ticket completed in sprint
    loop each ticket
        Roi->>Roi: sum CostEntry across ExecutionLegs
        Roi->>Roi: apply RoiBaseline snapshot
        Roi->>Roi: compute roi_pct, time_saved, attributed_legs
    end
    Roi->>Core: sprint RoiSummary rollup ready
    Core-->>PM: sprint report: $ saved, hours saved, autonomy_level breakdown
```

---

## Flow 5 — Co-Assigned Ticket With Human Override

Exercises: [`human-ai-collaboration.md`](03-components/human-ai-collaboration.md) §2 and §4.

```mermaid
sequenceDiagram
    participant Agent as Agent (owner)
    participant Human as Human (reviewer)
    participant Orch
    participant Core

    Orch->>Agent: dispatch
    Agent-->>Core: proposal Comment (draft artifact)
    Human->>Core: edits proposal directly (creates linked human-authored version)
    Human->>Core: approves -> status -> Done (approval_role: reviewer satisfied)
    Core->>Roi: RoiSummary computed; attributed_legs splits cost/time between Agent leg and Human review leg
```

# ADR-0012: Embed Claude Code as the Deep-Work Inner Loop

**Status:** Accepted  
**Date:** 2026-04-11  
**Deciders:** Agent Studio Architecture Team

## Context

The four outer agent roles (Planner, Coder, Tester, Reviewer) are platform coordinators: they manage task routing, HITL flows, delivery-bundle assembly, and multi-tenancy concerns. They are deliberately short-running and cheap. But software delivery tasks — especially complex refactors, multi-file feature implementations, and iterative test-fix loops — require a different mode of operation: plan mode (thinking through a problem before acting), todo tracking across many steps, iterative edit-run-fix cycles, and deep use of SKILLs. These are the concerns of a deep-work loop, not a coordinator.

There are three ways to provide this deep-work capability: (1) build a bespoke iterative edit-run-fix loop from scratch within the `agent-runtime` package, (2) run Claude Code as a completely separate external service that agents call over HTTP, or (3) embed Claude Code's engine directly as the inner loop, dispatched from within the outer roles. Option 1 means reinventing plan mode, todo tracking, SKILLs loading, nested subagents, and iterative refinement — all production-tested capabilities that Claude Code already provides. Option 2 introduces a network hop and a separate service deployment, and Claude Code is not designed to be a general-purpose HTTP API. Option 3 — embedding Claude Code using the `query()` primitive from `@anthropic-ai/claude-agent-sdk` — reuses the same engine that powers Claude Code in production, at two granularities: in-process (cheap, low-latency) and sandboxed subprocess (isolated, parallel-safe).

A critical architectural invariant must be enforced: nested planning must not occur. If the Planner role were allowed to call Claude Code, it could trigger an inner Claude Code session that also plans — resulting in two independent planning contexts for the same task, with potentially contradictory todo lists and incompatible approaches. The outer roles should plan once (the Planner's job) and then delegate execution to the inner loop, which follows the plan without re-deriving it. This invariant must be enforced at the allowlist level, not by convention.

## Decision

The `deep-coding` package implements and ships an internal `ClaudeCode Worker MCP` server that exposes five tools: `claude_code.run` (in-process nested session via `query()`), `claude_code.spawn_worker` (sandboxed Docker subprocess), `claude_code.status`, `claude_code.cancel`, and `claude_code.stream_events`. The Coder, Tester, and Reviewer roles are permitted to call these tools (subject to HITL approval for `spawn_worker` with `permissionMode=bypassPermissions`). The Planner role is explicitly DENIED access to all `claude_code.*` tools — this is the anti-nested-planning invariant, enforced at the MCP client allowlist layer (ADR-0010), not by convention or prompt instruction.

Two dispatch modes are provided. The in-process mode (`claude_code.run`) calls `query()` from `@anthropic-ai/claude-agent-sdk` in the same Node.js process as the orchestrator — no container overhead, low latency, inherits tenant workspace and SKILLs directory. The sandboxed mode (`claude_code.spawn_worker`) spawns a full Claude Code process inside a per-task Docker container with: a read-only repo snapshot mount (writes go to an overlay filesystem diffed back at completion), a scoped MCP client config (narrowest subset the task needs), environment-injected secrets (Anthropic API key from the secrets backend), CPU/memory/time budgets (killed on overrun), and network egress restricted to the Anthropic API and configured MCP endpoints.

Every `claude_code.run` or `spawn_worker` call takes a typed `DispatchEnvelope` that includes: `goal` (natural language objective), `workspace` (path, base ref, writable globs), `successCriteria` (machine-checkable tests, graph checks, or custom script), `toolBudget` (max tool calls, tokens, wall seconds), `mcpServers` (narrowest subset spec), `skillsDir`, `permissionMode`, `memoryContext` (pre-fetched Ruflo recall), `knowledgeContext` (pre-fetched knowledge.search results), and `returnShape`. Pre-fetching memory and knowledge into the envelope means the inner loop starts hot and does not spend its tool budget on retrieval — that cost stays in the outer loop where it is reasoned about separately. The Reviewer role can fan out multiple parallel `spawn_worker` calls for A/B exploration, wait on all results, and select the winner by success-criteria score.

## Consequences

### Positive
- Plan mode, todo tracking, SKILLs loading, nested subagents, and iterative edit-run-fix cycles are inherited from Claude Code without any in-house implementation — the largest single capability reuse in the platform.
- The in-process `query()` path has effectively zero overhead beyond the LLM API call itself; it is suitable for the common case of a single-worker coding task.
- The sandboxed Docker path provides full isolation for long-running refactors, untrusted tasks, and parallel A/B exploration — a crashing sandboxed worker cannot affect the orchestrator process or other tenants.
- The `DispatchEnvelope` provides a clean, machine-checkable contract between the outer coordination layer and the inner deep-work layer; success criteria are evaluated mechanically, not by asking the inner loop to self-report success.
- The anti-nested-planning invariant (Planner denied `claude_code.*`) is enforced at the allowlist level and cannot be bypassed by prompt injection or LLM creativity.

### Negative / Trade-offs
- Docker container spin-up time (typically 2–10 seconds) adds latency to the first tool call of a sandboxed worker. For short tasks, this overhead may be disproportionate; the in-process mode mitigates this for the common case.
- The `DispatchEnvelope` pre-fetch model (memory + knowledge fetched by the outer role before dispatch) means the outer role must know, before dispatch, approximately what context the inner loop will need. For novel failure modes, this prediction may be incomplete.
- Parallel `spawn_worker` dispatch (A/B exploration) multiplies container costs and API costs; cost ceilings per tenant must be enforced by the orchestrator before allowing fan-out. Without ceiling enforcement, a single misbehaving task could exhaust a tenant's quota.
- The `deep-coding` package is tightly coupled to the `@anthropic-ai/claude-agent-sdk` version; major SDK upgrades require corresponding updates to the dispatch envelope schema and the `query()` call site.

### Neutral
- The Reviewer role's parallel dispatch capability (multiple `spawn_worker` calls) is a design option, not a default; it is only used for explicitly configured "explore multiple approaches" tasks where the cost trade-off has been accepted.
- Every dispatch is tagged with `{task, role, mode, envelope.hash, finalCostTokens, wallMs, exitReason}` so the Web UI "MCP call log" tab shows a flattened view across outer and inner loop tool calls, with costs attributed correctly.
- The `bypassPermissions` permission mode, which allows the inner Claude Code session to make edits without per-edit confirmation, is never enabled without operator HITL approval — it is the only `permissionMode` value that is approval-gated in the `McpServerSpec` for the ClaudeCode Worker server.

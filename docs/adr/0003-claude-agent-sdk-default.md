# ADR-0003: Claude Agent SDK as the Default Agent Runtime

**Status:** Accepted  
**Date:** 2026-04-11  
**Deciders:** Agent Studio Architecture Team

## Context

Agent Studio's four roles — Planner, Coder, Tester, and Reviewer — and the in-process Deep Coding Worker all require an agent runtime: something that manages the conversation loop, tool-call dispatch, streaming, permission gating, and skill loading. The platform could build this loop itself (a thin `while (needsTool) { call model; dispatch tools; accumulate messages }` loop), adopt a general-purpose agent framework (LangGraph, CrewAI, AutoGen), or use the `@anthropic-ai/claude-agent-sdk` that already backs Claude Code.

Building the loop from scratch is viable but means re-implementing concerns that are already well-solved: streaming reassembly across tool-call turns, permission modes (default/acceptEdits/bypassPermissions), subagent nesting, hooks (pre/post tool call, session start), and skill/slash-command loading from a directory. These are precisely the primitives that Claude Code uses in production, which means they are tested against real-world agent workloads. A custom loop would start well behind that baseline.

General-purpose agent frameworks were evaluated. LangGraph adds a graph-state model that is useful for complex flows but introduces a new execution model that conflicts with the orchestrator's own task state machine — the result would be two state machines governing one task. CrewAI and AutoGen are Python-first; a Node.js port or subprocess bridge adds latency and complicates the monorepo. More fundamentally, none of these frameworks provide the skill-loading or permission-mode primitives that the user's existing SKILLs repo depends on.

The `@anthropic-ai/claude-agent-sdk` was designed specifically for this use case: it powers Claude Code, provides `query()` as the primitive for a single agent turn (or a full iterative loop), supports subagents, exposes permission modes, and loads skills from a configured directory. The user already has a SKILLs repo built against this SDK's conventions. Using it as the default runtime means the user's existing skills work in Agent Studio with zero changes.

## Decision

`@anthropic-ai/claude-agent-sdk` is the default runtime for all four agent roles (Planner, Coder, Tester, Reviewer) and for the in-process Deep Coding Worker. Each role is implemented as an SDK subagent with:

- A role-specific system prompt
- A filtered tool set (from the MCP client's per-role allowlists — ADR-0010)
- A permission mode appropriate to the role (Coder may use `acceptEdits`; Planner and Reviewer use `default`; any `bypassPermissions` use requires operator HITL approval — ADR-0012)
- Session hooks for pre/post tool call logging, cost tracking, and HITL event emission
- Skill loading from the tenant's configured SKILLs directory at session start

The `query()` primitive is used by the Deep Coding Worker for in-process nested sessions (ADR-0012). The same SDK entry point powers the sandboxed subprocess variant. This means both dispatch modes share the same agent behavior model — the only difference is the process boundary.

Because the LLM interface (ADR-0002) wraps the Claude adapter, the SDK can be swapped for a different provider's agent runtime at the adapter level without changing `agent-runtime` logic. However, skill loading and permission modes are Claude-specific features; if a non-Claude provider is selected, those features degrade gracefully (skills become plain system-prompt injections; permission modes are no-ops).

## Consequences

### Positive
- The user's existing SKILLs repo works in Agent Studio without modification — skills are loaded by the same SDK hook they were written for.
- Permission modes, subagent nesting, and hooks are production-tested capabilities inherited for free rather than reinvented.
- The `query()` primitive gives the Deep Coding Worker a clean, low-latency in-process dispatch path with no subprocess overhead for the common case.
- Streaming events (tool calls, text deltas, todo updates, plan changes) flow through the SDK's native streaming interface directly to the orchestrator's event bus.
- Claude is the highest-capability model for the complex planning and coding tasks Agent Studio performs; defaulting to it maximizes output quality.

### Negative / Trade-offs
- The SDK is an Anthropic product; its API surface and behavior can change between versions. The `llm` package adapter and `agent-runtime` must be tested against each SDK upgrade before rolling out.
- SKILLs-specific features (slash commands, skill metadata) are not portable to non-Claude providers. Tenants who switch provider lose skill loading.
- The SDK imposes its own opinion on how tool results are formatted and how multi-turn context is accumulated; integrations that need fine-grained control over the message array must work within those conventions.

### Neutral
- The SDK version is pinned in the monorepo root `package.json` and upgraded on a deliberate schedule, not auto-updated. Breaking changes in the SDK's major versions require a migration effort in `agent-runtime` and `deep-coding`.
- The Reviewer and Tester roles use the SDK in a lighter mode (fewer tool-call turns, shorter context windows) than the Coder role; per-role model configuration (e.g. using a smaller Claude model for Reviewer) is supported by passing the model identifier per `query()` call.

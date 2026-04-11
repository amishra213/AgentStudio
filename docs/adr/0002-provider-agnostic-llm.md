# ADR-0002: Provider-Agnostic LLM Interface

**Status:** Accepted  
**Date:** 2026-04-11  
**Deciders:** Agent Studio Architecture Team

## Context

Agent Studio's four agent roles (Planner, Coder, Tester, Reviewer) and its deep-coding worker all require access to a large language model. The most natural implementation would be to call the Anthropic API directly throughout the codebase — Claude is the expected default, the Claude Agent SDK is already a hard dependency (ADR-0003), and the user's existing SKILLs repo is built on Claude tooling. However, direct API coupling at every call site would make it impossible to run agents against a different provider without modifying agent-runtime code. Enterprise customers often have contractual or data-residency reasons to prefer a specific provider, and self-hosting requirements sometimes mandate a local model (Ollama + an open-weight model) over an external API.

The alternative of building a full abstraction layer from the outset adds upfront engineering cost. The risk is over-engineering: if the interface is too thick, every provider adapter becomes a significant project; if it is too thin, callers still end up provider-aware. The interface must be kept minimal — covering exactly the operations agents actually perform — rather than attempting to expose the full feature set of every provider.

Three design points were evaluated: (1) a raw HTTP adapter that normalizes provider REST formats, (2) a thin TypeScript interface backed by provider SDKs, and (3) adoption of an existing multi-provider library (Vercel AI SDK, LangChain). Option 3 was ruled out because those libraries introduce significant transitive dependency weight and abstract over provider streaming and tool-calling in ways that conflict with the Claude Agent SDK's own streaming model. Option 1 requires re-implementing SDK-level concerns (retry, streaming reassembly, auth). Option 2 — a thin interface over provider SDKs — gives the right balance: provider SDKs handle their own streaming and auth, and Agent Studio only writes the adapter glue.

## Decision

The `llm` package defines a minimal `LLMProvider` interface with three methods:

- `generate(request: GenerateRequest): Promise<GenerateResponse>` — single-turn completion with optional tool definitions and tool-call results
- `stream(request: GenerateRequest): AsyncIterable<StreamChunk>` — streaming variant, emitting text deltas and tool-call events
- `embed(texts: string[]): Promise<number[][]>` — text embedding for knowledge retrieval scoring

`GenerateRequest` carries: model identifier, messages (in a normalized role/content format), system prompt, tools (in MCP-compatible JSON Schema format), max tokens, temperature, and stop sequences. `StreamChunk` is a discriminated union over text deltas, tool-call starts, tool-call deltas, tool-call completions, and usage events.

Concrete implementations are provided for: Claude (via `@anthropic-ai/claude-agent-sdk` — the default, see ADR-0003), OpenAI (via `openai` SDK), Gemini (via `@google/generative-ai`), and Ollama (via its REST API). The active provider per agent role is selected from config; different roles may use different providers if cost or capability trade-offs warrant it.

## Consequences

### Positive
- No Anthropic API calls are scattered through `agent-runtime` or `orchestrator` — all LLM interaction is routed through the interface, making the provider swap a config change.
- The interface is small enough that writing a new adapter takes hours, not days.
- Cost optimization becomes possible: a lightweight provider (e.g., Ollama with a small model) can back the Reviewer's low-stakes "does the summary look complete?" checks while Claude backs planning and coding.
- The embed method is available to the Knowledge Retrieval layer for local re-ranking without pulling in a separate embedding client.

### Negative / Trade-offs
- Provider-specific advanced features (extended thinking, prompt caching, Anthropic tool-use betas) are not exposed through the interface; callers that need these must cast to the concrete adapter or accept that the feature is Claude-only. This is an explicit design choice: the interface is normalized to the intersection of provider capabilities, not the union.
- The normalization layer adds a small amount of serialization overhead per call (converting between the normalized format and the provider's native format).
- Keeping four adapters in sync with their respective SDKs as those SDKs evolve requires ongoing maintenance effort.

### Neutral
- The interface is defined in `shared-types` so that `agent-runtime`, `deep-coding`, and `knowledge` can all reference it without creating circular workspace dependencies on `llm`.
- Provider selection is resolved at startup from `agent-studio.config.ts`; there is no runtime provider switching within a task run.

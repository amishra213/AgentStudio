# ADR-0005: Delegate Persistent Memory to Ruflo via MCP

**Status:** Accepted  
**Date:** 2026-04-11  
**Deciders:** Agent Studio Architecture Team

## Context

Agents in Agent Studio need cross-session persistent memory: a place to store and retrieve learned patterns, prior solutions, clarification answers, and task context so that successive runs on similar problems get faster and more accurate over time. Without persistent memory, every task run starts cold — the agents cannot recall that a particular API requires a specific auth header pattern, or that a test failure in a certain module was previously solved by updating a fixture. The memory layer is therefore load-bearing for the platform's quality trajectory.

The two broad approaches are to build a first-party vector memory store or to consume one that already exists. Building first-party would require: choosing and operating a vector database (pgvector on PostgreSQL, Weaviate, Qdrant, Chroma, or a raw HNSW index); defining schemas for the 8+ memory types needed (episodic, semantic, procedural, etc.); implementing scope management across tenant/project/session boundaries; and maintaining the retrieval and write paths as agent requirements evolve. This is a substantial ongoing engineering investment for infrastructure that is not differentiated — many teams have already solved it.

Ruflo (`ruvnet/ruflo`) is an existing open-source project specifically designed as an agent memory and pattern layer. It ships: HNSW-indexed vector memory with PostgreSQL RuVector for durable storage; 8 memory types spanning project, local, and user scopes; pattern storage and retrieval tools; an MCP server interface that exposes all of this as standard MCP tools (`memory.store`, `memory.search`, `pattern.lookup`, `pattern.store`, and others per its published manifest). It is designed to be consumed by MCP clients exactly as Agent Studio would consume it. Notably, Ruflo also ships swarm, queen, router, and consensus features for multi-agent coordination — but Agent Studio does not need these because it has its own orchestrator-level coordination layer (ADR-0009 addresses this scope boundary explicitly).

The risk of consuming Ruflo rather than building in-house is dependency on an external project. This is mitigated by: consuming Ruflo exclusively through the MCP protocol boundary (the interface is stable and version-pinned); keeping a thin `MemoryClient` wrapper in `agent-runtime` that could be re-targeted to a different MCP memory server if Ruflo were abandoned; and the fallback behavior (runs continue stateless with a warning if Ruflo is unreachable — no hard blocking dependency).

## Decision

Agent Studio does not operate its own vector database, HNSW index, or memory schema. All persistent memory is delegated to Ruflo, which runs as a separate process (either a `stdio` child process of the orchestrator pod, or a centrally deployed `streamable-http` service shared across orchestrator replicas). Ruflo is registered in the MCP Server Registry (ADR-0010, ADR-0011) and accessed exclusively through the standard MCP tool-call loop — agents call `memory.store`, `memory.search`, `pattern.lookup`, and `pattern.store` exactly as they call any other tool.

A thin `MemoryClient` wrapper in the `agent-runtime` package provides a typed, scope-aware API (`remember(scope, kind, payload)`, `recall(query, topK)`) over the raw MCP tool calls, mapping Agent Studio's `(tenant, project, task)` coordinate system to Ruflo's `user/project/local` scope model. Defined write points are: after planning, after each successful fix, after test pass, on human clarification answer, and on task completion. Defined read points are: before planning, before each retry, before review, and on any test failure (before invoking knowledge retrieval). If Ruflo is unreachable, runs continue stateless with a `memory_unavailable` warning event — no silent data loss, no hard failure.

## Consequences

### Positive
- Eliminates the need to build, operate, and evolve a vector database and memory schema — a significant reduction in platform engineering scope for infrastructure that is not differentiated.
- Ruflo's HNSW-indexed vector search and 8 memory types across scopes are immediately available without any in-house development.
- Memory is shared across orchestrator replicas when Ruflo runs as a central HTTP service, enabling cross-session, cross-replica recall that would require additional engineering if built in-house.
- The MCP protocol boundary means Ruflo can be upgraded independently of Agent Studio; the `MemoryClient` wrapper localizes any breaking-change adaptations to a single file.
- The fallback to stateless operation means a Ruflo outage degrades quality but does not block task execution.

### Negative / Trade-offs
- Agent Studio's memory behavior is bounded by Ruflo's retrieval quality and scope model; advanced memory requirements (e.g. a new scope type, a specialized retrieval strategy) must either be contributed upstream or worked around within the existing API.
- Ruflo is an external dependency whose development pace and API stability are outside Agent Studio's control. Version pinning and a `MemoryClient` abstraction mitigate this but do not eliminate it.
- Running Ruflo as a central HTTP service introduces a shared mutable state component that must be operated with high availability; this is an additional infrastructure concern.
- The `MemoryClient` wrapper adds a thin translation layer that must be kept in sync with Ruflo's evolving tool manifest.

### Neutral
- Ruflo's swarm, queen, router, and consensus features are explicitly out of scope and are disabled via the MCP server allowlist for all agent roles — only `memory.*` and `pattern.*` tools are permitted (see ADR-0009).
- The scope mapping (`tenant/project/task` to Ruflo's `user/project/local`) is documented in `02-integrations/ruflo.md` and is the authoritative reference for any future memory backend migration.

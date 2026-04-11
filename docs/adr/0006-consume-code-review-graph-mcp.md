# ADR-0006: Consume code-review-graph as an External MCP Server

**Status:** Accepted  
**Date:** 2026-04-11  
**Deciders:** Agent Studio Architecture Team

## Context

Agent Studio's agents must understand the structure of the codebase they are working on — which functions call which, which tests cover which modules, what the blast radius of a proposed change is, and what the existing architecture looks like at a conceptual level. Without structural code understanding, the Planner must ingest entire files to locate the relevant slice of code (expensive in tokens), the Coder may introduce changes without knowing what else they affect, the Tester must guess which tests to run, and the Reviewer cannot produce a meaningful impact summary.

Building a first-party code understanding layer would require: integrating tree-sitter for multi-language parsing; building a graph database or in-memory graph for call/import/inheritance relationships; implementing semantic search over the graph; implementing change-detection against a git diff; and building impact-radius, caller/callee traversal, test-coverage linkage, and architecture-overview generation on top of that graph. This is a substantial software project in its own right, and it is the kind of infrastructure that is not unique to Agent Studio — it is useful to any agent-based development tool.

The `tirth8205/code-review-graph` project ships exactly this capability as a 22-tool MCP server. Its published toolset includes: `graph.build`, `graph.update`, `graph.detect_changes`, `graph.impact_radius`, `graph.callers_of`, `graph.callees_of`, `graph.tests_for`, `graph.semantic_search`, `graph.architecture_overview`, `graph.wiki_generate`, and `graph.visualize`, among others. Its authors report 6.8x–49x token reductions on code review tasks versus naive full-file ingestion, which directly addresses the platform's requirement to avoid full codebase ingestion. It ships a Python CLI and MCP server that can be spawned via stdio or run as a sidecar container with a pinned version. The MCP boundary means Agent Studio has no dependency on its internal implementation (Python, tree-sitter, specific graph library) — only on its published tool interface.

The code-review-graph serves three distinct jobs for the delivery loop: (a) token-efficient understanding of existing code before planning, (b) incremental tracking of what agents produce during the task (via fast `graph.update` calls after each coder commit), and (c) delivery bundle generation for the Reviewer role at task completion. Reimplementing any one of these would be a multi-month distraction; reimplementing all three is not feasible alongside platform development.

## Decision

Agent Studio does not build its own tree-sitter indexer, call-graph database, or code-understanding pipeline. It consumes `tirth8205/code-review-graph` as an external MCP server, pinned to a specific version in the MCP Server Registry. The server is spawned via `stdio` (as a Python sidecar process) or run as a Docker sidecar container per tenant-project, and is registered in the MCP Registry with a per-role tool allowlist: Planner (architecture_overview, semantic_search), Coder (impact_radius, callers_of, callees_of, update, detect_changes), Tester (tests_for, impact_radius), Reviewer (all tools — it drives the full delivery bundle).

The orchestrator calls `graph.update` + `graph.detect_changes` after every coder commit (via Git MCP) to keep the graph continuously synchronized with agent output. The Reviewer assembles the Delivery Bundle by calling `graph.impact_radius`, `graph.tests_for`, `graph.detect_changes`, `graph.wiki_generate`, and `graph.visualize` at task completion. If code-review-graph is unreachable, the Reviewer falls back to a diff-based summary and the task is flagged "partial delivery — graph unavailable" — there is no hard blocking dependency.

## Consequences

### Positive
- Eliminates the need to build and maintain a tree-sitter parsing pipeline, graph database, semantic search index, and the 22 derived capabilities built on top of them — the largest single scope reduction in the platform.
- The 6.8x–49x token reduction on code understanding tasks directly reduces cost and latency for the Planner and Coder roles.
- The incremental `graph.update` (completing in under ~2 seconds on multi-thousand-file repos) enables a live structural map of agent-produced changes throughout the task, not just at the end.
- The delivery bundle (impact radius, test coverage, risk-scored change summary, auto-generated wiki, interactive visualization) is produced by the external tool with no in-house implementation.
- The MCP boundary means the Python runtime, internal graph library, and database technology used by code-review-graph are invisible to Agent Studio — upgrades are managed through the MCP Registry.

### Negative / Trade-offs
- Agent Studio's code-understanding capability is bounded by what code-review-graph supports. Language coverage, graph depth, and retrieval quality are all upstream concerns; Agent Studio can only work around gaps at the prompt level.
- The Python runtime required by code-review-graph adds a second language runtime to the deployment footprint; the Docker sidecar approach contains this but adds container management overhead.
- Version pinning means Agent Studio may lag behind upstream improvements or bug fixes; upgrades require running the allowlist diff check (ADR-0011) before enabling in production.
- If the upstream project is abandoned, Agent Studio must either fork it (incurring the maintenance burden) or build a replacement — the fallback diff-based summary is a degraded experience.

### Neutral
- code-review-graph is not forked. Upgrades are opt-in through the MCP Registry, with the allowlist diff safety check gating any new tools that appear after an upgrade.
- The `graph.visualize` output (interactive HTML) is embedded in the Web UI's "Delivery" tab via an iframe; no in-house visualization code is required.

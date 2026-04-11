# ADR-0008: Federated Knowledge Retrieval as an Internal MCP Server

**Status:** Accepted  
**Date:** 2026-04-11  
**Deciders:** Agent Studio Architecture Team

## Context

Agents working on non-trivial software delivery tasks frequently encounter problems that have been solved before — either internally (a Confluence runbook, a SharePoint architecture decision, a GitHub issue with a fix already merged) or externally (a Stack Overflow answer, an official library documentation page, a known upstream bug report). Without a way to check these sources before attempting their own solution, agents waste tokens re-discovering known answers and sometimes implement solutions that contradict existing team conventions or that duplicate work already merged elsewhere in the organization.

Agent Studio must search across at least four heterogeneous knowledge sources: the public web (for library documentation, upstream issues, and community solutions), Confluence (for internal runbooks, architecture docs, and ADRs), SharePoint (for enterprise policies, design documents, and meeting notes), and GitHub (for existing issues, PRs, and code that solved similar problems across the organization's repos). These sources have incompatible APIs, authentication models, and result formats. If each agent role implemented its own search adapters, the result would be duplicated adapter code across the platform, inconsistent handling of auth and caching, and no unified observability over knowledge retrieval calls.

The alternatives considered were: (1) have agents call web/Confluence/SharePoint/GitHub APIs directly as MCP tools, (2) build a separate knowledge microservice with its own REST API, or (3) expose knowledge retrieval as an internal MCP server. Option 1 leaks adapter logic into agent prompts and bypasses the allowlist/observability infrastructure. Option 2 introduces a bespoke API contract that the agent runtime must call specially, outside the tool-use loop. Option 3 makes knowledge retrieval a first-class MCP tool (`knowledge.search`, `knowledge.fetch`) that slots into the same allowlist, approval, and observability pipeline as every other capability — agents call it identically to how they call `memory.search` or `graph.semantic_search`.

Result quality across heterogeneous sources is a known challenge: the best result from a web search may rank far below mediocre Confluence results if a naive union sort is used. Reciprocal Rank Fusion (RRF) is a well-established technique for combining ranked lists from multiple sources into a single list that preserves relative signal from each source without requiring score normalization. Per-query caching (keyed on query hash + source set + topK) avoids redundant API calls when the same failure signature triggers multiple knowledge lookups within a single task run.

## Decision

A `knowledge` package in the monorepo implements and ships an internal MCP server that exposes two tools: `knowledge.search(query, sources?, topK)` and `knowledge.fetch(url)`. Internally, `knowledge.search` fans out to a set of source adapters in parallel, collects normalized `KnowledgeHit` results from each, applies Reciprocal Rank Fusion to produce a unified ranked list, caches the result keyed on `(queryHash, sources, topK)` for the duration of the task, and returns the top-K hits. `knowledge.fetch` delegates to the Fetch MCP server to retrieve full page content for a URL returned by a prior `knowledge.search` call.

The source adapters are: (1) a pluggable web search adapter (Tavily by default; Brave or SerpAPI selectable per tenant via config); (2) a Confluence adapter using the Atlassian REST API v2 with CQL search and page-fetch, authenticated via API token per tenant from the secrets backend; (3) a SharePoint adapter using Microsoft Graph `/search/query`, authenticated via Azure AD app registration per tenant; and (4) a GitHub adapter that delegates to the GitHub MCP server's `github.search_code` and `github.search_issues` tools rather than re-implementing GitHub search. Per-tenant config declares which adapters are enabled and holds their credential references; adapters not configured for a tenant are simply skipped. All agent roles may call `knowledge.search`; the allowlist (ADR-0010) does not restrict it by role because knowledge retrieval is uniformly beneficial at all stages of the delivery loop.

## Consequences

### Positive
- A single `knowledge.search` call gives agents access to the full federated knowledge corpus — web, Confluence, SharePoint, and GitHub — without role-specific adapter logic.
- Reciprocal Rank Fusion produces a quality-ranked unified result list regardless of how individual adapters rank their own results, avoiding the need to normalize incompatible scoring systems.
- Per-query caching eliminates redundant API calls within a task: if the Tester and the Coder both search for the same failure pattern in the same task run, only the first call hits the external APIs.
- Knowledge retrieval slots into the same MCP allowlist, observability, and approval infrastructure as every other capability — every `knowledge.search` call is logged with `{task, role, query, sources, latency, hitCount}` for cost dashboards.
- Delegating GitHub search to the GitHub MCP server avoids duplicating GitHub API integration; the knowledge layer composes over existing MCP tools rather than re-implementing them.

### Negative / Trade-offs
- Maintaining four adapters (web, Confluence, SharePoint, GitHub delegate) and keeping them synchronized with upstream API changes is an ongoing maintenance surface. Atlassian and Microsoft both have histories of API version churn.
- The Confluence and SharePoint adapters require per-tenant credential setup (API tokens, Azure AD app registrations); tenants without internal knowledge systems must configure at least one external source or accept web-only results.
- Reciprocal Rank Fusion requires collecting results from all enabled adapters before returning; if one adapter is slow (e.g. a Confluence instance with high latency), the entire `knowledge.search` call is gated on it. Per-adapter timeouts and degraded-mode returns (skip slow adapter, warn in result metadata) mitigate this.
- The task-scoped cache does not persist across tasks; knowledge hits that would be relevant to a future task are not retained (that role belongs to Ruflo's pattern store, not to the knowledge layer).

### Neutral
- The internal knowledge MCP server is registered in the MCP Server Registry like any other server; operators can disable the `knowledge` server entry to turn off all knowledge retrieval for a tenant.
- An optional "internal docs" adapter (lightweight local RAG over a mounted docs folder) can be added in a later phase for tenants that have neither Confluence nor SharePoint but have a local documentation directory.
- The `knowledge.fetch` tool is a thin delegation to the Fetch MCP server and adds no independent implementation; it exists as a convenience so callers do not need to be aware of which MCP server handles raw URL fetching.

# Architecture Overview

This document describes the Agent Studio architecture using C4-style diagrams — Context, Container, and Component levels — plus a monorepo package dependency map.

---

## 1. System Context Diagram

Agent Studio sits at the centre of a constellation of users, LLM providers, external MCP servers, and enterprise knowledge sources. No agents run on user machines — all execution is cloud-hosted.

```mermaid
C4Context
  title Agent Studio — System Context

  Person(devUser, "Developer / Operator", "Submits tasks, steers execution, approves actions via VS Code extension or Web UI")

  System(agentStudio, "Agent Studio", "Centrally hosted platform. Orchestrates planner → coder → tester → reviewer agents to deliver software autonomously.")

  System_Ext(claude, "Claude LLM (Anthropic API)", "Default LLM backing all 4 agent roles and Claude Code deep-coding workers")
  System_Ext(ruflo, "Ruflo (ruvnet/ruflo)", "Persistent cross-session memory and learned patterns, consumed via MCP")
  System_Ext(wms, "WMS MCP Server", "User-provided enterprise WMS: read/update configs and source via MCP")
  System_Ext(github, "GitHub / GitLab / Bitbucket", "Remote forge: PRs, issues, code search; accessed via GitHub MCP server")
  System_Ext(confluence, "Confluence / SharePoint", "Enterprise knowledge bases; queried by Knowledge Retrieval MCP")
  System_Ext(playwright, "Playwright MCP", "Browser automation for E2E test generation and execution (Docker-sandboxed)")
  System_Ext(codeReviewGraph, "code-review-graph MCP", "Structural code knowledge graph: blast-radius, tests-for, wiki, visualize")

  Rel(devUser, agentStudio, "Submits tasks, steers execution, approves HITL actions", "HTTPS + WebSocket")
  Rel(agentStudio, claude, "Agent LLM calls and Claude Code worker invocations", "HTTPS")
  Rel(agentStudio, ruflo, "Store/recall memory and learned patterns", "MCP (stdio or HTTP)")
  Rel(agentStudio, wms, "Read/update enterprise WMS data", "MCP (as configured)")
  Rel(agentStudio, github, "Create PRs, search code/issues, merge", "MCP (HTTP)")
  Rel(agentStudio, confluence, "CQL search and page fetch for knowledge retrieval", "Atlassian REST API")
  Rel(agentStudio, playwright, "Launch browser, run E2E tests, capture reports", "MCP (stdio/Docker)")
  Rel(agentStudio, codeReviewGraph, "Build graph, detect changes, impact-radius, wiki generation", "MCP (stdio/Docker)")
```

---

## 2. Container Diagram

Inside Agent Studio, distinct containers handle orchestration, agent execution, deep coding, tool access, UI, and infrastructure.

```mermaid
C4Container
  title Agent Studio — Containers

  Person(user, "Developer / Operator")

  Container(webUI, "Web UI", "Next.js", "Task submission, live task graph, HITL approvals, MCP call log, Delivery Bundle viewer, MCP Marketplace")
  Container(vscodeExt, "VS Code Extension", "TypeScript / VS Code API", "Thin WebSocket client; mirrors Web UI; surfaces diffs and tests inline")

  Container(orchestrator, "Orchestrator Service", "Fastify + WebSocket + BullMQ", "Owns task state machine, dispatches agent runs, streams events, enforces cost ceilings and HITL flows")

  Container(agentRuntime, "Agent Runtime", "TypeScript / Claude Agent SDK", "Planner, Coder, Tester, Reviewer roles as SDK subagents. Short-running coordinators — delegate deep work to Claude Code workers via DispatchEnvelope.")

  Container(deepCoding, "Deep Coding Workers", "TypeScript (deep-coding package)", "Two modes: in-process query() via Claude Agent SDK; sandboxed Claude Code subprocess in k8s Job containers.")

  Container(mcpClient, "MCP Client", "TypeScript / @modelcontextprotocol/sdk", "Single package owning ALL external capability connections. Enforces per-role allowlists, approval hooks, health monitoring.")

  Container(knowledgeMcp, "Knowledge Retrieval MCP", "TypeScript (internal)", "Federated search over web / Confluence / SharePoint / GitHub. Returns ranked KnowledgeHit[]. Internal MCP server.")

  Container(postgres, "PostgreSQL", "Managed RDS / Cloud SQL / Azure DB", "Tasks, runs, events, checkpoints, HITL requests, MCP registry, audit log, tenant/project rows")
  Container(redis, "Redis", "Managed ElastiCache / Memorystore", "BullMQ task queue + pub/sub for WebSocket fan-out")

  Container(rufloSidecar, "Ruflo Sidecar", "ruvnet/ruflo (external)", "Central persistent memory service. Shared across orchestrator replicas. HNSW-indexed vector memory.")
  Container(crgSidecar, "code-review-graph Sidecar", "tirth8205/code-review-graph (external)", "Per tenant-project. Structural code graph: 22 tools for blast-radius, tests-for, semantic search, wiki, visualize.")
  Container(playwrightSidecar, "Playwright MCP Sidecar", "@playwright/mcp (external)", "Browser automation inside Docker sandbox. No external network. Reports on mounted volume.")
  Container(vault, "Secrets Backend", "HashiCorp Vault / Cloud KMS", "All credentials. Never in DB, never logged. Resolved at MCP server spawn time.")

  Rel(user, webUI, "Browser / HTTPS + WebSocket")
  Rel(user, vscodeExt, "VS Code / HTTPS + WebSocket")
  Rel(webUI, orchestrator, "REST + WebSocket", "HTTPS")
  Rel(vscodeExt, orchestrator, "REST + WebSocket", "HTTPS")
  Rel(orchestrator, agentRuntime, "Dispatch agent run (role + task context)")
  Rel(agentRuntime, deepCoding, "DispatchEnvelope → claude_code.run / spawn_worker")
  Rel(agentRuntime, mcpClient, "Tool calls (memory.search, git.diff, graph.architecture_overview, …)")
  Rel(deepCoding, mcpClient, "Scoped tool calls (fs.write, git.commit, graph.update, …)")
  Rel(mcpClient, knowledgeMcp, "knowledge.search / knowledge.fetch")
  Rel(mcpClient, rufloSidecar, "memory.store / memory.search / pattern.lookup")
  Rel(mcpClient, crgSidecar, "graph.build / graph.update / graph.impact_radius / …")
  Rel(mcpClient, playwrightSidecar, "playwright.run_test / playwright.get_report")
  Rel(orchestrator, postgres, "Read/write task state, events, audit log")
  Rel(orchestrator, redis, "Enqueue tasks, pub/sub for live events")
  Rel(vault, mcpClient, "Secrets injected at MCP server spawn time")
```

---

## 3. Monorepo Package Map

Agent Studio is a pnpm + Turborepo monorepo. The package graph below shows dependency edges (arrows mean "depends on").

```mermaid
graph TD
  sharedTypes["shared-types<br/>(types, enums, schemas)"]

  llm["llm<br/>(LLMProvider interface<br/>+ Claude adapter)"]
  mcpClient["mcp-client<br/>(MCP transports, registry,<br/>allowlists, approval hooks)"]
  knowledge["knowledge<br/>(Knowledge Retrieval MCP server —<br/>web/Confluence/SharePoint/GitHub)"]
  deepCoding["deep-coding<br/>(ClaudeCode Worker MCP —<br/>in-process query() + Docker worker)"]
  agentRuntime["agent-runtime<br/>(Planner/Coder/Tester/Reviewer<br/>subagents + MemoryClient wrapper)"]
  orchestrator["orchestrator<br/>(Fastify + WebSocket + BullMQ<br/>task state machine)"]
  testing["testing<br/>(Playwright integration,<br/>test loop utilities)"]
  web["web<br/>(Next.js control panel)"]
  vscodeExtension["vscode-extension<br/>(VS Code plugin)"]

  sharedTypes --> llm
  sharedTypes --> mcpClient
  sharedTypes --> knowledge
  sharedTypes --> deepCoding
  sharedTypes --> agentRuntime
  sharedTypes --> orchestrator
  sharedTypes --> testing
  sharedTypes --> web
  sharedTypes --> vscodeExtension

  llm --> agentRuntime
  mcpClient --> agentRuntime
  mcpClient --> deepCoding
  mcpClient --> knowledge
  mcpClient --> testing
  agentRuntime --> orchestrator
  deepCoding --> orchestrator
  knowledge --> orchestrator
  testing --> orchestrator
  orchestrator --> web
  orchestrator --> vscodeExtension
```

**Package responsibilities:**

| Package | Role | Key dependencies |
|---|---|---|
| `shared-types` | Canonical TypeScript types, Zod schemas, enums used across all packages | None |
| `llm` | `LLMProvider` interface + Claude adapter (default) + OpenAI/Gemini/Ollama stubs | `shared-types` |
| `mcp-client` | Single connection manager for all MCP servers; allowlists, approval hooks, health | `shared-types` |
| `knowledge` | Internal Knowledge Retrieval MCP server; adapters for web/Confluence/SharePoint/GitHub | `shared-types`, `mcp-client` |
| `deep-coding` | Internal ClaudeCode Worker MCP; in-process `query()` + sandboxed Docker worker | `shared-types`, `mcp-client` |
| `agent-runtime` | Planner/Coder/Tester/Reviewer subagents; `MemoryClient` wrapper; SKILLs loader | `shared-types`, `llm`, `mcp-client` |
| `orchestrator` | Fastify service; task state machine; BullMQ queue; WebSocket event streaming | `shared-types`, `agent-runtime`, `deep-coding`, `knowledge` |
| `testing` | Playwright MCP integration helpers; test loop utilities; coverage threshold checks | `shared-types`, `mcp-client` |
| `web` | Next.js control panel; WebSocket client; Delivery Bundle viewer; MCP Marketplace | `shared-types` |
| `vscode-extension` | VS Code plugin; WebSocket client; inline diff/test views; HITL approval panel | `shared-types` |

---

## 4. Key Architectural Principles

### No agents run locally
Users connect to the hosted orchestrator from VS Code or a browser. All LLM calls, MCP tool executions, file operations, and test runs happen in the cloud. See [ADR-0013](adr/0013-cloud-hosted-no-local-agents.md).

### MCP as the universal tool boundary
Every external capability — memory (Ruflo), repo ops (Git MCP), forge ops (GitHub MCP), browser automation (Playwright MCP), code understanding (code-review-graph), enterprise data (WMS MCP), knowledge retrieval (internal MCP) — is accessed via the MCP client. No bespoke tool code leaks into `agent-runtime`. See [ADR-0004](adr/0004-mcp-client-transport.md) and [`02-components/mcp-client.md`](02-components/mcp-client.md).

### Outer roles coordinate; inner loop does the work
The four agent roles (Planner, Coder, Tester, Reviewer) are deliberately short-running coordinators. All heavy task breakdown and iterative coding is dispatched to Claude Code deep-coding workers via a typed `DispatchEnvelope`. This separation keeps the outer loop cheap and prevents nested re-planning. See [ADR-0012](adr/0012-embed-claude-code-as-deep-worker.md) and [`02-components/deep-coding-workers.md`](02-components/deep-coding-workers.md).

### No forks of external projects
Ruflo, code-review-graph, and all upstream MCP servers are consumed as external dependencies, pinned to versions in the MCP Registry. Forking any of them would create a maintenance burden and obscure upgrade paths. See [ADR-0009](adr/0009-consume-ruflo-via-mcp-not-fork.md) and [ADR-0006](adr/0006-consume-code-review-graph-mcp.md).

### Provider-agnostic LLM layer
All LLM calls go through the `LLMProvider` interface. Claude is the default (and the recommended choice given the user's SKILLs repo and the `@anthropic-ai/claude-agent-sdk` integration). Swapping to OpenAI, Gemini, or Ollama is a one-adapter change. See [ADR-0002](adr/0002-provider-agnostic-llm.md).

---

## 5. Cross-Reference

| Topic | Detail doc |
|---|---|
| Orchestrator internals | [`02-components/orchestrator.md`](02-components/orchestrator.md) |
| Agent roles + anti-nesting | [`02-components/agent-runtime.md`](02-components/agent-runtime.md) |
| Deep Coding Workers + DispatchEnvelope | [`02-components/deep-coding-workers.md`](02-components/deep-coding-workers.md) |
| MCP client + allowlists | [`02-components/mcp-client.md`](02-components/mcp-client.md) |
| MCP Registry & Manager | [`02-components/mcp-registry.md`](02-components/mcp-registry.md) |
| Cloud hosting topology | [`02-components/hosting-and-deployment.md`](02-components/hosting-and-deployment.md) |
| Delivery Bundle | [`02-components/delivery-bundle.md`](02-components/delivery-bundle.md) |
| All MCP integrations | [`02-integrations/README.md`](02-integrations/README.md) |
| Security | [`06-security.md`](06-security.md) |
| Phased roadmap | [`07-roadmap.md`](07-roadmap.md) |

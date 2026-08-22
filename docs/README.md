# Agent Studio — Documentation Index

> **Start here.** If you are new to Agent Studio, read the files in the order listed under
> [Reading Order for Newcomers](#reading-order-for-newcomers) before diving into component or
> integration details.

Agent Studio is a centrally hosted platform that drives autonomous and semi-autonomous software
delivery through a pipeline of planner → coder → tester → reviewer agents, all coordinated by a
single cloud-hosted orchestrator, with persistent memory, browser-level test automation, structural
code understanding, and a unified human-in-the-loop approval surface available in both the browser
and VS Code.

---

> **Newcomer callout.** Not sure where to begin? Read [`00-overview.md`](./00-overview.md) for
> the goals and big picture, then [`01-architecture.md`](./01-architecture.md) for the system
> structure, and finally [`07-roadmap.md`](./07-roadmap.md) for the phased build plan. Everything
> else in this tree is a deep-dive reference you can return to as needed.

---

## Reading Order for Newcomers

```
00-overview.md          ← start here (goals, non-goals, success criteria, spec traceability)
01-architecture.md      ← C4 diagrams: context, container, monorepo package map
02-components/          ← deep dives on each internal service and subsystem
02-integrations/        ← one file per external MCP server Agent Studio talks to
03-data-model.md        ← task / run / event database schemas
04-api-contracts.md     ← REST + WebSocket surface
05-sequence-flows.md    ← end-to-end execution traces with MCP call annotations
06-security.md          ← authn/z, tenancy, secrets, sandboxing
07-roadmap.md           ← phased implementation plan (Phase 0 → Phase 11)
adr/                    ← architectural decision records (the "why" behind key choices)
research/               ← analyses of external systems that inform our design
```

---

## Full Document Tree

### Overview

| File | Description |
|------|-------------|
| [00-overview.md](./00-overview.md) | Project purpose, goals, non-goals, measurable success criteria, and a traceability table mapping the 8 user-spec sections to the docs that address each one. |
| [01-architecture.md](./01-architecture.md) | C4-style architecture document with Mermaid context diagram, container diagram, and monorepo package-dependency map, plus narrative explanation of every major interaction. |

### Components (15 files)

| File | Description |
|------|-------------|
| [02-components/orchestrator.md](./02-components/orchestrator.md) | Central task-graph scheduler: Fastify service, BullMQ queues, state machine, event streaming, multi-tenancy, and HA topology. |
| [02-components/agent-runtime.md](./02-components/agent-runtime.md) | The four agent roles (Planner, Coder, Tester, Reviewer) implemented as Claude Agent SDK subagents; per-role system prompts, allowed tools, and anti-nesting invariants. |
| [02-components/llm-abstraction.md](./02-components/llm-abstraction.md) | Provider-agnostic `LLMProvider` interface with Claude as the default; how to swap in OpenAI, Gemini, or Ollama; cost normalization across providers. |
| [02-components/skills-loader.md](./02-components/skills-loader.md) | Loading a user-configured SKILLs repository into the agent at session start; directory layout contract (`SKILL.md` + optional scripts); precedence rules; runtime hot-reload. |
| [02-components/mcp-client.md](./02-components/mcp-client.md) | Central MCP client (built on `@modelcontextprotocol/sdk`): connection lifecycles, pluggable transports (stdio / streamable-http / sse), per-role tool allowlists, per-task overrides, approval hooks, health monitoring, and observability. |
| [02-components/mcp-registry.md](./02-components/mcp-registry.md) | Dynamic MCP server registry and manager: declarative `McpServerSpec`, layered config sources, five source kinds (npx / docker / http / binary / git), curated marketplace catalog, lifecycle operations (install / upgrade / enable / disable / remove), version-pinning, hot-reload, and audit log. |
| [02-components/deep-coding-workers.md](./02-components/deep-coding-workers.md) | Claude Code as the inner-loop deep worker: in-process `claude_code.run` (Agent SDK `query()`), sandboxed `claude_code.spawn_worker` (Docker), `DispatchEnvelope` contract, anti-nested-planning rule, parallel fan-out, cost and failure isolation. |
| [02-components/delivery-bundle.md](./02-components/delivery-bundle.md) | How the Reviewer role assembles the final delivery artifact using `code-review-graph` tools: impact radius, test coverage confirmation, risk-scored change summary, auto-generated wiki, and interactive graph visualization. |
| [02-components/task-state.md](./02-components/task-state.md) | Task lifecycle state machine (`not_started → planning → in_progress → blocked → partially_complete → completed / failed / cancelled`), checkpoint semantics, pause/resume, HITL interrupts, and audit trail. |
| [02-components/testing-pipeline.md](./02-components/testing-pipeline.md) | Playwright test loop: how the Tester agent derives the test surface from `graph.tests_for`, drives the Playwright MCP server, handles failures with memory + knowledge retrieval, commits fixes via Git MCP, and exits on threshold or max-iterations. |
| [02-components/hosting-and-deployment.md](./02-components/hosting-and-deployment.md) | Cloud topology: stateless orchestrator pods, managed Postgres and Redis, Ruflo sidecar, `code-review-graph` sidecar, ephemeral k8s worker Jobs; three deployment footprints (dev docker-compose, staging k8s, production HA). |
| [02-components/execution-control.md](./02-components/execution-control.md) | Steering verbs available from both Web UI and VS Code: `pause`, `resume`, `inject_context`, `override_plan`, `approve`, `reject`, `cancel`, `branch`, `rollback`, `set_budget`, `retarget_reviewer`; semantics and audit guarantees. |
| [02-components/vscode-extension.md](./02-components/vscode-extension.md) | VS Code extension as a thin control surface: WebSocket client, inline diff/test views, approval panel, session bridging with the web UI, auth (OAuth PKCE), and parity matrix. |
| [02-components/web-ui.md](./02-components/web-ui.md) | Next.js control panel: task submission, live task graph, agent transcripts, MCP call log, knowledge-hit inspector, memory browser, MCP server health dashboard, HITL approval queue, and Delivery Bundle viewer. |
| [02-components/human-in-the-loop.md](./02-components/human-in-the-loop.md) | First-class HITL design: `askHuman` primitive, approval-gated MCP tool calls, clarification request schema, notification routing, timeout and escalation policy, and audit recording. |

### Integrations (11 files)

| File | Description |
|------|-------------|
| [02-integrations/README.md](./02-integrations/README.md) | Integration matrix showing every MCP server against every agent role, transport type, tools consumed, and approval requirements. |
| [02-integrations/ruflo.md](./02-integrations/ruflo.md) | Ruflo persistent memory via MCP: tool names, scope mapping (tenant/project/task → Ruflo user/project/local), read/write checkpoints, `MemoryClient` wrapper, and fallback behavior. |
| [02-integrations/wms.md](./02-integrations/wms.md) | Enterprise WMS MCP server (user-provided): connection config, tool allowlist per role, write-approval gates, failure modes, and example tool call sequences. |
| [02-integrations/git.md](./02-integrations/git.md) | Git MCP server (stdio sidecar): clone, branch, stage, commit, diff, log, status; per-role read/write split; workspace path-jailing; interaction with the coder's edit loop. |
| [02-integrations/github.md](./02-integrations/github.md) | GitHub MCP server (HTTP sidecar): PR lifecycle, issue search, code search, review, merge; HITL-gated write operations; GitLab/Bitbucket/Azure DevOps swap-in guidance. |
| [02-integrations/playwright.md](./02-integrations/playwright.md) | Playwright MCP server in Docker sandbox: browser launch, navigation, interaction, snapshot, test execution, report retrieval; tester-only allowlist; sandbox resource limits. |
| [02-integrations/filesystem.md](./02-integrations/filesystem.md) | Filesystem MCP server: path-jailed workspace I/O; per-role read/write split; interaction with Git MCP; security considerations. |
| [02-integrations/fetch.md](./02-integrations/fetch.md) | Fetch MCP server: URL-to-markdown conversion, domain allowlist enforcement, integration with Knowledge Retrieval MCP, rate limits. |
| [02-integrations/knowledge.md](./02-integrations/knowledge.md) | Knowledge Retrieval MCP (internal): federated search over web (Tavily/Brave/SerpAPI), Confluence (CQL), SharePoint (Microsoft Graph), and GitHub; `KnowledgeHit` normalization; reciprocal rank fusion; per-query caching. |
| [02-integrations/claude-code-worker.md](./02-integrations/claude-code-worker.md) | ClaudeCode Worker MCP (internal): `claude_code.run` and `claude_code.spawn_worker` tools, `DispatchEnvelope` wire format, streaming event protocol, cost and exit-reason reporting. |
| [02-integrations/code-review-graph.md](./02-integrations/code-review-graph.md) | `code-review-graph` MCP (external Python service): all 22 tools consumed, token-efficiency rationale, incremental graph update after every coder commit, Delivery Bundle generation, failure fallback to diff-based summary. |

### Data Model, API, Sequences, Security, Roadmap

| File | Description |
|------|-------------|
| [03-data-model.md](./03-data-model.md) | Postgres schemas for tasks, runs, events, MCP registry, audit log, and tenant/project rows; index strategy; event-sourcing conventions. |
| [04-api-contracts.md](./04-api-contracts.md) | Complete REST and WebSocket API surface: endpoint catalog, request/response shapes, error codes, authentication headers, rate limits, and versioning policy. |
| [05-sequence-flows.md](./05-sequence-flows.md) | End-to-end Mermaid sequence diagrams: happy-path task execution, HITL clarification flow, Playwright test-fail-and-fix loop, knowledge retrieval, and Delivery Bundle assembly. |
| [06-security.md](./06-security.md) | Authentication (OAuth PKCE / JWT), per-tenant DB row isolation, per-role MCP tool allowlists, Docker sandboxing for code execution and Playwright, secrets management (Vault / cloud KMS), domain allowlists, and supply-chain controls for MCP server upgrades. |
| [07-roadmap.md](./07-roadmap.md) | Phased implementation plan from Phase 0 (monorepo scaffolding) through Phase 11 (observability and hardening); deliverables, packages affected, design decisions locked in, and exit criteria for each phase. |

### Research Notes

| File | Description |
|------|-------------|
| [research/openhands-context-management.md](./research/openhands-context-management.md) | Analysis of context management in the OpenHands agent SDK: why its agents burn tokens at a high rate, thirteen identified gaps (condensation triggered at the full context window, size-blind event counts, a summariser fed 500-character previews without tool arguments, no observation lifecycle, context isolation off by default), and a layered redesign proposal. Closes with what Agent Studio already avoids by construction and what remains open for us. |
| [research/openhands-context-cost-model.py](./research/openhands-context-cost-model.py) | Dependency-free policy simulator backing the cost comparisons in the note above. Re-implements the OpenHands condenser's trigger arithmetic over a synthetic event stream and sweeps condensation thresholds. |

### Architectural Decision Records (13 ADRs)

| File | Decision |
|------|----------|
| [adr/0001-typescript-monorepo.md](./adr/0001-typescript-monorepo.md) | Use TypeScript + pnpm workspaces + Turborepo as the monorepo foundation. |
| [adr/0002-provider-agnostic-llm.md](./adr/0002-provider-agnostic-llm.md) | Wrap LLM calls behind a `LLMProvider` interface so any model can be swapped in without touching agent logic. |
| [adr/0003-claude-agent-sdk-default.md](./adr/0003-claude-agent-sdk-default.md) | Adopt `@anthropic-ai/claude-agent-sdk` as the default agent runtime and Claude as the default model. |
| [adr/0004-mcp-client-transport.md](./adr/0004-mcp-client-transport.md) | Support stdio, streamable-http, and sse transports in the central MCP client; choose per server in config. |
| [adr/0005-delegate-memory-to-ruflo.md](./adr/0005-delegate-memory-to-ruflo.md) | Delegate all persistent memory to Ruflo via MCP rather than running a bespoke pgvector layer. |
| [adr/0006-consume-code-review-graph-mcp.md](./adr/0006-consume-code-review-graph-mcp.md) | Consume `tirth8205/code-review-graph` as an external MCP server rather than re-implementing structural code analysis. |
| [adr/0007-playwright-test-loop.md](./adr/0007-playwright-test-loop.md) | Drive all E2E testing through the Playwright MCP server running in a Docker sandbox, with test surface derived from `graph.tests_for`. |
| [adr/0008-knowledge-retrieval-federation.md](./adr/0008-knowledge-retrieval-federation.md) | Build the Knowledge Retrieval layer as an internal MCP server federating web, Confluence, SharePoint, and GitHub search behind a single `knowledge.search` tool. |
| [adr/0009-consume-ruflo-via-mcp-not-fork.md](./adr/0009-consume-ruflo-via-mcp-not-fork.md) | Consume Ruflo as an upstream distribution via MCP only; do not fork it; explicitly do not use its swarm/consensus/routing features. |
| [adr/0010-mcp-server-registry-and-allowlists.md](./adr/0010-mcp-server-registry-and-allowlists.md) | Introduce a first-class MCP Server Registry with per-role tool allowlists, version pinning, and hot-reload as a platform primitive. |
| [adr/0011-dynamic-mcp-manager-and-catalog.md](./adr/0011-dynamic-mcp-manager-and-catalog.md) | Extend the registry with a dynamic manager (install/upgrade/enable/disable/remove without redeploy) and a curated marketplace catalog. |
| [adr/0012-embed-claude-code-as-deep-worker.md](./adr/0012-embed-claude-code-as-deep-worker.md) | Embed Claude Code as the deep-work inner loop via `DispatchEnvelope`; outer roles are coordinators only; Planner is denied `claude_code.*` tools. |
| [adr/0013-cloud-hosted-no-local-agents.md](./adr/0013-cloud-hosted-no-local-agents.md) | Deploy Agent Studio as a centrally hosted cloud service; agents never run locally on user machines; VS Code extension and browser are thin clients only. |

---

## How This Documentation Is Organized

The documentation intentionally mirrors the C4 model:

1. **Overview** (`00-overview.md`) — *why* the system exists and what it must achieve.
2. **Architecture** (`01-architecture.md`) — *what* the system looks like at the context, container, and package level.
3. **Components** (`02-components/`) — *how* each internal subsystem works in detail.
4. **Integrations** (`02-integrations/`) — *how* Agent Studio connects to every external capability.
5. **Data / API / Sequences** (`03–05`) — the contracts that hold the system together.
6. **Security** (`06-security.md`) — cross-cutting security posture.
7. **Roadmap** (`07-roadmap.md`) — *when* each capability is built and in what order.
8. **ADRs** (`adr/`) — the *why not* of key design alternatives that were considered and rejected.

All diagrams are written in [Mermaid](https://mermaid.js.org/) and render natively on GitHub, GitLab, and Bitbucket.

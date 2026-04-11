# Agent Studio

**Centrally hosted platform for autonomous software delivery** — driven by planner → coder → tester → reviewer agents, backed by persistent memory, structural code understanding, federated knowledge retrieval, and a first-class human-in-the-loop control plane.

Users connect from **VS Code** or a **browser**. Agents never run locally.

---

## What it does

1. You submit a business requirement (text, issue link, or file).
2. A **Planner** agent reads the codebase structure (via `code-review-graph`) and prior memory (via Ruflo), then produces a plan.
3. A **Coder** agent dispatches the plan to a **Claude Code deep-coding worker** that iteratively edits, commits, and verifies code — using your enterprise WMS, Git, and filesystem via MCP.
4. A **Tester** agent determines the exact test surface (via `graph.tests_for` + `graph.impact_radius`), runs Playwright E2E tests in a Docker sandbox, and loops through failures with memory and knowledge retrieval before dispatching fixes.
5. A **Reviewer** agent assembles a **Delivery Bundle** — blast-radius analysis, auto-generated wiki, interactive code graph, risk-scored change summary — and opens a HITL-gated PR.
6. You approve or steer from VS Code or the browser at any point.

---

## Architecture at a glance

- **Orchestrator** — Fastify + WebSocket service; owns the task state machine, BullMQ queue, event streaming, and HITL flows
- **Agent Runtime** — Planner / Coder / Tester / Reviewer as `@anthropic-ai/claude-agent-sdk` subagents behind a provider-agnostic `LLMProvider` interface (Claude default)
- **Deep Coding Workers** — Claude Code embedded as the inner loop: in-process `query()` for most work, Docker-sandboxed subprocess for isolation
- **MCP Client** — single package connecting to every external capability (Ruflo, Git, GitHub, WMS, Playwright, Filesystem, Fetch, code-review-graph, knowledge retrieval) with per-role allowlists and approval hooks
- **MCP Registry/Manager** — add, upgrade, or disable MCP servers at runtime without redeployment — same model as the SKILLs loader
- **Knowledge Retrieval MCP** — federated search over web (Tavily/Brave/SerpAPI), Confluence, SharePoint, and GitHub before agents attempt their own fix
- **Web UI** — Next.js: task graph, agent transcripts, MCP call log, Delivery Bundle viewer, MCP Marketplace, HITL approval queue
- **VS Code Extension** — same WebSocket API as the Web UI; full parity; seamless session switching

→ Full architecture: [`docs/01-architecture.md`](docs/01-architecture.md)

---

## Documentation

| Doc | Description |
|---|---|
| [`docs/README.md`](docs/README.md) | Doc index and reading order |
| [`docs/00-overview.md`](docs/00-overview.md) | Goals, non-goals, success criteria, spec traceability |
| [`docs/01-architecture.md`](docs/01-architecture.md) | C4 context + container diagrams, monorepo package map |
| **Components** | |
| [`docs/02-components/orchestrator.md`](docs/02-components/orchestrator.md) | Task graph scheduler, state machine, BullMQ |
| [`docs/02-components/agent-runtime.md`](docs/02-components/agent-runtime.md) | Planner/Coder/Tester/Reviewer roles, anti-nesting invariants |
| [`docs/02-components/llm-abstraction.md`](docs/02-components/llm-abstraction.md) | Provider-agnostic LLMProvider interface |
| [`docs/02-components/skills-loader.md`](docs/02-components/skills-loader.md) | Loading user's SKILLs repo into agents |
| [`docs/02-components/mcp-client.md`](docs/02-components/mcp-client.md) | Central MCP client, transports, per-role allowlists |
| [`docs/02-components/mcp-registry.md`](docs/02-components/mcp-registry.md) | Dynamic MCP server registry/manager |
| [`docs/02-components/deep-coding-workers.md`](docs/02-components/deep-coding-workers.md) | Claude Code as the inner loop, DispatchEnvelope |
| [`docs/02-components/delivery-bundle.md`](docs/02-components/delivery-bundle.md) | Reviewer-assembled final delivery artifact |
| [`docs/02-components/task-state.md`](docs/02-components/task-state.md) | Task lifecycle, pause/resume, checkpoints |
| [`docs/02-components/testing-pipeline.md`](docs/02-components/testing-pipeline.md) | Playwright loop, graph-derived test surface |
| [`docs/02-components/hosting-and-deployment.md`](docs/02-components/hosting-and-deployment.md) | Cloud topology, multi-tenancy, dev/staging/prod |
| [`docs/02-components/execution-control.md`](docs/02-components/execution-control.md) | Steering verbs: pause/resume/inject/branch/cancel |
| [`docs/02-components/vscode-extension.md`](docs/02-components/vscode-extension.md) | VS Code plugin |
| [`docs/02-components/web-ui.md`](docs/02-components/web-ui.md) | Next.js control panel |
| [`docs/02-components/human-in-the-loop.md`](docs/02-components/human-in-the-loop.md) | Clarification, approvals, interrupts |
| **Integrations** | |
| [`docs/02-integrations/README.md`](docs/02-integrations/README.md) | Integration matrix: all MCP servers × roles × tools |
| [`docs/02-integrations/ruflo.md`](docs/02-integrations/ruflo.md) | Persistent memory via Ruflo MCP |
| [`docs/02-integrations/wms.md`](docs/02-integrations/wms.md) | Enterprise WMS MCP server |
| [`docs/02-integrations/git.md`](docs/02-integrations/git.md) | Git MCP (clone, branch, commit, diff) |
| [`docs/02-integrations/github.md`](docs/02-integrations/github.md) | GitHub MCP (PRs, issues, code search) |
| [`docs/02-integrations/playwright.md`](docs/02-integrations/playwright.md) | Playwright MCP (browser automation, test exec) |
| [`docs/02-integrations/filesystem.md`](docs/02-integrations/filesystem.md) | Filesystem MCP (scoped workspace I/O) |
| [`docs/02-integrations/fetch.md`](docs/02-integrations/fetch.md) | Fetch MCP (URL → markdown) |
| [`docs/02-integrations/knowledge.md`](docs/02-integrations/knowledge.md) | Knowledge Retrieval MCP (web/Confluence/SharePoint) |
| [`docs/02-integrations/claude-code-worker.md`](docs/02-integrations/claude-code-worker.md) | ClaudeCode Worker MCP (in-process + sandboxed) |
| [`docs/02-integrations/code-review-graph.md`](docs/02-integrations/code-review-graph.md) | code-review-graph MCP (blast-radius, wiki, delivery bundle) |
| **Cross-cutting** | |
| [`docs/03-data-model.md`](docs/03-data-model.md) | Task/run/event schemas (orchestrator DB) |
| [`docs/04-api-contracts.md`](docs/04-api-contracts.md) | REST + WebSocket API surface |
| [`docs/05-sequence-flows.md`](docs/05-sequence-flows.md) | End-to-end execution sequence diagrams |
| [`docs/06-security.md`](docs/06-security.md) | AuthN/Z, tenancy, secrets, sandboxing |
| [`docs/07-roadmap.md`](docs/07-roadmap.md) | Phased implementation plan (Phases 0–11) |
| **ADRs** | |
| [`docs/adr/0001-typescript-monorepo.md`](docs/adr/0001-typescript-monorepo.md) | pnpm + Turborepo monorepo |
| [`docs/adr/0002-provider-agnostic-llm.md`](docs/adr/0002-provider-agnostic-llm.md) | LLMProvider interface |
| [`docs/adr/0003-claude-agent-sdk-default.md`](docs/adr/0003-claude-agent-sdk-default.md) | Claude Agent SDK as default runtime |
| [`docs/adr/0004-mcp-client-transport.md`](docs/adr/0004-mcp-client-transport.md) | Three MCP transports |
| [`docs/adr/0005-delegate-memory-to-ruflo.md`](docs/adr/0005-delegate-memory-to-ruflo.md) | No in-house vector DB |
| [`docs/adr/0006-consume-code-review-graph-mcp.md`](docs/adr/0006-consume-code-review-graph-mcp.md) | No in-house code graph |
| [`docs/adr/0007-playwright-test-loop.md`](docs/adr/0007-playwright-test-loop.md) | Graph-derived test scoping |
| [`docs/adr/0008-knowledge-retrieval-federation.md`](docs/adr/0008-knowledge-retrieval-federation.md) | Federated knowledge retrieval |
| [`docs/adr/0009-consume-ruflo-via-mcp-not-fork.md`](docs/adr/0009-consume-ruflo-via-mcp-not-fork.md) | Ruflo not forked |
| [`docs/adr/0010-mcp-server-registry-and-allowlists.md`](docs/adr/0010-mcp-server-registry-and-allowlists.md) | Per-role allowlists |
| [`docs/adr/0011-dynamic-mcp-manager-and-catalog.md`](docs/adr/0011-dynamic-mcp-manager-and-catalog.md) | Hot-reload MCP registry |
| [`docs/adr/0012-embed-claude-code-as-deep-worker.md`](docs/adr/0012-embed-claude-code-as-deep-worker.md) | Claude Code as inner loop |
| [`docs/adr/0013-cloud-hosted-no-local-agents.md`](docs/adr/0013-cloud-hosted-no-local-agents.md) | Cloud-hosted, no local agents |

---

## Key external dependencies

| Dependency | Role | Notes |
|---|---|---|
| `@anthropic-ai/claude-agent-sdk` | Agent runtime + in-process deep-coding worker | Default LLM provider |
| `anthropics/claude-code` | Sandboxed deep-coding worker (Docker mode) | Hosted with Agent Studio |
| `@modelcontextprotocol/sdk` | MCP client transports | stdio / streamable-http / sse |
| `ruvnet/ruflo` | Persistent cross-session memory | Consumed via MCP — not forked |
| `tirth8205/code-review-graph` | Structural code graph + delivery bundle | Consumed via MCP — not forked |
| `BullMQ` + Redis | Task queue | Managed Redis in production |
| Fastify | Orchestrator HTTP/WebSocket server | |
| Next.js | Web control panel | |
| pnpm + Turborepo | Monorepo toolchain | |

---

## Implementation plan

See [`docs/07-roadmap.md`](docs/07-roadmap.md) for the full phased plan (Phase 0–11).

**Quick summary:**
- Phase 0–1: Monorepo + orchestrator + first agent
- Phase 1.5–2: Deep Coding Workers + MCP client + registry
- Phase 3–5: SKILLs, Ruflo memory, WMS, GitHub, knowledge retrieval
- Phase 6–7: code-review-graph, Delivery Bundle, Playwright test loop
- Phase 8–9: Web UI + VS Code extension + execution-control verbs
- Phase 10–11: Cloud deployment + observability + hardening

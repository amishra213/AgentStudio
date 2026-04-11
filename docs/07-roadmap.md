# Phased Implementation Roadmap

This document captures the phased delivery plan for Agent Studio. Each phase has a clear deliverable, the packages it touches, the key design decisions it locks in, and exit criteria that must be met before the next phase begins.

The phases are ordered by dependency: later phases build on earlier ones. Within a phase, work can be parallelised across packages.

---

## Phase 0 — Monorepo Scaffolding

**Goal:** A working, buildable repository that every subsequent phase can build on.

**Deliverables:**
- pnpm workspace + Turborepo pipeline (`build`, `lint`, `test`, `typecheck` tasks)
- ESLint + Prettier + TypeScript strict mode configured workspace-wide
- `shared-types` package with canonical enums, Zod schemas for `Task`, `TaskRun`, `TaskEvent`, `Checkpoint`, `HitlRequest`, `McpServerSpec`, `DispatchEnvelope`, `KnowledgeHit`, `MemoryHit`
- Config loader (`agent-studio.config.ts`) with typed schema and environment-variable override support
- Secrets backend abstraction: `SecretsProvider` interface with `EnvSecretsProvider` implementation (for local dev) and a stub `VaultSecretsProvider`
- CI pipeline (GitHub Actions or equivalent): lint → typecheck → build → unit test on every PR
- `docker-compose.yml` for local dev: Postgres + Redis only (no MCP sidecars yet)

**Packages affected:** `shared-types`, monorepo root

**Design decisions locked in:**
- pnpm + Turborepo as the monorepo toolchain (ADR-0001)
- TypeScript strict mode across all packages
- Zod as the schema/validation library for all cross-package types

**Exit criteria:**
- `pnpm build` succeeds from repo root
- `pnpm test` passes (unit tests for `shared-types` schema validation)
- `docker-compose up` starts Postgres + Redis without errors
- CI pipeline passes on a blank PR

---

## Phase 1 — Orchestrator + LLM Abstraction + First Agent

**Goal:** A running orchestrator service that can dispatch a trivial task to a single Planner agent and return a result.

**Deliverables:**
- `llm` package: `LLMProvider` interface (`generate`, `stream`, `embed` methods) + `ClaudeProvider` adapter using `@anthropic-ai/claude-agent-sdk`
- `orchestrator` package: Fastify HTTP server, WebSocket endpoint, BullMQ task queue wired to Redis, basic task state machine (`not_started → planning → completed / failed`), Postgres schema migrations (tasks, task_runs, task_events, audit_log tables)
- `agent-runtime` package: single `PlannerAgent` implemented as a Claude SDK subagent, system prompt, no MCP tools yet (plain text planning only)
- `POST /tasks` endpoint accepts a `requirement` string and returns a task ID
- `GET /tasks/:id/events` WebSocket streams task events to a client
- Basic JWT auth middleware (HS256, no OAuth yet — static signing secret for Phase 1)

**Packages affected:** `llm`, `orchestrator`, `agent-runtime`, `shared-types`

**Design decisions locked in:**
- Claude Agent SDK as the default agent runtime (ADR-0003)
- Provider-agnostic `LLMProvider` interface (ADR-0002)
- Fastify as the orchestrator HTTP framework
- BullMQ + Redis as the task queue

**Exit criteria:**
- `POST /tasks` with a text requirement returns a task ID
- Planner agent produces a text plan and the task transitions to `completed`
- Task events stream to a WebSocket client in real time
- Unit tests for state machine transitions pass

---

## Phase 1.5 — Deep Coding Worker

**Goal:** The `deep-coding` package and its ClaudeCode Worker MCP server are operational. Coder role can dispatch to an in-process worker; sandboxed worker runs in Docker.

**Deliverables:**
- `deep-coding` package:
  - `claude_code.run` tool: in-process `query()` session via `@anthropic-ai/claude-agent-sdk`, emits streaming progress events
  - `claude_code.spawn_worker` tool: spawns headless Claude Code in a per-task Docker container with read-only repo snapshot, overlay FS, scoped MCP config, env-injected secrets, resource limits
  - `claude_code.status`, `claude_code.cancel`, `claude_code.stream_events` tools
  - Internal ClaudeCode Worker MCP server exposing the above tools
- `DispatchEnvelope` and `WorkerResult` TypeScript types finalised and exported from `shared-types`
- `CoderAgent` in `agent-runtime`: dispatches via `DispatchEnvelope` to `claude_code.run`; does NOT re-plan (anti-nesting invariant enforced — `claude_code.*` tools excluded from Planner's allowlist)
- Orchestrator wires the ClaudeCode Worker MCP server into Phase 1's MCP client (pre-registry stub)

**Packages affected:** `deep-coding`, `agent-runtime`, `shared-types`, `orchestrator`

**Design decisions locked in:**
- Claude Code as the deep-work inner loop (ADR-0012)
- `DispatchEnvelope` as the single boundary between outer roles and inner loop
- Anti-nested-planning invariant: Planner denied `claude_code.*` tools

**Exit criteria:**
- `claude_code.run` successfully completes a trivial coding task (e.g. create a file) and returns a diff
- `claude_code.spawn_worker` runs in Docker with resource limits enforced
- Orchestrator streams worker progress events to WebSocket clients
- Planner cannot invoke `claude_code.*` tools (blocked at allowlist check)

---

## Phase 2 — MCP Client + Registry/Manager

**Goal:** The full `mcp-client` package with per-role allowlists, approval hooks, health monitoring, and the MCP Registry/Manager subsystem. First three external servers wired.

**Deliverables:**
- `mcp-client` package: stdio / streamable-http / sse transport support, `McpServerSpec` type, per-role allowlist enforcement, approval hook (raises `hitl.question` event before forwarding approval-gated calls), heartbeat + `tool_unavailable` event on failure, observability log per call
- MCP Registry/Manager: layered config sources (tenant DB overrides > project `agent-studio.mcp.yaml` > platform defaults in `config/mcp-servers.d/`), DB `mcp_server_registrations` table, hot-reload via DB LISTEN/NOTIFY + file watcher, lifecycle CLI (`mcp list/install/upgrade/disable/enable/remove/test/describe`), audit log for registry mutations
- First three external MCP servers registered and tested: **Filesystem MCP**, **Git MCP**, **Fetch MCP**
- ClaudeCode Worker MCP registered as an internal server

**Packages affected:** `mcp-client`, `orchestrator`, `shared-types`

**Design decisions locked in:**
- MCP as the universal tool boundary (ADR-0004)
- Per-role allowlists, per-task tightening-only overrides (ADR-0010)
- Dynamic MCP Registry with hot-reload (ADR-0011)
- New tools default to DENIED after upgrade

**Exit criteria:**
- Coder agent reads/writes files via Filesystem MCP and commits via Git MCP
- Fetch MCP fetches a URL and returns markdown; domain allowlist blocks an out-of-list domain
- `mcp list` CLI shows all registered servers with health status
- Hot-reload: adding a server entry to the DB is reflected in the running orchestrator within 5 seconds without restart
- An approval-gated tool call raises a `hitl.question` event and blocks until answered

---

## Phase 3 — SKILLs Loader + Ruflo Memory

**Goal:** Agents can load skills from a user-configured SKILLs directory, and all memory operations flow through Ruflo via MCP.

**Deliverables:**
- SKILLs loader in `agent-runtime`: scans `SKILL.md` + optional scripts in the SKILLs directory at session start, registers each skill via the SDK's skill-loading hook, precedence rules (tenant > project > platform defaults)
- Ruflo MCP server registered in the default catalog: `McpServerSpec` for both stdio (local dev) and HTTP (central) transports, tools: `memory.store`, `memory.search`, `pattern.lookup`, `pattern.store`
- `MemoryClient` wrapper in `agent-runtime`: `remember(scope, kind, payload)` + `recall(query, topK)` normalising over Ruflo's tool names
- Scope mapping: Agent Studio `(tenant, project, task)` → Ruflo `user/project/local` scopes
- Write points wired: after planning, after each successful fix, after test pass, on HITL answer, on task completion
- Read points wired: before planning, before each retry, before review, on test failure (before knowledge retrieval)
- Fallback: if Ruflo unreachable, task continues with a `memory_unavailable` warning event

**Packages affected:** `agent-runtime`, `mcp-client` (Ruflo server registration), `orchestrator`

**Design decisions locked in:**
- No in-house vector DB — memory delegated to Ruflo (ADR-0005)
- Ruflo consumed via MCP, not forked (ADR-0009)

**Exit criteria:**
- A skill defined in the SKILLs directory is available to the Planner and Coder agents
- After task completion, `memory.search` returns the stored plan and fix patterns
- A subsequent task retrieves prior memory in `recall()` before planning
- With Ruflo stopped, tasks complete with a warning (no crash)

---

## Phase 4 — WMS MCP + GitHub MCP

**Goal:** The two primary enterprise integrations are live: the user's WMS server and GitHub.

**Deliverables:**
- **WMS MCP**: register the user's existing WMS server in the MCP Registry (transport from user config), per-role allowlist (coder: read+write; planner/reviewer: read), approval gating on `wms.update_config` and `wms.apply_patch`, failure mode (block HITL on write failure)
- **GitHub MCP**: register the upstream GitHub-maintained MCP server, tools: `github.create_pr`, `github.list_prs`, `github.get_pr`, `github.add_comment`, `github.search_code`, `github.search_issues`, `github.merge_pr`, per-role allowlist (coder: create+comment; reviewer: review+merge; planner/tester: read), approval gating on `create_pr` and `merge_pr`
- Reviewer agent wires `github.create_pr` as the final delivery step (HITL-gated)

**Packages affected:** `mcp-client` (server registrations), `agent-runtime` (reviewer role), `orchestrator`

**Exit criteria:**
- Coder agent reads WMS config via `wms.read_config`; write attempt triggers HITL approval
- Reviewer agent opens a draft PR on GitHub after task completion; merge is HITL-gated
- `github.search_code` returns results accessible to all roles

---

## Phase 5 — Knowledge Retrieval MCP

**Goal:** Agents can search for prior solutions across web, GitHub, Confluence, and SharePoint before attempting their own fix.

**Deliverables:**
- `knowledge` package: internal Knowledge Retrieval MCP server with `knowledge.search(query, sources?, topK)` and `knowledge.fetch(url)` tools
- Adapters: **web** (Tavily/Brave/SerpAPI — pluggable), **GitHub** (delegates to GitHub MCP `search_code` + `search_issues`), **Confluence** (Atlassian REST v2 + CQL), **SharePoint** (Microsoft Graph `/search/query`)
- Normalised `KnowledgeHit` type; reciprocal rank fusion re-ranking; per-query-hash caching for task lifetime
- Per-tenant config: which sources are enabled; credentials via secrets backend
- Agent integration: Coder calls `knowledge.search` proactively before a non-trivial fix; Tester calls it before dispatching a fix after test failure

**Packages affected:** `knowledge`, `mcp-client`, `agent-runtime`

**Design decisions locked in:**
- Knowledge Retrieval as an internal MCP server (ADR-0008)
- GitHub search delegated to GitHub MCP server (not reimplemented)

**Exit criteria:**
- `knowledge.search("authentication timeout WMS")` returns ranked hits from configured sources
- With only web + GitHub enabled, Confluence/SharePoint adapters are skipped cleanly
- Per-query caching: second identical call within a task returns the cached result without an external request
- Pre-fetched `knowledgeContext` appears in the `DispatchEnvelope` sent to the Coder worker

---

## Phase 6 — code-review-graph MCP Integration + Delivery Bundle

**Goal:** code-review-graph is live and the reviewer role can produce a complete Delivery Bundle.

**Deliverables:**
- Register `tirth8205/code-review-graph` in the MCP Registry (stdio or Docker sidecar, pinned version)
- Planner wires `graph.architecture_overview` + `graph.semantic_search` before planning (token-efficient code understanding)
- Coder wires `graph.update` + `graph.detect_changes` after every Git commit
- Tester wires `graph.tests_for` + `graph.impact_radius` to determine the exact test surface
- Reviewer assembles Delivery Bundle: `graph.impact_radius` → `graph.tests_for` → `graph.detect_changes` → `graph.wiki_generate` → `graph.visualize`
- Delivery Bundle persisted in `task_events` and surfaced as a `task.delivery_bundle_ready` WebSocket event
- Fallback: if code-review-graph unreachable, reviewer falls back to diff-based summary and flags `partial_delivery`

**Packages affected:** `mcp-client` (server registration), `agent-runtime` (all 4 roles), `orchestrator`, `shared-types` (DeliveryBundle type)

**Design decisions locked in:**
- No in-house tree-sitter/call-graph — consumed from code-review-graph (ADR-0006)

**Exit criteria:**
- Planner receives an architecture overview without ingesting the entire codebase
- After a coder commit, `graph.update` completes in under 5 seconds on the test repo
- Reviewer produces a Delivery Bundle with impact_radius, tests_for, risk-scored summary, wiki, and visualize HTML
- With code-review-graph stopped, task completes with a `partial_delivery` flag (no crash)

---

## Phase 7 — Playwright MCP + Full Test Loop

**Goal:** The tester agent runs a complete test loop: graph-derived test surface → Playwright execution → memory/knowledge-backed failure handling → fix loop → pass.

**Deliverables:**
- Playwright MCP server registered in the MCP Registry (stdio inside Docker sandbox, `tester` role only)
- Docker sandbox config: no external network, report volume mounted, `@playwright/mcp` pinned version
- Tester agent full loop: `graph.tests_for` + `graph.impact_radius` → generate spec via `claude_code.run` → `playwright.run_test` → on failure: `memory.search` (Ruflo) + `knowledge.search` → `DispatchEnvelope` to Coder worker (with `knowledgeContext`) → fix committed → `graph.update` → re-run
- Loop exit conditions: pass-rate/coverage thresholds met, OR max-iterations reached (task transitions to `blocked` for HITL)
- Pass/fail thresholds configurable per project in `agent-studio.mcp.yaml`

**Packages affected:** `mcp-client`, `agent-runtime` (tester role), `testing`, `orchestrator`

**Design decisions locked in:**
- Playwright MCP in Docker sandbox; graph-derived test scoping (ADR-0007)
- Memory + knowledge lookup before fix dispatch (retrieval-first failure handling)

**Exit criteria:**
- Tester generates a Playwright spec for a code change without guessing the test surface
- A deliberately introduced bug causes the loop to: detect failure → retrieve from Ruflo/knowledge → fix → retest → pass
- With max-iterations reached, task blocks for HITL (no infinite loop)
- Playwright Docker container has no external network access

---

## Phase 8 — Web UI Control Panel + HITL + MCP Manager UI + Delivery Bundle Viewer

**Goal:** A fully functional Next.js control panel that surfaces all platform capabilities and handles all HITL interactions.

**Deliverables:**
- `web` package: Next.js app with:
  - **Task list + submission form**: submit requirement, workspace config, budget, tenant
  - **Live task graph view**: real-time state transitions and agent transcripts
  - **MCP call log**: every tool call across all servers with latency, result, cost; filterable by role/server/tool
  - **Knowledge-hit inspector**: what `knowledge.search` returned for each query
  - **Memory browser**: reads Ruflo memory via MCP for the current task/project/tenant scope
  - **MCP server health dashboard**: registered servers, versions, health status, allowlist per role
  - **HITL approval queue**: approve/reject pending tool calls and `askHuman` questions
  - **Run history**: past tasks with cost, duration, exit reason
  - **Delivery Bundle viewer**: embeds `graph.visualize` interactive HTML, risk-scored change summary, auto-wiki, test coverage report
  - **MCP Marketplace**: catalog of known-good servers; Install/Upgrade/Disable/Remove actions; raw `McpServerSpec` input

**Packages affected:** `web`, `orchestrator` (REST/WebSocket API surface finalised)

**Exit criteria:**
- All HITL approval flows completable from the Web UI
- Delivery Bundle renders with interactive graph, wiki, and risk summary
- MCP Marketplace: installing a new server from catalog makes its tools available within 5 seconds
- MCP call log shows all tool calls with latency for a completed task

---

## Phase 9 — VS Code Extension + Session Sync + Execution-Control Verbs

**Goal:** VS Code extension reaches full parity with the Web UI; all 11 execution-control verbs are wired end-to-end from both surfaces.

**Deliverables:**
- `vscode-extension` package: VS Code WebSocket client, task list panel, diff viewer, HITL approval panel, same session token as Web UI
- Session bridging: opening the same task in VS Code and browser shows a single conversation and todo list (one authoritative state on the server)
- All 11 execution-control verbs wired: `task.submit`, `task.pause`, `task.resume`, `task.inject_context`, `task.override_plan`, `task.approve`, `task.reject`, `task.cancel`, `task.branch`, `task.rollback`, `task.set_budget`
- Parity matrix document (Web UI vs VS Code): every feature in both surfaces
- OAuth PKCE auth: VS Code stores token in secret storage; browser in secure cookie; shared silent refresh

**Packages affected:** `vscode-extension`, `orchestrator` (steering verbs), `web`

**Exit criteria:**
- Task started in browser can be paused/resumed from VS Code extension
- HITL approval in VS Code reflects immediately in the browser view
- `task.branch` creates a fork at the current checkpoint; both branches visible in both surfaces
- Parity matrix: 0 features missing from either surface

---

## Phase 10 — Cloud Deployment Profiles

**Goal:** Three deployment footprints documented and tested: dev (docker-compose), staging (k8s single namespace), production (HA with managed Postgres/Redis/Vault + dedicated worker node pool).

**Deliverables:**
- **Dev:** `docker-compose.yml` with all services (Orchestrator, Web UI, Postgres, Redis, Ruflo sidecar, code-review-graph sidecar, Playwright sidecar, stub Vault)
- **Staging:** k8s manifests (single namespace, small worker node pool, managed Postgres + Redis, real Vault); Helm chart with values file
- **Production:** HA Orchestrator (≥2 replicas behind LB), managed Postgres (RDS/Cloud SQL/Azure DB), managed Redis (ElastiCache/Memorystore), dedicated worker node pool for Claude Code k8s Jobs, production Vault, CDN for Web UI, separate k8s namespace per environment
- Multi-tenancy verification: tenant A cannot read tenant B's tasks or memory

**Packages affected:** Infrastructure (Helm charts, docker-compose, k8s manifests) — no package code changes

**Exit criteria:**
- `docker-compose up` starts all services and a full task runs end-to-end
- Staging: a task runs end-to-end in the k8s cluster; orchestrator can be scaled to 2 replicas without state loss
- Production: HA orchestrator survives a pod restart mid-task (picks up from checkpoint)
- Multi-tenancy: cross-tenant data isolation verified by test

---

## Phase 11 — Observability, Cost Tracking, Multi-Provider Failover, Hardening

**Goal:** Production-ready platform: full observability, cost enforcement, LLM provider failover, security hardening.

**Deliverables:**
- **Observability:** OpenTelemetry traces for every task run (orchestrator → agent role → MCP tool call → worker → result); structured JSON logs; Grafana dashboards for task throughput, MCP call latency P50/P95/P99, worker cost per task, Ruflo memory hit rate
- **Cost tracking:** per-tenant token budget enforcement before every Claude Code dispatch; cost ceiling alerts; cost breakdown in Web UI run history
- **Multi-provider failover:** if Claude API returns 5xx/rate-limit, `LLMProvider` falls back to a configured secondary provider (e.g. OpenAI GPT-4o); failover logged and surfaced in task events
- **Hardening:** penetration test scope (JWT validation, per-tenant RLS, MCP allowlist bypass attempts, Fetch domain allowlist bypass); automated supply-chain checks on MCP server upgrades (allowlist diff + changelog review); secret rotation runbook; Claude Code worker container CVE scanning
- **Performance:** load test at 50 concurrent tasks; identify and fix bottlenecks in orchestrator dispatch and MCP client connection pooling

**Packages affected:** All (`shared-types` for telemetry types, `orchestrator`, `agent-runtime`, `mcp-client`, `llm`, `deep-coding`)

**Exit criteria:**
- End-to-end trace visible in Grafana for a complete task run
- Cost ceiling enforced: a task exceeding the tenant budget is cancelled with a `over_budget` exit reason
- LLM provider failover: with Claude API mocked to return 503, task completes via secondary provider
- 50 concurrent tasks complete without orchestrator OOM or queue starvation
- Zero high-severity findings from penetration test (or mitigations documented)

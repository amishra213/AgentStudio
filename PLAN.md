# Plan: Agent Studio – Architecture & Design Documentation

## Context

The target repository is currently empty (only `LICENSE` + `README.md`). The user wants a **centrally hosted Agent Studio platform** that drives autonomous/semi-autonomous software delivery through planner → coder → tester → reviewer agents, backed by persistent memory, MCP-based tool use (including an already-built WMS MCP server), Playwright testing, a VS Code extension, and a web control panel. The docs produced here are intended to be portable — any downstream environment should be able to drop them into its own repository without rewrites.

This first delivery is **architecture + design docs only — no runnable code**. The user confirmed:

- **Language:** TypeScript / Node.js across backend, extension, web UI, and MCP pieces.
- **Agent runtime:** Provider-agnostic LLM abstraction, with **Claude as the default** so agents can load an existing user **SKILLs repo**.
- **WMS integration:** The user already has a WMS MCP **server**; Agent Studio only needs to be an **MCP client** that can connect to it. They pointed at `ruvnet/ruflo` as a reference pattern for MCP client + persistent memory + swarm orchestration.
- **Persistent memory:** Ruflo already ships cross-session persistent memory (HNSW-indexed vector memory, PostgreSQL RuVector, AgentDB, 8 memory types across project/local/user scopes). Agent Studio will **consume Ruflo's memory via MCP** instead of standing up its own pgvector layer.
- **Knowledge retrieval:** Agents must be able to search external reference sources — web, Confluence, SharePoint, and GitHub (code / issues / PRs across org repos) — so they can check whether a similar problem has already been solved before attempting their own fix.
- **No existing code to reuse** (greenfield).

The goal of the docs is to be concrete enough that an implementation team (or Claude itself in a later session) can start building each component without re-deriving the architecture.

## Deliverable

A `docs/` tree committed to the active feature branch, plus a refreshed top-level `README.md` that points into it. All files are Markdown; diagrams rendered as Mermaid so they render natively on any Git forge. The tree is self-contained and can be lifted into any downstream repo.

```
<repo-root>/
├── README.md                         # rewritten: project pitch + docs index
└── docs/
    ├── README.md                     # doc index / reading order
    ├── 00-overview.md                # goals, non-goals, success criteria
    ├── 01-architecture.md            # C4-style context + container diagrams
    ├── 02-components/
    │   ├── orchestrator.md           # central task/graph scheduler
    │   ├── agent-runtime.md          # planner / coder / tester / reviewer
    │   ├── llm-abstraction.md        # provider-agnostic layer, Claude default
    │   ├── skills-loader.md          # loading user's SKILLs repo into agents
    │   ├── mcp-client.md             # central MCP client, transports, per-role allowlists
    │   ├── mcp-registry.md           # dynamic MCP server registry/manager (add/upgrade/remove)
    │   ├── deep-coding-workers.md    # Claude Code as the inner loop (dispatch envelope, modes, anti-nesting)
    │   ├── delivery-bundle.md        # how the reviewer assembles the final delivery artifact
    │   ├── task-state.md             # lifecycle, pause/resume, HITL
    │   ├── testing-pipeline.md       # Playwright loop + success thresholds
    │   ├── hosting-and-deployment.md # cloud topology, multi-tenancy, dev/staging/prod footprints
    │   ├── execution-control.md      # steering verbs (pause/resume/inject/override/cancel/branch)
    │   ├── vscode-extension.md       # IDE plugin, WebSocket client, parity w/ web UI
    │   ├── web-ui.md                 # Next.js control panel, parity w/ extension
    │   └── human-in-the-loop.md      # clarification, approvals, interrupts
    ├── 02-integrations/              # one file per MCP server Agent Studio talks to
    │   ├── README.md                 # integration matrix (server × agent role × tools)
    │   ├── ruflo.md                  # persistent memory + patterns (external process)
    │   ├── wms.md                    # user's enterprise WMS MCP server
    │   ├── git.md                    # Git MCP (clone, branch, commit, diff, push)
    │   ├── github.md                 # GitHub MCP (PRs, issues, code search)
    │   ├── playwright.md             # Playwright MCP (browser automation, test exec)
    │   ├── filesystem.md             # Filesystem MCP (scoped workspace I/O)
    │   ├── fetch.md                  # Fetch MCP (URL → markdown)
    │   ├── knowledge.md              # internal Knowledge Retrieval MCP (web/Confluence/SharePoint)
    │   ├── claude-code-worker.md     # internal ClaudeCode Worker MCP (in-process + sandboxed)
    │   └── code-review-graph.md      # external code-review-graph MCP (blast-radius, wiki, delivery bundle)
    ├── 03-data-model.md              # task/run/event schemas (orchestrator DB only)
    ├── 04-api-contracts.md           # REST + WebSocket surface
    ├── 05-sequence-flows.md          # end-to-end task execution diagrams (with MCP calls)
    ├── 06-security.md                # authn/z, tenancy, secrets, sandboxing
    ├── 07-roadmap.md                 # phased implementation plan
    └── adr/
        ├── 0001-typescript-monorepo.md
        ├── 0002-provider-agnostic-llm.md
        ├── 0003-claude-agent-sdk-default.md
        ├── 0004-mcp-client-transport.md
        ├── 0005-delegate-memory-to-ruflo.md
        ├── 0006-consume-code-review-graph-mcp.md
        ├── 0007-playwright-test-loop.md
        ├── 0008-knowledge-retrieval-federation.md
        ├── 0009-consume-ruflo-via-mcp-not-fork.md
        ├── 0010-mcp-server-registry-and-allowlists.md
        ├── 0011-dynamic-mcp-manager-and-catalog.md
        ├── 0012-embed-claude-code-as-deep-worker.md
        └── 0013-cloud-hosted-no-local-agents.md
```

## Key architectural decisions the docs will codify

1. **Monorepo (pnpm + Turborepo)** with packages: `orchestrator`, `agent-runtime`, `deep-coding`, `llm`, `mcp-client`, `knowledge`, `testing`, `web`, `vscode-extension`, `shared-types`. (No standalone `memory` or `code-graph` package — memory is consumed from Ruflo via MCP, and structural code analysis is consumed from `code-review-graph` via MCP. The `deep-coding` package wraps the Claude Agent SDK `query()` primitive and the sandboxed Claude Code worker MCP — see §17.)

2. **Orchestrator service** (Fastify + WebSocket) owns the task graph, dispatches agent runs, streams events to UI/IDE. Task queue via BullMQ on Redis. **This is the sole orchestration layer** — Ruflo's own swarm/queen/router/consensus features are deliberately **not** used; Ruflo is consumed as a memory-and-patterns utility only (see §7 and ADR-0009). The orchestrator owns: task state machine, routing between the 4 roles, HITL flows, approvals, retries, cost ceilings, audit, and delivery-bundle assembly.

3. **Agent runtime — outer orchestration layer** built on the **Claude Agent SDK** (`@anthropic-ai/claude-agent-sdk`) behind a thin `LLMProvider` interface so OpenAI/Gemini/Ollama can be swapped in. Planner/Coder/Tester/Reviewer are implemented as SDK subagents with per-role system prompts, allowed tools, and permission modes. These 4 roles are deliberately **short-running coordinators**, not deep-work loops — they own routing, HITL, approvals, and delivery, but dispatch all heavy task-breakdown / iterative coding work to the **Deep Coding Worker** (see §17), which runs Claude Code as the inner loop. This prevents nested re-planning and keeps the outer loop cheap.

4. **SKILLs repo loader** – at session start the runtime scans the user-configured SKILLs directory (mounted or git-cloned) and registers each skill with the agent via the SDK's skill-loading hook. Doc explains directory layout contract (`SKILL.md` + optional scripts) and precedence rules.

5. **MCP client — central nervous system** – a single `mcp-client` package (built on `@modelcontextprotocol/sdk`) owns connection lifecycles to **every** external capability. Every tool an agent can call — memory, repo ops, browser automation, enterprise app, knowledge lookup — is a tool on some MCP server, registered here. No bespoke tool code leaks into `agent-runtime`. Key properties:
   - **Pluggable transports:** `stdio` (spawn a local binary), `streamable-http`, and `sse`. Chosen per server in config.
   - **Server registry:** declared in `agent-studio.config.ts` with a typed `McpServerSpec` per entry (name, transport, command/url, env, auth, healthcheck, retries, allowlist).
   - **Per-role tool allowlists:** planner / coder / tester / reviewer each get a glob-filtered view. Example: the planner cannot call `git.push`; only the coder can. The tester is the only role allowed to call `playwright.*`.
   - **Per-task tool overrides:** a task definition can further tighten (never widen) the role allowlists — e.g. a read-only audit task disables all write tools across every server.
   - **Approval hooks:** any tool flagged `requiresApproval` triggers the HITL primitive before execution (e.g. `git.push`, `github.merge_pull_request`, `wms.update_config`). Approvals are recorded to the task's audit trail.
   - **Health + failover:** each server has a heartbeat; on failure the client emits a `tool_unavailable` event, masks the tools, and the orchestrator decides whether to block the task or proceed degraded. A secondary instance can be declared per server for failover.
   - **Observability:** every MCP call is logged with `{task, role, server, tool, latency, tokens, result_status}` for cost + audit dashboards.

6. **MCP server integrations — how the pieces fit**

   Agent Studio is itself an **MCP client only**. Every external capability is an MCP server, run either as a spawned child process, a sidecar container, or a remote HTTP endpoint. Nothing except the orchestrator and agent runtime is built in-house. The table below is the integration matrix the `02-integrations/` docs will expand on in full detail; each integration gets its own file with config snippet, tool allowlist per role, failure mode, and sequence diagram.

   | MCP Server | Purpose | Transport | Who runs it | Primary tools consumed | Roles allowed | Approval-gated? |
   |---|---|---|---|---|---|---|
   | **Ruflo** | Persistent memory + learned patterns across sessions | stdio (local) or HTTP (central) | External — Ruflo's own distribution, pinned version | `memory.store`, `memory.search`, `pattern.lookup`, `pattern.store` | all roles (read); planner/coder/tester/reviewer (write at defined checkpoints) | no |
   | **WMS** (user-provided) | Read/update enterprise WMS configs + source | As configured by the user's existing server | External — already built | `wms.read_config`, `wms.update_config`, `wms.read_source`, `wms.apply_patch` (names illustrative — finalized against the real manifest) | coder (read+write), planner/reviewer (read) | yes, on writes |
   | **Git MCP** | Local repo operations: clone, branch, stage, commit, diff, log, status | stdio | Sidecar (`npx @modelcontextprotocol/server-git` or equivalent) | `git.clone`, `git.status`, `git.diff`, `git.stage`, `git.commit`, `git.branch`, `git.checkout`, `git.log` | coder (all), planner/tester/reviewer (read-only) | no (writes are local only) |
   | **GitHub MCP** | Remote forge ops: PRs, issues, code search, reviews | HTTP | Sidecar (GitHub-maintained MCP server) or equivalent for GitLab/Bitbucket | `github.create_pr`, `github.list_prs`, `github.get_pr`, `github.add_comment`, `github.search_code`, `github.search_issues`, `github.merge_pr` | coder (create PR, comment), reviewer (review, merge), planner/tester (read) | **yes** for `create_pr`, `merge_pr`, `push` |
   | **Playwright MCP** | Browser automation for E2E test generation, execution, and visual verification | stdio, inside a Docker sandbox | Sidecar (`@playwright/mcp` or equivalent) | `playwright.launch`, `playwright.navigate`, `playwright.click`, `playwright.fill`, `playwright.snapshot`, `playwright.run_test`, `playwright.get_report` | tester only | no (sandboxed) |
   | **Filesystem MCP** | Scoped read/write inside the task's working directory | stdio | Sidecar (`@modelcontextprotocol/server-filesystem`) | `fs.read`, `fs.write`, `fs.list`, `fs.search` | coder (rw), planner/tester/reviewer (read) | no (path-jailed) |
   | **Fetch MCP** | Fetch a URL and return markdown (used by knowledge + ad-hoc lookups) | stdio | Sidecar (`@modelcontextprotocol/server-fetch`) | `fetch.url` | all roles | no (read-only, domain allowlist) |
   | **code-review-graph** (`tirth8205/code-review-graph`) | Structural knowledge graph of existing code **and** of the artifacts the agents produce during the task. Blast-radius, impact, callers/callees, test coverage, architecture overview, risk-scored change summaries, community-detected wiki. | stdio (spawn its Python MCP server) or sidecar container | External — upstream Python distribution, pinned version | `graph.build`, `graph.update`, `graph.detect_changes`, `graph.impact_radius`, `graph.callers_of`, `graph.callees_of`, `graph.tests_for`, `graph.semantic_search`, `graph.architecture_overview`, `graph.wiki_generate`, `graph.visualize` (names per its published 22-tool manifest) | planner (overview, semantic search), coder (impact, callers/callees, update), tester (tests_for, impact), reviewer (all — drives the delivery bundle) | no |
   | **ClaudeCode Worker MCP** *(internal, built by us)* | Spawn a nested/sandboxed Claude Code session as the **deep-work inner loop** — plan mode, todos, SKILLs, iterative edit-run-fix — for heavy task breakdown and coding | stdio (in-process `query()`) **or** docker-sandboxed subprocess | Shipped in-tree as `deep-coding` package + MCP server | `claude_code.run` (in-process nested session), `claude_code.spawn_worker` (sandboxed subprocess), `claude_code.status`, `claude_code.cancel`, `claude_code.stream_events` | coder (both), tester (spec generation), reviewer (structural walks); planner **not allowed** (prevents nested re-planning) | **yes** for `spawn_worker` with `permissionMode=bypassPermissions` |
   | **Knowledge Retrieval MCP** *(internal, built by us)* | Federated "have we seen this before?" over web / Confluence / SharePoint / GitHub search | stdio | Shipped in-tree as an MCP server package | `knowledge.search`, `knowledge.fetch` | all roles | no |

   **Key interaction principles:**
   - **Single tool-use loop, many servers.** Agents do not know whether a tool call goes to Ruflo, Git, WMS, or an internal server — they just call `memory.search` or `git.diff`. The MCP client routes by tool name prefix.
   - **No forking.** Ruflo, WMS MCP, Git MCP, GitHub MCP, Playwright MCP, Filesystem MCP, and Fetch MCP are all consumed as upstream distributions. We pin versions in config and upgrade on our schedule. Ruflo specifically is **not** forked — ADR-0009 records that decision.
   - **Internal-only servers for Agent-Studio-specific capabilities.** The Knowledge Retrieval and Code Graph layers are exposed as MCP servers too, so they share the same allowlist/observability/approval infrastructure as everything else. No special-case pathways.
   - **Transport choice drives deployment.** stdio servers are spawned per orchestrator process (cheap, simple); HTTP/SSE servers run as sidecars or centrally (Ruflo typically central so memory is shared across orchestrator replicas).
   - **Failure isolation.** Losing any one server degrades — not breaks — the task. E.g., Ruflo down → runs proceed without memory with a warning; Playwright down → tester blocks for HITL.
   - **Secrets never in config files.** All credentials (GitHub PAT, WMS auth token, Ruflo endpoint secret, Confluence API token, SharePoint client secret) are referenced by name and resolved at server-spawn time from the secrets backend.

7. **Persistent memory via Ruflo** – Agent Studio does **not** run its own vector DB. Ruflo runs as a separate process (stdio child or central HTTP service) and is registered in the MCP server registry. Agents call its memory tools through the normal tool-use loop. The `02-integrations/ruflo.md` doc specifies:
   - Exact Ruflo tool names invoked (`memory.store`, `memory.search`, `pattern.lookup`, etc. — finalized against Ruflo's published manifest at integration time).
   - A thin `MemoryClient` wrapper in `agent-runtime` that standardizes `remember(scope, kind, payload)` and `recall(query, topK)`, so a future memory backend swap is localized to one file.
   - Scope mapping: Agent Studio `(tenant, project, task)` → Ruflo `user/project/local` scopes.
   - Write points: after planning, after each successful fix, after test pass, on human clarification, on task completion.
   - Read points: before planning, before each retry, before review, on any test failure (before invoking knowledge retrieval).
   - Fallback: if Ruflo is unreachable, runs continue stateless with a warning event — no silent data loss, no hard dependency.
   - **Not forked.** Ruflo is consumed as-is from its upstream distribution (see ADR-0009). Only its memory + pattern tools are enabled by default; its swarm/consensus/routing features are deliberately out of scope.

8. **Knowledge Retrieval Layer** – a federated "have we seen this before?" tool that agents call proactively before attempting a non-trivial fix, and reactively after a test failure. Exposed as its own internal MCP server so it slots into the same tool-use pipeline as every other capability — **one unified tool** (`knowledge.search(query, sources?, topK)`) backed by adapters:
   - **Web search** — pluggable provider (Tavily / Brave / SerpAPI); returns titles, snippets, URLs; full content fetched via the Fetch MCP server when needed.
   - **Confluence** — Atlassian REST API adapter (CQL search + page fetch); auth via API token per tenant.
   - **SharePoint** — Microsoft Graph API adapter (`/search/query`); auth via Azure AD app registration.
   - **GitHub** — delegates to the **GitHub MCP server** (`github.search_code`, `github.search_issues`) rather than re-implementing; crucial for "has this issue already been filed/fixed?".
   - **Internal docs (optional phase)** — lightweight local RAG over a mounted docs folder if the tenant has no Confluence/SharePoint.
   Each adapter returns a normalized `KnowledgeHit { source, title, url, snippet, score, retrievedAt }`. Results are re-ranked (reciprocal rank fusion) and cached per query hash for the task's lifetime to avoid duplicate calls. Per-tenant config declares which sources are enabled and holds their credentials (via secrets backend, never in memory).

9. **Structural code understanding via `code-review-graph`** – Agent Studio does **not** build its own tree-sitter indexer. It consumes `tirth8205/code-review-graph` as an external MCP server (the upstream project ships a 22-tool MCP interface and a Python CLI; we spawn it via stdio or run it as a sidecar container and pin the version in the MCP Registry). This tool does three jobs for us that a naive graph couldn't:

   **a. Token-efficient *existing* code understanding.** Before planning, the planner calls `graph.architecture_overview` and `graph.semantic_search` to locate the relevant slice of the repo instead of ingesting it whole. Its authors report 6.8×–49× token reductions on review tasks, which directly serves the "avoid full codebase ingestion" requirement (spec §3).

   **b. Incremental tracking of what agents *produce* during the task.** This is the capability that actually makes the delivery loop work. After every coder commit (via Git MCP), the orchestrator calls `graph.update` + `graph.detect_changes`. Because `code-review-graph`'s update completes in under ~2s on multi-thousand-file repos, the graph is continuously in sync with agent output. The result is a **live structural map of everything the planner, coder, tester, and reviewer subagents have touched** — nodes (new/changed functions, classes, configs), edges (new calls, new imports, new test coverage), and metadata (risk scores, criticality).

   **c. Delivery bundle generation for the reviewer role.** At task completion the reviewer subagent assembles a **Delivery Bundle** by calling:
   - `graph.impact_radius` over the set of agent-changed nodes → "what else could this have affected?"
   - `graph.tests_for` over the same set → confirm every impacted node has test coverage (and feeds the Playwright loop in §11 with the exact test surface to re-run).
   - `graph.detect_changes` → risk-scored change summary for the human reviewer.
   - `graph.wiki_generate` over the task's community subgraph → auto-generated markdown docs of the new/changed feature.
   - `graph.visualize` → interactive HTML graph embedded in the Web UI's "Delivery" tab.
   The bundle is persisted against the task record, surfaced in Web UI + VS Code, and is the artifact a human signs off before merge.

   **Failure mode:** if `code-review-graph` is unreachable, the reviewer falls back to a diff-based summary and flags the task "partial delivery — graph unavailable." No hard dependency.

   **Not forked.** Upgrades are managed through the MCP Registry like every other external server. Its Python runtime is invisible to the rest of Agent Studio — the MCP boundary is the contract.

10. **Task state machine** – `not_started → planning → in_progress → blocked → partially_complete → completed` (plus `failed`, `cancelled`). Blocked tasks emit a `clarification_needed` event with a typed question schema; resume is automatic once a user answer is posted. All transitions persisted for audit.

11. **Playwright test loop** – Tester agent dispatches to a **Claude Code worker** (§17) to generate spec files, then drives the **Playwright MCP** server (running inside a Docker sandbox) to execute them, capturing HTML/JSON reports and screenshots. The test surface isn't guessed — the tester first calls `graph.tests_for` + `graph.impact_radius` on the coder's latest changes (via `code-review-graph`) to get the exact set of tests to run. On failure the loop calls `memory.search` (Ruflo) and `knowledge.search` (internal) before dispatching a fix to the coder's Claude Code worker, so known solutions surface cheaply. The worker uses **Git MCP** to stage and commit fixes; after each commit the orchestrator re-runs `graph.update` so the next iteration sees a fresh graph. Loop exits when pass-rate/coverage thresholds are met or max-iterations hit (then blocks for human review). Final review by the reviewer role builds the **Delivery Bundle** (see §9c) and opens a PR through **GitHub MCP** (HITL-gated) with the bundle attached.

12. **VS Code extension** – thin client that opens a WebSocket to the orchestrator, mirrors the web UI's task list, surfaces diffs/tests inline, and lets the user approve/reject agent actions. Web and IDE share the same session token so switching surfaces is seamless.

13. **Web control panel** – Next.js app: task submission form, live task graph view, agent transcripts, **MCP call log** (every tool call across every server with latency + result), **knowledge-hit inspector**, **memory browser** (reads Ruflo via MCP), **MCP server health dashboard**, HITL approval queue, run history.

14. **Human-in-the-loop** – first-class: any agent can emit `askHuman(question, schema)`; orchestrator pauses the task, notifies both surfaces, resumes on answer. Approval-gated MCP tool calls (e.g. `git.push`, `github.create_pr`, `github.merge_pr`, `wms.update_config`) flow through the same primitive — the MCP client intercepts the call, raises an approval event, and only forwards the invocation after the user approves.

15. **Security** – JWT auth, per-tenant DB row isolation, per-role MCP tool allowlists, Docker sandbox for Playwright and any code execution, secrets (GitHub PAT, WMS auth, Confluence token, SharePoint client secret, Ruflo endpoint creds, web-search API keys, Anthropic API key for Claude Code workers) held in a secrets backend (env / Vault) and injected into MCP server spawn env at runtime — never persisted in any DB, never logged. Domain allowlists on the Fetch MCP server to prevent exfiltration via URL fetches. **Claude Code worker sandboxing (see §17):** sandboxed workers run in per-task Docker containers with CPU/memory/time limits, read-only mounts for the repo snapshot, an explicit scoped MCP subset, and `permissionMode=bypassPermissions` is **never** allowed without operator approval (routed through HITL).

16. **MCP Registry & Manager** – a first-class subsystem that lets operators add, remove, upgrade, enable, and disable MCP servers **without redeploying Agent Studio**, mirroring the way SKILLs can be dropped in dynamically. New capabilities (a new enterprise system, a new browser automation server, a new knowledge source) become available as soon as their MCP server entry is registered. The manager sits between the raw `mcp-client` transport layer and the agent runtime.

   Its responsibilities, documented in `02-components/mcp-client.md` and a new `02-components/mcp-registry.md`:

   **A. Declarative registry.** Servers are declared in one of three layered sources, highest precedence first:
   1. **Tenant overrides** in the orchestrator DB (`mcp_server_registrations` table) — hot-editable via the web UI.
   2. **Per-project `agent-studio.mcp.yaml`** checked into the target project's repo — travels with the code.
   3. **Platform defaults** in `config/mcp-servers.d/*.yaml` shipped with Agent Studio (e.g. Git, Filesystem, Fetch, Playwright pinned versions).

   Every entry is a typed `McpServerSpec`:
   ```yaml
   name: playwright
   version: "^1.46.0"
   source:
     kind: npx            # npx | docker | http | binary | git
     package: "@playwright/mcp"
   transport: stdio       # stdio | streamable-http | sse
   env:
     - name: PLAYWRIGHT_BROWSERS_PATH
       valueFrom: { secret: playwright-browsers-cache }
   healthcheck:
     tool: playwright.ping
     intervalMs: 30000
   allowlist:
     tester:   ["playwright.*"]
     coder:    []
     planner:  []
     reviewer: []
   approvalRequired: []
   sandbox: docker-playwright
   enabled: true
   ```

   **B. Source kinds the manager can install from:**
   - `npx` — auto-download and spawn (e.g. `npx -y @modelcontextprotocol/server-git`)
   - `docker` — pull an image and run as a sidecar with resource limits
   - `http` / `sse` — connect to an existing remote endpoint (Ruflo central, user's WMS server)
   - `binary` — path to a pre-installed executable
   - `git` — clone a repo, build, and run (for in-development community servers)

   **C. Catalog of known-good servers** — ships with the platform as a curated list (Ruflo, Git, GitHub, Playwright, Filesystem, Fetch, Slack, Confluence, Jira, Notion, …). The web UI presents this as an "MCP Marketplace" view where an operator clicks **Install** and fills in required secrets/config; the manager writes the registration to the DB, probes health, and makes the tools available immediately. Unlisted servers can be added by pasting a raw `McpServerSpec`.

   **D. Lifecycle operations** (CLI + REST + Web UI parity):
   - `mcp list` — show registered servers, versions, health, which roles can use which tools
   - `mcp install <name>` / `mcp add --spec file.yaml`
   - `mcp upgrade <name> [--to <version>]`
   - `mcp disable <name>` / `mcp enable <name>`
   - `mcp remove <name>`
   - `mcp test <name>` — probe the server, list its advertised tools, show allowlist diff
   - `mcp describe <name>` — dump normalized spec with secrets redacted

   **E. Version pinning & upgrade safety.** Every registration pins a version (or version range). Upgrades are opt-in: the manager can check upstream for newer versions and surface them in the UI, but never auto-upgrade. After upgrade it re-runs the healthcheck and the allowlist diff; if new tools appeared that aren't in the allowlist, they default to **denied** until an operator explicitly grants them — so a supply-chain surprise can't silently widen the attack surface.

   **F. Runtime hot-reload.** Adding/removing/enabling/disabling a server is picked up by the running orchestrator through a registry watcher (DB LISTEN/NOTIFY for tenant overrides, file watcher for project YAML). No restart. In-flight tasks keep using the snapshot of servers they started with; new tasks see the updated set.

   **G. Parity with the SKILLs loader.** Exactly the same mental model: SKILLs are dropped into a directory, MCP servers are dropped into the registry. The SKILLs loader and the MCP Registry both expose a `list`, `install`, `enable`, `disable`, `remove`, and `describe` surface — operators learn one pattern, apply it to both.

   **H. Audit + observability.** Every registry mutation (add/remove/upgrade/enable/disable) is written to an append-only audit log with actor, diff, and reason. Every tool call (already covered in §5) is tagged with the registry version that served it, so a post-hoc question like "which Playwright version produced this failing run?" is answerable.

   **I. Security posture of the manager itself.** The registry is a high-value target — it can introduce new code execution paths. Mitigations: tenant-admin-only mutation RBAC; mandatory human approval for any new `source.kind=git` or `source.kind=binary` registration; container sandbox defaults for every new server unless explicitly waived; secrets resolved at spawn time only, never stored in the registry row.

17. **Deep Coding Workers — Claude Code as the inner loop** – The outer 4-role orchestration layer (§3) does not re-implement plan-mode, todo tracking, or iterative edit-run-fix loops. Instead, whenever real task breakdown and deep coding are required, the Coder / Tester / Reviewer roles **dispatch to a Claude Code session** that owns that inner loop. Claude Code is hosted *with* Agent Studio, not beside it: it ships as part of the deployment, runs under the same tenancy, and is invoked only through Agent Studio's MCP client.

   The `deep-coding` package provides two dispatch modes, both surfaced as tools on the internal `ClaudeCode Worker MCP` server (§6):

   **A. In-process nested session — `claude_code.run`**
   - Implemented directly on top of `query()` from `@anthropic-ai/claude-agent-sdk` (the same engine Claude Code itself runs on).
   - Same Node process as the orchestrator — cheap, low-latency, no container overhead.
   - Inherits tenant, workspace, SKILLs directory, and the scoped MCP server subset from the dispatching role.
   - Used by default for most coder/tester/reviewer work.
   - Emits streaming progress events (tool calls, todos, plan changes, intermediate messages) back to the orchestrator, which forwards them to the Web UI and VS Code extension in real time.

   **B. Sandboxed worker — `claude_code.spawn_worker`**
   - Spawns a full Claude Code process (headless `claude -p` or equivalent SDK entry point) inside a **per-task Docker container**.
   - Used for: long-running refactors, untrusted tasks, parallel exploration ("try three approaches, pick the winner"), or anything the operator wants isolated from the main process.
   - Container config:
     - Read-only mount of the repo snapshot (produced by Git MCP); writes go to an overlay filesystem that's diffed back at the end.
     - Scoped MCP client config file written into the container — narrowest subset the task needs (e.g. just Filesystem + Git + code-review-graph; never the full registry).
     - Environment-injected secrets (Anthropic API key resolved from the secrets backend at spawn).
     - CPU/memory/time budgets, killed on overrun.
     - Network egress allowlist (Anthropic API + configured MCP endpoints only).
   - Returns a structured result: final diff, final todo list, per-iteration telemetry, exit reason, cost, tool-call log.

   **Dispatch envelope (what the outer role sends in).** Every `claude_code.run` / `spawn_worker` call takes a typed `DispatchEnvelope`:
   ```ts
   {
     goal: string,              // natural language objective
     workspace: { path, baseRef, writableGlobs },
     successCriteria: {         // machine-checkable
       tests?: string[],        // e.g. "pnpm test -- src/wms/**"
       graphChecks?: string[],  // e.g. "graph.impact_radius(<=3) within allowed modules"
       customScript?: string
     },
     toolBudget: { maxToolCalls, maxTokens, maxWallSeconds },
     mcpServers: McpServerSpec[],      // narrowest subset
     skillsDir?: string,               // tenant SKILLs or a subset
     permissionMode: 'default' | 'acceptEdits' | 'plan' | 'bypassPermissions',
     memoryContext: MemoryHit[],       // pre-fetched Ruflo recall
     knowledgeContext: KnowledgeHit[], // pre-fetched knowledge.search results
     returnShape: 'diff' | 'diff+summary+telemetry'
   }
   ```
   The outer role assembles this envelope (including pre-fetching memory and knowledge hits so the inner loop starts hot) and then hands off. The inner loop does not call `memory.*` or `knowledge.*` itself on cold-start — that keeps its tool budget focused on code work, and keeps the expensive retrieval decisions in the outer loop where they can be reasoned about.

   **C. Anti-nested-planning rule.** If an outer role itself runs in plan mode, it **must not** re-plan work it is about to dispatch — the outer role builds a dispatch envelope and delegates; planning happens exactly once, inside the inner Claude Code session. The Planner role is explicitly **denied** access to `claude_code.*` tools to enforce this; only Coder/Tester/Reviewer can dispatch. The `02-components/agent-runtime.md` doc will call this out in a dedicated "Anti-nesting invariants" subsection.

   **D. Parallel dispatch.** The reviewer role can fan out multiple `spawn_worker` calls in parallel for A/B exploration (e.g. three candidate refactors), wait on all results, and pick the best by success-criteria score. Each worker is fully isolated.

   **E. Cost + observability.** Every dispatch is tagged with `{task, role, mode, envelope.hash, finalCostTokens, wallMs, exitReason}` so the Web UI "MCP call log" tab can show a flattened view across outer + inner loops. Cost ceilings per tenant are enforced by the orchestrator before dispatch.

   **F. Failure isolation.** A crashing sandboxed worker kills only its own container. The outer role sees `{exitReason: 'crashed' | 'timeout' | 'over_budget' | 'success' | 'blocked_hitl'}` and decides the next action (retry with larger budget, escalate to HITL, swap approach).

   **G. Why this layering and not "just use Claude Code":** Agent Studio still owns the platform concerns Claude Code by itself does not — multi-tenancy, web UI, VS Code extension synced with web, persistent cross-session memory (Ruflo), delivery bundle (code-review-graph), HITL approval flows, MCP registry, task state, audit. Claude Code owns the deep-work loop concerns we'd otherwise reinvent — plan mode, todo tracking, iterative edit-run-fix, SKILLs loading, nested subagents, permission modes. Embedding Claude Code as the inner loop gives both layers what they do best with a clean boundary at the `DispatchEnvelope`.

18. **Cloud hosting topology — centrally hosted, multi-client** – Agent Studio is designed to be deployed as a hosted service in the customer's cloud (AWS / GCP / Azure / on-prem Kubernetes) from day one. Users never run agents locally; they connect to the hosted orchestrator from VS Code or a browser. The `02-components/hosting-and-deployment.md` doc specifies:

   | Layer | Deployment | Notes |
   |---|---|---|
   | **Orchestrator service** | Stateless Fastify pods behind an LB, horizontally scalable | Reads/writes state in Postgres; subscribes to Redis pub/sub for live events |
   | **Postgres** | Managed (RDS / Cloud SQL / Azure DB) | Holds tasks, runs, events, MCP registry, audit log, tenant/project rows |
   | **Redis** | Managed (ElastiCache / Memorystore) | BullMQ task queue + pub/sub for WebSocket fan-out |
   | **Ruflo** | Central sidecar service with a persistent volume | One instance per deployment, shared across orchestrator replicas so memory is tenant-global |
   | **`code-review-graph`** | Sidecar container per tenant-project | Pinned version; SQLite graph on a persistent volume |
   | **Claude Code sandboxed workers** | Ephemeral k8s Jobs on a dedicated worker-node pool | Per-task containers; FS overlays; scoped MCP config; CPU/mem/time limits; killed at TTL |
   | **Stdio MCP servers** (Git, Filesystem, Fetch, …) | Spawned per orchestrator pod | Short-lived child processes managed by the MCP client |
   | **HTTP/SSE MCP servers** (GitHub, Playwright, central Ruflo, central code-review-graph) | Central sidecars / own services | Referenced by URL from the MCP registry |
   | **Secrets** | HashiCorp Vault or cloud KMS | Never in DB, never in config, never in logs; resolved at spawn time |
   | **Web UI (Next.js)** | Separate deployment behind the same LB / CDN | Talks to orchestrator over HTTPS + WebSocket; same tenant/session model as the extension |

   **Multi-tenancy model.** Every request carries a tenant/project/user triple on the JWT. DB rows are tenant-scoped; MCP tool calls inherit the tenant; secret lookups are tenant-keyed; Ruflo scopes and code-review-graph workspaces are per-tenant-per-project. Cost ceilings and quotas are enforced per tenant before any Claude Code dispatch.

   **Deployment footprints.** The docs describe three target profiles: (a) single-node **dev** (docker-compose, SQLite where possible), (b) **staging** (single k8s namespace, small worker pool), (c) **production** (HA orchestrator, managed Postgres/Redis, dedicated worker node pool, Vault). ADR-0013 records the cloud-first / no-local-agents decision.

19. **Client surfaces — VS Code extension and browser are peers** – The VS Code extension and the Web UI are both **thin control surfaces** over the hosted orchestrator. Neither runs agents. Both use the same REST + WebSocket API, the same session token, and the same event stream, so a user can start a task in the browser, steer it from VS Code, and finish the approval on their phone. Two-way sync is the default, not a bolt-on. The `02-components/vscode-extension.md` and `02-components/web-ui.md` docs will specify:

   - **Auth:** OAuth PKCE → short-lived JWT scoped to tenant/project/user. Tokens stored in the VS Code secret storage / browser secure cookie; refreshed via a silent refresh endpoint.
   - **Transport:** WebSocket for live task/agent/MCP events; REST for imperative commands. Both gated by the same JWT.
   - **Parity guarantee:** every feature is available from both surfaces. Docs include a parity matrix to prevent drift.
   - **Session bridging:** if a user opens the same task in both surfaces, they see a single conversation and a single todo list — there is only one authoritative state on the server.

20. **Execution control & steering — first-class verbs, either surface** – Users can steer a running task from either surface via a small, typed verb set. Every verb is both a REST endpoint and a WebSocket message and is captured in `04-api-contracts.md` and `02-components/execution-control.md`:

   | Verb | Effect | Allowed states |
   |---|---|---|
   | `task.submit` | Create a new task with business requirement, workspace, budget, tenant | — |
   | `task.pause` | Snapshot agent state, stop consuming budget, transition to `blocked` | `in_progress` |
   | `task.resume` | Unblock and continue from the snapshot | `blocked`, `partially_complete` |
   | `task.inject_context` | Inject text / file / URL / chat message as new context mid-run | any live state |
   | `task.override_plan` | Edit the latest plan or todo list before the agent continues | `planning`, `blocked` |
   | `task.approve` / `task.reject` | Respond to an `askHuman` or an approval-gated MCP tool call | `blocked` |
   | `task.cancel` | Hard-stop the task; kill any sandboxed workers; stop at current state | any live state |
   | `task.branch` | Fork the task at the current checkpoint to explore an alternative approach | any state with a checkpoint |
   | `task.rollback` | Revert to a prior checkpoint in the state machine | any state with a prior checkpoint |
   | `task.set_budget` | Raise or lower the cost / wall-time ceiling mid-run | any live state |
   | `task.retarget_reviewer` | Change who the HITL questions route to | any state |

   **Semantics worth locking down in docs:**
   - **Checkpoints** are written at every state transition and after each Claude Code worker run, so `rollback` and `branch` have well-defined targets.
   - **Injection** is accepted by the outer role and surfaced to the next Claude Code dispatch via `DispatchEnvelope.memoryContext` / `.goal` — the inner loop never sees the steering API directly, preserving the `DispatchEnvelope` as the single boundary.
   - **Pause** is honored at the next tool-call boundary, so an in-flight MCP call is allowed to complete before the snapshot — avoids partial external-system writes.
   - **Cancel** kills sandboxed workers immediately via the k8s Job lifecycle; in-process `query()` sessions are cancelled through the SDK's AbortSignal; any in-flight approval-gated tool call is not executed.
   - **Auditability:** every steering verb is recorded in the append-only audit log with actor, task, state, and reason.

## Phased roadmap (captured in `07-roadmap.md`)

- **Phase 0:** Monorepo scaffolding, CI, shared types, config loader, secrets backend.
- **Phase 1:** Orchestrator + LLM abstraction + Claude provider + single planner agent running a trivial task.
- **Phase 1.5:** **Deep Coding Worker** — `deep-coding` package with `claude_code.run` (in-process `query()` on Claude Agent SDK) first, `claude_code.spawn_worker` (Docker-sandboxed CLI) second. DispatchEnvelope contract finalized. Anti-nesting invariants enforced in the Coder role.
- **Phase 2:** **MCP client + MCP Registry/Manager** (see §16). Wire first three external servers: Filesystem MCP, Git MCP, Fetch MCP. Register `ClaudeCode Worker MCP` as an internal server.
- **Phase 3:** SKILLs loader + Ruflo MCP integration for persistent memory.
- **Phase 4:** WMS MCP integration (user's existing server) + GitHub MCP integration.
- **Phase 5:** Knowledge Retrieval MCP (internal) — GitHub + web search adapters first, Confluence and SharePoint next.
- **Phase 6:** **`code-review-graph` MCP integration** — pin upstream version, add to registry, wire planner/coder/tester/reviewer calls (`architecture_overview`, `impact_radius`, `tests_for`, `detect_changes`, `update`), stand up the Delivery Bundle assembler in the reviewer role.
- **Phase 7:** Playwright MCP integration inside Docker sandbox; tester agent drives test surface off `graph.tests_for`; retrieval-first failure handling.
- **Phase 8:** Web UI control panel + HITL workflows + MCP server manager UI + **Delivery Bundle viewer** (embeds `graph.visualize` HTML + risk-scored change summary + auto-wiki).
- **Phase 9:** VS Code extension + IDE/web session sync (both surfaces on the same WebSocket API); execution-control verbs wired end-to-end (pause/resume/inject/override/cancel/branch).
- **Phase 10:** Cloud deployment profiles (dev docker-compose → staging k8s → production HA with managed Postgres/Redis/Vault and dedicated worker node pool).
- **Phase 11:** Observability, cost tracking, multi-provider failover, hardening.

## Critical references the docs will cite

**Runtime & SDKs**
- `@anthropic-ai/claude-agent-sdk` — subagents, hooks, permission modes, skill loading, **`query()` primitive powering in-process Deep Coding Workers (§17)**
- `anthropics/claude-code` — the Claude Code CLI, hosted alongside Agent Studio and invoked as the sandboxed-worker mode of the Deep Coding Worker for heavy/isolated task breakdown and iterative coding
- `@modelcontextprotocol/sdk` — MCP client transports (stdio / streamable-http / sse)
- `BullMQ` + Redis — task queue
- `Fastify`, `Next.js`, `pnpm`, `Turborepo` — baseline infra

**External MCP servers consumed (not forked)**
- **Ruflo** (`ruvnet/ruflo`) — persistent memory + learned patterns, via MCP only. Exact tool names finalized against its published manifest at integration time. ADR-0009 records the no-fork decision.
- **code-review-graph** (`tirth8205/code-review-graph`) — Python-based structural code knowledge graph with a built-in 22-tool MCP server: impact/blast-radius, callers/callees, tests-for, semantic search, architecture overview, detect-changes, wiki generation, interactive visualization. Powers both token-efficient code understanding *and* the Delivery Bundle the reviewer produces at task completion. ADR-0006 records the decision to consume rather than reimplement.
- **WMS MCP server** — user-provided, already built; Agent Studio only connects as a client.
- **Git MCP** — e.g. `@modelcontextprotocol/server-git` or equivalent (stdio); repo ops.
- **GitHub MCP** — upstream GitHub-maintained MCP server; PRs, issues, searches, merges. Equivalents can be swapped in for GitLab / Bitbucket / Azure DevOps via the registry.
- **Playwright MCP** — e.g. `@playwright/mcp`; browser automation, test execution, snapshots. Runs inside the Docker sandbox.
- **Filesystem MCP** — `@modelcontextprotocol/server-filesystem`; path-jailed workspace I/O.
- **Fetch MCP** — `@modelcontextprotocol/server-fetch`; URL → markdown with domain allowlist.

**Internal MCP servers built in this project**
- **ClaudeCode Worker MCP** — exposes `claude_code.run` (in-process nested session via Agent SDK `query()`) and `claude_code.spawn_worker` (Docker-sandboxed Claude Code subprocess) as the deep-work inner loop for Coder / Tester / Reviewer roles. ADR-0012 records the embed-not-reinvent decision and the anti-nested-planning invariant.
- **Knowledge Retrieval MCP** — federated search over web (Tavily/Brave/SerpAPI), Confluence (Atlassian REST v2 + CQL), SharePoint (Microsoft Graph `/search/query`), and GitHub (delegated to the GitHub MCP server above).

**Extensibility**
- The **MCP Registry/Manager** (§16) means all servers above are merely the *default catalog*. New MCP servers — Slack, Jira, Notion, Kubernetes, in-house enterprise systems — can be added at runtime without code changes, in the same way SKILLs can be added.

## Verification

Because this delivery is documentation-only, verification is a doc review:

1. **Completeness check** – every numbered requirement in the user's spec (§1–§8) has a corresponding section in `docs/` (a traceability table will be included in `00-overview.md`).
2. **Diagram rendering** – open each Mermaid diagram on GitHub's preview to confirm it renders.
3. **Link check** – run `lychee` (or manual scan) over the `docs/` tree to confirm no broken internal links.
4. **Reference check** – every external library named in the docs resolves to an existing npm/Cargo package or upstream repo.
5. **ADR sanity** – each ADR has Context / Decision / Consequences sections and a status of `Accepted`.
6. **User walkthrough** – share the doc index with the user and confirm the design matches their intent before any code work begins.

## Files to be created / modified

- `README.md` (modified) — rewritten as a short pitch that links into `docs/`
- `docs/**` (created) — full tree listed above (~34 Markdown files including `02-integrations/`, `mcp-registry.md`, `deep-coding-workers.md`, `claude-code-worker.md`, `hosting-and-deployment.md`, `execution-control.md`, and ADRs 0009–0013)

No source code, build config, or dependency manifests are introduced in this delivery. The docs are structured to be portable — a downstream environment can lift `docs/` into any repository of its choosing.

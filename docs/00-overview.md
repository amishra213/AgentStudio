# Agent Studio — Overview

> **Document status:** Living design document — updated as each phase is implemented.
> **Reading order position:** 1 of 8 — read this before any other doc in this tree.

---

## Table of Contents

1. [Project Purpose](#1-project-purpose)
2. [Goals](#2-goals)
3. [Non-Goals](#3-non-goals)
4. [Success Criteria](#4-success-criteria)
5. [Spec Traceability Table](#5-spec-traceability-table)

---

## 1. Project Purpose

Agent Studio is a **centrally hosted, cloud-native platform** that drives autonomous and
semi-autonomous software delivery by orchestrating a pipeline of four specialised AI agents —
Planner, Coder, Tester, and Reviewer — over an organisation's real codebases, backed by
persistent cross-session memory, structural code understanding, federated knowledge retrieval,
and a unified human-in-the-loop approval surface available from both a browser control panel and
a VS Code extension. Every agent capability — memory operations, repository manipulation, browser
test automation, enterprise system access, and deep iterative coding — is exposed through the
Model Context Protocol (MCP), so new tools and enterprise integrations can be registered at
runtime without redeploying the platform. Agent Studio is the connective tissue between an
organisation's existing tools (WMS, GitHub, Confluence, SharePoint) and the Anthropic Claude
models that reason over them; it deliberately owns the platform concerns (multi-tenancy, state
machine, audit trail, cost ceilings, delivery bundle, HITL) while delegating deep coding loops
to an embedded Claude Code inner loop via a typed `DispatchEnvelope` boundary.

---

## 2. Goals

- **G1 — Autonomous software delivery pipeline.** Run a planner → coder → tester → reviewer
  pipeline that can take a natural-language business requirement from submission through a
  reviewed, tested, delivery-bundled pull request with minimal human interaction on the
  critical path.

- **G2 — Persistent cross-session memory.** Agents remember what worked, what failed, and what
  patterns already exist in the codebase across sessions and across tasks, so repeated mistakes
  are avoided and known solutions are surfaced cheaply before attempting a new fix.

- **G3 — Structural code understanding without full ingestion.** Before planning any change,
  agents locate the relevant slice of the codebase via a structural knowledge graph
  (`code-review-graph`) — avoiding the token cost and hallucination risk of ingesting entire
  repositories.

- **G4 — Federated knowledge retrieval.** Before attempting a non-trivial fix, agents proactively
  search web sources, Confluence, SharePoint, and GitHub (issues, PRs, code) to check whether
  the problem has already been solved or documented.

- **G5 — Enterprise tool integration via MCP.** Any enterprise system (WMS, Jira, Slack,
  Confluence, SharePoint, internal APIs) can be exposed to agents through an MCP server and
  registered in the platform's MCP Registry without code changes.

- **G6 — Dynamic MCP server lifecycle.** Operators can install, upgrade, enable, disable, and
  remove MCP servers at runtime without redeploying Agent Studio. New capabilities are available
  immediately after registration.

- **G7 — Human-in-the-loop as a first-class primitive.** Any agent can pause execution and
  request human input (clarification, approval, decision) at any point. Approval-gated MCP tool
  calls (e.g. `git.push`, `github.merge_pr`, `wms.update_config`) route through the same
  primitive. The human can steer, pause, resume, branch, or cancel from either the browser or
  VS Code.

- **G8 — Provider-agnostic LLM layer.** Although Claude is the default model and the Claude
  Agent SDK is the default runtime, the `LLMProvider` interface allows any supported model
  (OpenAI, Gemini, Ollama) to be substituted without touching agent logic.

- **G9 — SKILLs repo compatibility.** At session start, agents load the user's existing SKILLs
  directory (mounted or git-cloned), so proprietary workflows and domain knowledge travel with
  every task automatically.

- **G10 — Deep coding via embedded Claude Code.** Heavy task breakdown and iterative edit-run-fix
  loops are delegated to a Claude Code inner loop (the `deep-coding` package), rather than
  re-implemented. The outer 4-role pipeline acts as coordinator; Claude Code acts as the engine.

- **G11 — Multi-tenancy and cost control.** Every task, secret lookup, MCP call, and Claude Code
  dispatch is scoped to a tenant/project/user triple. Cost ceilings are enforced per tenant before
  any expensive dispatch. Audit logs are append-only and per-tenant.

- **G12 — Portable documentation.** The `docs/` tree is self-contained and can be dropped into
  any downstream repository without rewrites. All diagrams render natively on GitHub, GitLab, and
  Bitbucket via Mermaid.

---

## 3. Non-Goals

The following are **explicitly out of scope** for Agent Studio. Documenting non-goals prevents
scope creep and clarifies where Agent Studio's boundary ends and other tools begin.

- **Does not run agents on user machines.** Agent Studio is a centrally hosted cloud service.
  The VS Code extension and browser are thin control surfaces over the hosted orchestrator. No
  agent process, no Claude Code session, and no MCP server runs locally on the developer's
  laptop. See [ADR-0013](./adr/0013-cloud-hosted-no-local-agents.md).

- **Does not run its own vector database.** Agent Studio has no pgvector layer, no Chroma
  instance, and no HNSW index. Persistent memory is delegated entirely to Ruflo via MCP.
  See [ADR-0005](./adr/0005-delegate-memory-to-ruflo.md).

- **Does not fork Ruflo.** Agent Studio consumes `ruvnet/ruflo` as an upstream distribution,
  pinned at a tested version and registered in the MCP Registry. Ruflo's swarm, queen, router,
  and consensus features are deliberately not used. See [ADR-0009](./adr/0009-consume-ruflo-via-mcp-not-fork.md).

- **Does not re-implement structural code analysis.** Agent Studio has no tree-sitter indexer,
  no call-graph builder, and no AST walker of its own. Structural code understanding is delegated
  to `tirth8205/code-review-graph` via MCP. See [ADR-0006](./adr/0006-consume-code-review-graph-mcp.md).

- **Does not re-implement Playwright test execution.** Test automation is driven through the
  upstream Playwright MCP server running in a Docker sandbox. Agent Studio does not fork or
  modify the Playwright MCP server. See [ADR-0007](./adr/0007-playwright-test-loop.md).

- **Does not build or host the WMS MCP server.** The user's WMS MCP server is already built and
  deployed. Agent Studio acts as an MCP client only and connects to it via its declared transport
  and credentials.

- **Does not provide its own Git forge.** All repository hosting (GitHub, GitLab, Bitbucket,
  Azure DevOps) is external. Agent Studio connects to them via MCP servers (Git MCP for local ops,
  GitHub MCP for remote forge ops).

- **Does not build a proprietary agent framework.** The outer orchestration layer uses the
  `@anthropic-ai/claude-agent-sdk` for subagent execution and `@modelcontextprotocol/sdk` for
  tool connectivity. No bespoke LLM orchestration library is introduced.

- **Does not run Ruflo's swarm orchestration.** Ruflo is an MCP memory utility from Agent
  Studio's perspective. Its internal consensus, routing, and queen/worker swarm architecture are
  not used and not configured.

- **Does not provide a managed Anthropic API.** Agent Studio assumes the deploying organisation
  has its own Anthropic API key, injected via the secrets backend. Agent Studio does not resell
  or proxy the Anthropic service tier.

- **Does not process documents offline without an LLM.** Agent Studio is designed for interactive
  and semi-autonomous sessions driven by LLM reasoning. Batch ETL, document indexing without
  agent involvement, or offline ML training are out of scope.

---

## 4. Success Criteria

Success criteria are measurable conditions that can be evaluated at the end of each phase and at
GA. They map directly to the goals above.

| ID | Criterion | Measurement method | Target |
|----|-----------|--------------------|--------|
| SC-1 | End-to-end task completion | Run a representative business requirement through the full pipeline (plan → code → test → review → PR) without human intervention on the critical path | Task completes with a passing PR opened ≥ 80% of representative test cases |
| SC-2 | Persistent memory recall | After a completed task, submit an identical or closely related task and measure how many planning steps are skipped due to memory recall | ≥ 60% of previously solved sub-problems retrieved from memory on first `recall()` attempt |
| SC-3 | Token efficiency via code graph | Measure tokens consumed in the planning phase with vs. without `graph.architecture_overview` + `graph.semantic_search` pre-fetch | ≥ 50% token reduction vs. naive full-repo ingestion (baseline: authors report 6.8×–49× on review tasks) |
| SC-4 | Knowledge retrieval hit rate | On test tasks where a known solution exists in Confluence, SharePoint, or GitHub, measure retrieval recall | `knowledge.search` surfaces the relevant artifact in top-5 results ≥ 70% of the time |
| SC-5 | MCP server hot-registration | Time from `mcp install <server>` to tools being callable by a live agent session | ≤ 30 seconds without orchestrator restart |
| SC-6 | HITL round-trip latency | From an agent emitting `askHuman` to resuming after human response | Notification delivered ≤ 5 seconds; task resumes ≤ 2 seconds after approval posted |
| SC-7 | Playwright test pass rate | On tasks where a Playwright spec is generated, measure the test-pass rate on the first submission to CI | ≥ 75% of generated specs pass on first run; remaining pass after ≤ 2 fix iterations |
| SC-8 | Multi-tenant isolation | No cross-tenant data leakage in DB queries, MCP tool calls, memory scopes, or secret lookups | Zero cross-tenant leakage events in automated penetration test suite |
| SC-9 | Cost ceiling enforcement | Submit a task with a low token budget ceiling; verify the orchestrator halts before exceeding it | Task halted within 5% of configured budget ceiling in ≥ 99% of test runs |
| SC-10 | Provider swap | Swap the LLM provider from Claude to a configured alternative (e.g. Gemini) via config change only | No changes to `agent-runtime`, `orchestrator`, or `mcp-client` packages required; all four roles function with the alternative provider |
| SC-11 | Delivery bundle completeness | Every completed task produces a Delivery Bundle with: risk-scored change summary, impact-radius report, test-coverage confirmation, auto-wiki, and interactive graph visualization | 100% of completed tasks include all five bundle components, or explicitly note `graph unavailable` fallback |
| SC-12 | VS Code / Web UI parity | Every feature available in the Web UI is available in the VS Code extension | Parity matrix in `02-components/vscode-extension.md` shows 0 feature gaps; verified by automated E2E suite |

---

## 5. Spec Traceability Table

The following table maps the eight sections of the user specification to the documents in this
tree that address each requirement. Every requirement in the spec has at least one corresponding
document; no requirement is left implicit.

| Spec section | Requirement summary | Primary doc(s) | Supporting doc(s) |
|---|---|---|---|
| **§1 — Multi-interface access** | Users interact via VS Code extension and a browser control panel; both must be peers with identical feature sets and shared session state | [02-components/vscode-extension.md](./02-components/vscode-extension.md), [02-components/web-ui.md](./02-components/web-ui.md) | [04-api-contracts.md](./04-api-contracts.md), [adr/0013-cloud-hosted-no-local-agents.md](./adr/0013-cloud-hosted-no-local-agents.md) |
| **§2 — Core capabilities** | Autonomous planner → coder → tester → reviewer pipeline; persistent memory; structured output; HITL approvals; execution control (pause/resume/inject/cancel/branch) | [01-architecture.md](./01-architecture.md), [02-components/agent-runtime.md](./02-components/agent-runtime.md), [02-components/orchestrator.md](./02-components/orchestrator.md), [02-components/task-state.md](./02-components/task-state.md), [02-components/execution-control.md](./02-components/execution-control.md) | [05-sequence-flows.md](./05-sequence-flows.md), [03-data-model.md](./03-data-model.md) |
| **§3 — Code understanding** | Agents must understand existing codebases without full ingestion; structural call-graph awareness; blast-radius / impact analysis before any change | [02-integrations/code-review-graph.md](./02-integrations/code-review-graph.md), [02-components/delivery-bundle.md](./02-components/delivery-bundle.md) | [adr/0006-consume-code-review-graph-mcp.md](./adr/0006-consume-code-review-graph-mcp.md), [02-components/testing-pipeline.md](./02-components/testing-pipeline.md) |
| **§4 — MCP tooling** | All agent capabilities (memory, repo ops, browser, enterprise systems, knowledge) must be exposed via MCP; support dynamic registration of new MCP servers at runtime | [02-components/mcp-client.md](./02-components/mcp-client.md), [02-components/mcp-registry.md](./02-components/mcp-registry.md), [02-integrations/README.md](./02-integrations/README.md) | [adr/0004-mcp-client-transport.md](./adr/0004-mcp-client-transport.md), [adr/0010-mcp-server-registry-and-allowlists.md](./adr/0010-mcp-server-registry-and-allowlists.md), [adr/0011-dynamic-mcp-manager-and-catalog.md](./adr/0011-dynamic-mcp-manager-and-catalog.md) |
| **§5 — Iterative problem solving** | Agents must iterate on failures using memory recall and knowledge retrieval before escalating; deep coding loops with plan-mode, todos, and edit-run-fix must be available | [02-components/deep-coding-workers.md](./02-components/deep-coding-workers.md), [02-components/testing-pipeline.md](./02-components/testing-pipeline.md) | [adr/0012-embed-claude-code-as-deep-worker.md](./adr/0012-embed-claude-code-as-deep-worker.md), [02-integrations/claude-code-worker.md](./02-integrations/claude-code-worker.md) |
| **§6 — Reuse and extensibility** | SKILLs repo loading; new MCP servers added without redeploy; provider-agnostic LLM; no vendor lock-in on memory or code analysis | [02-components/skills-loader.md](./02-components/skills-loader.md), [02-components/llm-abstraction.md](./02-components/llm-abstraction.md), [02-components/mcp-registry.md](./02-components/mcp-registry.md) | [adr/0001-typescript-monorepo.md](./adr/0001-typescript-monorepo.md), [adr/0002-provider-agnostic-llm.md](./adr/0002-provider-agnostic-llm.md), [adr/0003-claude-agent-sdk-default.md](./adr/0003-claude-agent-sdk-default.md) |
| **§7 — Human-in-the-loop** | Every approval-gated tool call and every agent question routes through a HITL primitive; both surfaces display the same queue; audit trail is append-only | [02-components/human-in-the-loop.md](./02-components/human-in-the-loop.md), [02-components/task-state.md](./02-components/task-state.md) | [06-security.md](./06-security.md), [04-api-contracts.md](./04-api-contracts.md), [05-sequence-flows.md](./05-sequence-flows.md) |
| **§8 — Success criteria** | Measurable thresholds for autonomous task completion, memory recall, token efficiency, knowledge retrieval, MCP registration speed, HITL latency, test pass rate, multi-tenant isolation, cost control, provider swap, delivery bundle completeness, and UI parity | [00-overview.md](./00-overview.md) §4 (this document) | [07-roadmap.md](./07-roadmap.md), [06-security.md](./06-security.md) |

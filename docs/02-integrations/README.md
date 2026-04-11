# Integration Matrix — Agent Studio MCP Servers

Agent Studio is a pure **MCP client**. Every external capability — memory, repo operations, browser automation, enterprise systems, knowledge retrieval, structural code analysis, and deep coding workers — is exposed through an MCP server. This document is the authoritative integration matrix for all ten servers Agent Studio connects to.

---

## Integration Matrix

| MCP Server | Purpose | Transport | Who Runs It | Primary Tools | Roles Allowed | Approval-Gated |
|---|---|---|---|---|---|---|
| **Ruflo** | Persistent cross-session memory and learned patterns (HNSW vector store, 8 memory types, project/local/user scopes) | `stdio` child process (dev/single-node) or `streamable-http` (central sidecar shared across orchestrator replicas) | External — upstream `ruvnet/ruflo` distribution, pinned version in MCP Registry | `memory.store`, `memory.search`, `pattern.lookup`, `pattern.store` *(names finalized against published Ruflo manifest at integration time)* | All roles (read); planner/coder/tester/reviewer (write at defined checkpoints only) | No |
| **WMS** *(user-provided)* | Read and update enterprise WMS configuration and source artifacts | As configured by the user's existing server (`http`, `sse`, or `stdio`) | External — already built and operated by the user; Agent Studio is client-only | `wms.read_config`, `wms.update_config`, `wms.read_source`, `wms.apply_patch` *(illustrative — finalized against the real server manifest)* | coder (read + write); planner, reviewer (read-only); tester (read-only) | **Yes** — `wms.update_config`, `wms.apply_patch` require HITL approval |
| **Git MCP** | Local repository operations: clone, branch, stage, commit, diff, log, status | `stdio` — spawned via `npx @modelcontextprotocol/server-git` (or equivalent) | Sidecar spawned per orchestrator pod | `git.clone`, `git.status`, `git.diff`, `git.stage`, `git.commit`, `git.branch`, `git.checkout`, `git.log` | coder (all); planner, tester, reviewer (read-only: `git.status`, `git.diff`, `git.log`) | No — writes are local-only; `git.push` is handled by GitHub MCP |
| **GitHub MCP** | Remote forge operations: PRs, issues, code search, reviews, merges | `streamable-http` — upstream GitHub-maintained MCP server; swap for GitLab/Bitbucket via registry | Central sidecar / upstream hosted service | `github.create_pr`, `github.list_prs`, `github.get_pr`, `github.add_comment`, `github.search_code`, `github.search_issues`, `github.merge_pr` | coder (`create_pr`, `add_comment`); reviewer (`get_pr`, `merge_pr`, all review tools); planner, tester (read-only) | **Yes** — `github.create_pr`, `github.merge_pr` require HITL approval |
| **Playwright MCP** | Browser automation, E2E test generation, execution, visual verification, and report capture | `stdio` inside a Docker sandbox (no external network) | Sidecar container (`@playwright/mcp` or equivalent) | `playwright.launch`, `playwright.navigate`, `playwright.click`, `playwright.fill`, `playwright.snapshot`, `playwright.run_test`, `playwright.get_report` | **Tester only** | No — fully sandboxed; no network egress |
| **Filesystem MCP** | Scoped read/write access inside the task's working directory | `stdio` — `@modelcontextprotocol/server-filesystem` | Spawned per orchestrator pod | `fs.read`, `fs.write`, `fs.list`, `fs.search` | coder (read + write); planner, tester, reviewer (read-only) | No — path-jailed to task working directory |
| **Fetch MCP** | Fetch a URL and return its content as Markdown | `stdio` — `@modelcontextprotocol/server-fetch` | Spawned per orchestrator pod | `fetch.url` | All roles | No — read-only; domain allowlist enforced |
| **code-review-graph** | Structural knowledge graph of the codebase and of agent-produced artifacts. Blast-radius, impact, callers/callees, test coverage, architecture overview, risk-scored change summaries, community-detected wiki, interactive visualization | `stdio` (spawn Python MCP server) or sidecar container | External — upstream `tirth8205/code-review-graph`, pinned version | `graph.build`, `graph.update`, `graph.detect_changes`, `graph.impact_radius`, `graph.callers_of`, `graph.callees_of`, `graph.tests_for`, `graph.semantic_search`, `graph.architecture_overview`, `graph.wiki_generate`, `graph.visualize` *(per published 22-tool manifest)* | planner (`architecture_overview`, `semantic_search`); coder (`impact_radius`, `callers_of`, `callees_of`, `update`); tester (`tests_for`, `impact_radius`); reviewer (all — drives the delivery bundle) | No |
| **ClaudeCode Worker MCP** *(internal)* | Expose Claude Code as the deep-work inner loop. Mode A: in-process `query()` via Claude Agent SDK. Mode B: sandboxed Docker subprocess | `stdio` (in-process) or Docker-spawned subprocess | Shipped in-tree as the `deep-coding` package | `claude_code.run`, `claude_code.spawn_worker`, `claude_code.status`, `claude_code.cancel`, `claude_code.stream_events` | coder (both modes); tester (`claude_code.run` for spec generation); reviewer (structural walks); **planner: DENIED** (anti-nesting rule) | **Yes** — `claude_code.spawn_worker` with `permissionMode=bypassPermissions` requires HITL approval |
| **Knowledge Retrieval MCP** *(internal)* | Federated "have we seen this before?" over web, Confluence, SharePoint, and GitHub search | `stdio` | Shipped in-tree as an MCP server package | `knowledge.search`, `knowledge.fetch` | All roles | No |

---

## Key Interaction Principles

### 1. Single Tool-Use Loop, Many Servers

Agents do not know which server handles a given tool call. They call `memory.search`, `git.diff`, or `knowledge.search` — the `mcp-client` package routes by tool name prefix to the correct server. There are no bespoke code paths for individual integrations in the agent runtime; the MCP boundary is the single seam.

### 2. No Forking

Ruflo, WMS MCP, Git MCP, GitHub MCP, Playwright MCP, Filesystem MCP, and Fetch MCP are all consumed **as upstream distributions**. Versions are pinned in the MCP Registry and upgraded on a deliberate schedule. Forking any of them would be a significant maintenance burden and is explicitly forbidden:

- **Ruflo:** ADR-0009 records the no-fork decision. Only its memory and pattern tools are used; its swarm/queen/router/consensus features are out of scope.
- **code-review-graph:** ADR-0006 records the consume-not-reimplement decision.

Internal MCP servers (Knowledge Retrieval MCP, ClaudeCode Worker MCP) are built in-tree because they implement Agent Studio-specific orchestration logic that no upstream project provides.

### 3. Transport Choice Drives Deployment

| Transport | When to Use | Deployment Pattern |
|---|---|---|
| `stdio` | Server is a local binary or npx package; low-latency, no auth required | Spawned as a child process per orchestrator pod; dies with the pod |
| `streamable-http` | Server must be shared across orchestrator replicas (e.g. Ruflo memory must be consistent) | Runs as a central sidecar service; URL configured in MCP Registry |
| `sse` | Legacy HTTP streaming; used only when `streamable-http` is unavailable | Same as `streamable-http` deployment pattern |

stdio servers are cheap and simple; use them for everything that doesn't need cross-replica state. HTTP/SSE servers run as sidecars or independent services; use them when state must be shared.

### 4. Failure Isolation

Losing any one MCP server degrades the task rather than breaking it:

| Server Down | Behavior |
|---|---|
| Ruflo | Runs proceed stateless; a `memory_unavailable` warning event is emitted; no silent data loss |
| code-review-graph | Reviewer falls back to diff-based summary; task flagged `partial_delivery` |
| Playwright | Tester blocks for HITL review |
| WMS (write task) | Task blocks for HITL; operator can retry or override |
| Git | Coder cannot commit; task blocks for HITL |
| Knowledge Retrieval | Agents proceed without external context; warning event emitted |
| GitHub | PR creation/merge blocked; task pauses at reviewer handoff |

The orchestrator's MCP health monitor emits `tool_unavailable` events on heartbeat failure, masks the affected tools from the role's allowlist, and records the degraded state to the audit log.

### 5. Secrets Never in Config Files

All credentials — GitHub PAT, WMS auth token, Ruflo endpoint secret, Confluence API token, SharePoint client secret, Anthropic API key, web-search API keys — are **referenced by name** in the `McpServerSpec` and **resolved at server-spawn time** from the secrets backend (HashiCorp Vault or cloud KMS). They are never:

- Written to any config file, database row, or registry entry
- Logged in any MCP call log, audit trail, or error message
- Passed through environment variables that persist after server spawn

The `McpServerSpec.env[].valueFrom.secret` field holds only the secret name, never the value. The MCP client resolves the name before forking the child process or constructing the HTTP auth header.

---

## McpServerSpec Schema (Reference)

Every MCP server registered with Agent Studio is described by a typed `McpServerSpec`. The schema below is the canonical definition; individual integration docs include a concrete YAML snippet.

```yaml
name: string                       # unique server name (used as tool prefix)
version: string                    # semver or semver range (e.g. "^1.46.0")
source:
  kind: npx | docker | http | binary | git
  package: string                  # npm package (npx), Docker image, git URL, or binary path
transport: stdio | streamable-http | sse
command?: string[]                 # argv for stdio servers (auto-built from source.kind if omitted)
url?: string                       # base URL for http/sse servers
env:
  - name: string
    value?: string                 # literal value (non-secret only)
    valueFrom?:
      secret: string               # secret name — resolved at spawn time from secrets backend
healthcheck:
  tool: string                     # tool name to call as a ping (e.g. "playwright.ping")
  intervalMs: number
  timeoutMs: number
retries:
  maxAttempts: number
  backoffMs: number
allowlist:
  planner:  string[]               # glob patterns (e.g. ["graph.architecture_overview"])
  coder:    string[]
  tester:   string[]
  reviewer: string[]
approvalRequired: string[]         # tool names that require HITL before execution
sandbox?: string                   # named sandbox profile (e.g. "docker-playwright")
enabled: boolean
```

---

## Further Reading

Each integration has a dedicated file with full tool-by-tool documentation, per-role allowlists, failure handling, and a config snippet:

- [Ruflo — Persistent Memory](./ruflo.md)
- [WMS — Enterprise WMS Server](./wms.md)
- [Git — Local Repository Operations](./git.md)
- [GitHub — Remote Forge Operations](./github.md)
- [Playwright — Browser Automation and Testing](./playwright.md)
- [Filesystem — Scoped Workspace I/O](./filesystem.md)
- [Fetch — URL to Markdown](./fetch.md)
- [Knowledge Retrieval MCP — Federated Search](./knowledge.md)
- [ClaudeCode Worker MCP — Deep Coding Inner Loop](./claude-code-worker.md)
- [code-review-graph — Structural Code Knowledge Graph](./code-review-graph.md)

# Ruflo — Persistent Memory Integration

## What Is Ruflo?

[Ruflo](https://github.com/ruvnet/ruflo) (`ruvnet/ruflo`) is a self-hosted MCP server that provides cross-session persistent memory, eight typed memory categories, HNSW-indexed vector search, PostgreSQL RuVector storage, AgentDB, and pattern storage. It is the memory backbone for Agent Studio's agents.

Agent Studio consumes Ruflo exclusively as an **MCP client** — it calls Ruflo's tools through the standard MCP tool-use loop, exactly like any other server in the registry. No code from Ruflo is copied, modified, or embedded in Agent Studio.

---

## ADR Reference: Not Forked (ADR-0009)

ADR-0009 records the decision to consume Ruflo as an upstream distribution rather than forking it. Key reasons:

- Ruflo already ships exactly the memory infrastructure Agent Studio needs (HNSW vector search, 8 memory types, project/local/user scopes, pattern storage).
- Forking would bind Agent Studio to maintaining a vector-DB stack, which is outside scope.
- Consuming via MCP means a future memory-backend swap is localized to the thin `MemoryClient` wrapper described below — agent-runtime code is entirely unaffected.
- Ruflo's **swarm, queen, router, and consensus** features are explicitly **out of scope** for Agent Studio. The orchestrator owns all multi-agent routing and task-state logic; Ruflo is a memory utility, not an orchestration layer.

---

## Transport

Ruflo supports two deployment modes, selected in the `McpServerSpec`:

| Mode | Transport | When to Use |
|---|---|---|
| **stdio child** | `stdio` | Development, single-node deployments. Ruflo starts as a child process of the orchestrator pod. Memory is local to that pod unless Ruflo uses a remote PostgreSQL backend. |
| **Central HTTP sidecar** | `streamable-http` | Production multi-replica deployments. A single Ruflo instance (with its own persistent volume) is shared across all orchestrator replicas, ensuring memory is tenant-global. The orchestrator connects to it by URL. |

Production deployments should use the central HTTP sidecar so that cross-session memory accumulated by one orchestrator replica is visible to all others.

---

## Tools Invoked

> **Note:** Tool names below reflect the current published Ruflo manifest. Names are finalized against the real manifest at integration time; the `MemoryClient` wrapper (see below) is the single place that must change if Ruflo renames a tool.

| Tool | Description | Called by |
|---|---|---|
| `memory.store` | Persist a memory object with type, scope, and payload | Planner, Coder, Tester, Reviewer (at defined write points) |
| `memory.search` | Vector search over stored memories; returns top-K hits with scores | All roles (at defined read points) |
| `pattern.store` | Persist a learned pattern (e.g. a successful fix strategy) with structured metadata | Coder (after successful fix), Tester (after test pass) |
| `pattern.lookup` | Fuzzy-lookup stored patterns by description or tags | Planner (before planning), Coder (before each retry) |

**Ruflo features NOT used by Agent Studio:**

- `swarm.*` — multi-agent swarm coordination
- `queen.*` — queen/worker task delegation
- `router.*` — Ruflo's own message routing
- `consensus.*` — distributed consensus primitives

These are disabled in the `allowlist` section of the `McpServerSpec` (all four roles get empty arrays for those prefixes).

---

## The `MemoryClient` Wrapper

The `agent-runtime` package exposes a thin `MemoryClient` class that wraps all Ruflo MCP calls. No agent, planner, or role implementation calls `memory.*` tools directly — they call `MemoryClient` methods. This isolates all Ruflo-specific names and argument shapes behind a stable interface:

```typescript
// packages/agent-runtime/src/memory/MemoryClient.ts

export interface MemoryHit {
  id: string;
  scope: RufloScope;
  kind: MemoryKind;
  payload: unknown;
  score: number;
  createdAt: string;
}

export type RufloScope = 'user' | 'project' | 'local';

export type MemoryKind =
  | 'fact'
  | 'decision'
  | 'error'
  | 'fix'
  | 'test_result'
  | 'clarification'
  | 'pattern'
  | 'summary';

export class MemoryClient {
  constructor(private readonly mcpClient: McpClient) {}

  /**
   * Store a memory in Ruflo.
   * @param scope  Agent Studio scope context (resolved to a Ruflo scope via mapScope)
   * @param kind   One of the 8 typed memory categories
   * @param payload Arbitrary serializable content
   */
  async remember(
    scope: AgentStudioScope,
    kind: MemoryKind,
    payload: unknown,
  ): Promise<void> {
    const rufloScope = this.mapScope(scope);
    await this.mcpClient.callTool('memory.store', {
      scope: rufloScope,
      kind,
      payload,
      metadata: {
        tenantId: scope.tenantId,
        projectId: scope.projectId,
        taskId: scope.taskId,
      },
    });
  }

  /**
   * Search Ruflo memory and return the top-K most relevant hits.
   * @param query  Natural language or embedding query
   * @param topK   Maximum results to return (default: 5)
   */
  async recall(query: string, topK = 5): Promise<MemoryHit[]> {
    const result = await this.mcpClient.callTool('memory.search', {
      query,
      topK,
    });
    return result.hits as MemoryHit[];
  }

  /**
   * Store a learned pattern for future retrieval.
   */
  async rememberPattern(
    description: string,
    tags: string[],
    payload: unknown,
  ): Promise<void> {
    await this.mcpClient.callTool('pattern.store', {
      description,
      tags,
      payload,
    });
  }

  /**
   * Lookup previously learned patterns by description or tags.
   */
  async recallPatterns(query: string, topK = 3): Promise<MemoryHit[]> {
    const result = await this.mcpClient.callTool('pattern.lookup', {
      query,
      topK,
    });
    return result.patterns as MemoryHit[];
  }

  private mapScope(scope: AgentStudioScope): RufloScope {
    if (scope.taskId) return 'local';      // task-scoped → Ruflo "local"
    if (scope.projectId) return 'project'; // project-scoped → Ruflo "project"
    return 'user';                         // tenant-scoped → Ruflo "user"
  }
}
```

If Ruflo renames `memory.store` to `memory.write` in a future release, the fix is one line in `MemoryClient.remember()`. No agent code changes.

---

## Scope Mapping

Agent Studio identifies memory by a three-level hierarchy that maps onto Ruflo's native scopes:

| Agent Studio concept | Ruflo scope | Lifetime | Example content |
|---|---|---|---|
| `tenantId` (no project/task) | `user` | Until explicitly purged | Tenant-level preferences, known error patterns across all projects |
| `tenantId` + `projectId` | `project` | Project lifetime | Architectural decisions, recurring patterns for this repo |
| `tenantId` + `projectId` + `taskId` | `local` | Task lifetime | In-progress reasoning, intermediate results, clarifications from this run |

Ruflo's storage is keyed by scope, so project-level memories from one task are visible to future tasks on the same project, while task-local memories are isolated.

---

## Write Points

Agents write to Ruflo memory at the following points in the delivery loop:

| Event | Role | Kind | Scope | What is stored |
|---|---|---|---|---|
| Planning complete | Planner | `decision` | `project` | Decomposed plan, module assignments, assumptions |
| Successful fix committed | Coder | `fix` | `project` | Diff summary, root cause, fix strategy |
| Test suite passes | Tester | `test_result` | `project` | Test surface, pass rate, coverage delta |
| Human clarification received | Any | `clarification` | `local` or `project` | Question, human answer, whether it generalised |
| Pattern identified | Coder | `pattern` | `project` | Reusable fix pattern with tags |
| Task completed | Reviewer | `summary` | `project` | Delivery summary, impact radius, linked PR |

---

## Read Points

Agents read from Ruflo at the following points:

| Event | Role | Query | Purpose |
|---|---|---|---|
| Before planning | Planner | Task requirement text | Surface similar past tasks, known constraints |
| Before each retry | Coder | Error message + file path | Check if this exact error has been solved before |
| Before review | Reviewer | Changed module names | Surface past review findings for the same modules |
| On test failure | Tester | Test name + error | Check if this test failure has a known fix |
| Before non-trivial fix | Coder | Symptom description | Surface patterns before attempting knowledge retrieval |

Memory reads are always followed by knowledge retrieval if no memory hit scores above the relevance threshold. This two-stage lookup (cheap local memory first, expensive federated search second) keeps costs low.

---

## Fallback Behaviour

If Ruflo is unreachable at any read or write point:

1. The MCP client emits a `tool_unavailable` event tagged `server=ruflo`.
2. The orchestrator records a `memory_unavailable` warning in the task event log.
3. The requesting role receives an empty result (no hits) and proceeds **stateless** — it does not retry indefinitely or block the task.
4. Write calls are silently dropped (not queued for later delivery) to avoid stale memory poisoning.
5. The delivery bundle is flagged `memory_degraded` in its metadata.

There is no hard dependency on Ruflo. Every task can complete without it; the degradation is surfaced to the operator and recorded in the audit log.

---

## Config Snippet

```yaml
# config/mcp-servers.d/ruflo.yaml
# — or — tenant override in mcp_server_registrations table

name: ruflo
version: "^0.3.0"          # pin to tested minor; update explicitly
source:
  kind: http               # central sidecar in production
  # kind: npx              # uncomment for single-node / dev
  # package: "ruflo"
url: "https://ruflo.internal.example.com/mcp"
transport: streamable-http
env:
  - name: RUFLO_API_KEY
    valueFrom:
      secret: ruflo-api-key          # resolved from Vault/KMS at connection time
  - name: RUFLO_TENANT_ID
    valueFrom:
      secret: ruflo-tenant-id
healthcheck:
  tool: memory.search                # lightweight vector search with empty query as ping
  intervalMs: 30000
  timeoutMs: 5000
retries:
  maxAttempts: 3
  backoffMs: 1000
allowlist:
  planner:  ["memory.search", "pattern.lookup"]
  coder:    ["memory.store", "memory.search", "pattern.store", "pattern.lookup"]
  tester:   ["memory.search", "memory.store", "pattern.lookup"]
  reviewer: ["memory.search", "memory.store", "pattern.lookup"]
approvalRequired: []
enabled: true
```

For stdio (dev/single-node):

```yaml
name: ruflo
version: "^0.3.0"
source:
  kind: npx
  package: "ruflo"
transport: stdio
env:
  - name: RUFLO_DATA_DIR
    value: "/var/agent-studio/ruflo-data"
  - name: DATABASE_URL
    valueFrom:
      secret: ruflo-postgres-url
healthcheck:
  tool: memory.search
  intervalMs: 30000
  timeoutMs: 5000
allowlist:
  planner:  ["memory.search", "pattern.lookup"]
  coder:    ["memory.store", "memory.search", "pattern.store", "pattern.lookup"]
  tester:   ["memory.search", "memory.store", "pattern.lookup"]
  reviewer: ["memory.search", "memory.store", "pattern.lookup"]
approvalRequired: []
enabled: true
```

---

## Ruflo Features Explicitly Out of Scope

The following Ruflo capabilities are **not enabled** in Agent Studio's MCP allowlists:

| Feature | Why excluded |
|---|---|
| `swarm.*` | Agent Studio's orchestrator owns all multi-agent routing; Ruflo swarm would create a competing orchestration layer |
| `queen.*` | Queen/worker task delegation is replaced by Agent Studio's planner → coder → tester → reviewer pipeline |
| `router.*` | Ruflo's message routing is not needed; the MCP client routes by tool prefix |
| `consensus.*` | Distributed consensus is not applicable to Agent Studio's single-orchestrator model |

These tools receive an empty allowlist (`[]`) for all four roles, so even if Ruflo advertises them, agents cannot call them.

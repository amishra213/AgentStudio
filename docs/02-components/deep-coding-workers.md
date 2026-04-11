# Deep Coding Workers

The Deep Coding Workers are the **inner loop** of Agent Studio. Whenever real task breakdown, iterative coding, or long-running editing is required, the outer agent roles delegate to a Claude Code session that owns that inner loop. Claude Code is hosted *with* Agent Studio — not beside it — and is invoked exclusively through the `ClaudeCode Worker MCP` server, which means it shares the same allowlist, observability, and approval infrastructure as every other capability.

---

## Why delegate instead of doing deep work in the outer roles?

The four outer roles (Planner, Coder, Tester, Reviewer) are **short-running coordinators**. Asking them to also run multi-step iterative coding loops creates several problems:

| Problem | Consequence |
|---|---|
| Long context accumulation | Outer role context grows unbounded across many edit-run-fix iterations, increasing cost and reducing coherence |
| Nested re-planning risk | If the outer role re-plans inside the same context, two plan levels exist and contradict each other |
| No isolation | A failure or hang in the coding loop blocks the outer role's ability to handle HITL or routing decisions |
| Parallel exploration impossible | The outer role can only follow one path; parallel A/B exploration requires separate processes |

Claude Code already solves the inner loop problem: plan mode, todo tracking, iterative edit-run-fix, SKILLs loading, nested subagents, and permission modes. The `DispatchEnvelope` is the clean boundary between the two layers.

---

## Two dispatch modes

Both modes are surfaced as tools on the internal `ClaudeCode Worker MCP` server, built in the `packages/deep-coding` package.

### Mode A — In-process nested session (`claude_code.run`)

```
claude_code.run(envelope: DispatchEnvelope) → WorkerResult
```

- Implemented on top of `query()` from `@anthropic-ai/claude-agent-sdk` — the same engine Claude Code itself runs on.
- Runs in the **same Node.js process** as the Orchestrator. No container overhead. Low latency.
- Inherits tenant, workspace, SKILLs directory, and the scoped MCP server subset from the dispatching role.
- Emits streaming progress events (tool calls, todos, plan changes, intermediate messages) forwarded to Web UI and VS Code in real time.
- Cancelled via the SDK's `AbortSignal` when the Orchestrator receives `task.cancel` or `task.pause`.
- **Default mode** for most Coder and Tester work.

### Mode B — Sandboxed worker (`claude_code.spawn_worker`)

```
claude_code.spawn_worker(envelope: DispatchEnvelope) → WorkerResult
```

- Spawns a full Claude Code process (headless `claude -p` equivalent) inside a **per-task Docker container** running as a Kubernetes Job on the dedicated worker node pool.
- Used for: long-running refactors, untrusted tasks, parallel A/B exploration, or anything requiring physical isolation from the main process.

**Container configuration:**

| Resource | Value |
|---|---|
| Repo snapshot | Read-only bind mount (produced by Git MCP `clone` at task start) |
| Writes | Overlay filesystem (`overlayfs`); diffed back at job completion |
| MCP config | Scoped config file written into the container — narrowest subset the task needs |
| Secrets | Anthropic API key + any task-specific secrets injected as environment variables at spawn time via the secrets backend; never baked into the image |
| CPU | Configurable ceiling (default: 2 vCPU) |
| Memory | Configurable ceiling (default: 4 GiB) |
| Wall time | Configurable ceiling (default: 30 min); Job is killed on overrun |
| Network egress | Anthropic API endpoint + configured MCP server endpoints only; all other egress blocked by network policy |

The Reviewer role uses `spawn_worker` for **parallel A/B exploration**: fan out N workers with different approaches, wait on all results, pick the winner by success-criteria score.

---

## DispatchEnvelope — the single boundary

Every `claude_code.run` or `spawn_worker` call takes a typed `DispatchEnvelope`. This is the **only** way the outer role communicates intent to the inner loop.

```typescript
// packages/shared-types/src/dispatch-envelope.ts

export interface DispatchEnvelope {
  /** Natural language objective for this dispatch */
  goal: string;

  /** Workspace configuration */
  workspace: {
    path: string;                  // absolute path inside the worker's FS
    baseRef: string;               // git ref the overlay is based on (e.g. 'main')
    writableGlobs: string[];       // e.g. ['src/**', 'tests/**', '!*.lock']
  };

  /** Machine-checkable exit conditions */
  successCriteria: {
    tests?: string[];              // shell commands to run; all must exit 0
    graphChecks?: string[];        // e.g. 'graph.impact_radius(<=3) within allowed modules'
    customScript?: string;         // path to an evaluation script
  };

  /** Resource limits for the inner session */
  toolBudget: {
    maxToolCalls: number;          // e.g. 200
    maxTokens: number;             // e.g. 100_000 (input + output combined)
    maxWallSeconds: number;        // e.g. 1800 (30 min)
  };

  /** Narrowest MCP subset the inner session should see */
  mcpServers: McpServerSpec[];

  /** Path to the SKILLs directory (tenant-level or subset) */
  skillsDir?: string;

  /** Permission mode for the inner Claude Code session */
  permissionMode: 'default' | 'acceptEdits' | 'plan' | 'bypassPermissions';

  /** Pre-fetched memory context (avoids cold retrieval inside the inner loop) */
  memoryContext: MemoryHit[];

  /** Pre-fetched knowledge search results */
  knowledgeContext: KnowledgeHit[];

  /** Shape of the result the outer role expects */
  returnShape: 'diff' | 'diff+summary+telemetry';

  /** Trace context for observability linking */
  traceContext: {
    taskId: string;
    runId: string;
    role: AgentRole;
    envelopeHash: string;           // hash of the envelope for deduplication
  };
}

export interface WorkerResult {
  exitReason: ExitReason;
  diff: string;                    // unified diff of all changes made
  todoList?: TodoItem[];           // final todo state from Claude Code's plan mode
  summary?: string;                // human-readable summary (when returnShape includes 'summary')
  telemetry?: WorkerTelemetry;     // per-iteration cost + tool-call breakdown
  blockedQuestion?: HitlQuestion;  // populated when exitReason === 'blocked_hitl'
  cost: { inputTokens: number; outputTokens: number; estimatedUsd: number };
}

export type ExitReason =
  | 'success'           // successCriteria all passed
  | 'blocked_hitl'      // inner session needs human input → outer role handles
  | 'timeout'           // maxWallSeconds exceeded
  | 'over_budget'       // maxTokens or maxToolCalls exceeded
  | 'crashed'           // unexpected process exit / container OOM
  | 'cancelled';        // AbortSignal triggered by task.cancel or task.pause

export interface WorkerTelemetry {
  iterations: number;
  totalToolCalls: number;
  iterationBreakdown: Array<{
    iteration: number;
    toolCalls: number;
    inputTokens: number;
    outputTokens: number;
    wallMs: number;
  }>;
}
```

---

## Anti-nested-planning rule

The Planner role **must not** dispatch to Claude Code workers. Planning happens exactly once, inside the Planner's own turn, and produces a structured plan that all subsequent roles consume.

Enforcement is dual-layer:

**Layer 1 — Allowlist (hard boundary):**
The MCP client's per-role allowlist for the Planner explicitly excludes all `claude_code.*` tools. A call attempt returns `tool_denied` and is audit-logged.

**Layer 2 — Prompt (soft reinforcement):**
The Planner system prompt explicitly states: *"Do not call claude_code.run or claude_code.spawn_worker. Your output is a structured plan; do not implement anything."*

**Layer 3 — `permissionMode` guard:**
The `DispatchEnvelope.permissionMode` field is validated at dispatch time. If a role other than a Planner-scoped context sets `permissionMode: 'plan'`, the `deep-coding` package logs an `ANTI_NESTING_VIOLATION` error and rejects the envelope.

See [agent-runtime.md — Anti-nesting invariants](./agent-runtime.md#anti-nesting-invariants) for the full list of invariants.

---

## Parallel dispatch (Reviewer A/B exploration)

The Reviewer role can fan out multiple `spawn_worker` calls simultaneously to explore competing approaches:

```typescript
// Reviewer role — parallel A/B exploration
const [resultA, resultB, resultC] = await Promise.all([
  mcpClient.callTool('claude_code.spawn_worker', {
    ...baseEnvelope,
    goal: 'Refactor using Strategy pattern',
    workspace: { ...baseEnvelope.workspace, baseRef: 'task/feature-branch' },
  }),
  mcpClient.callTool('claude_code.spawn_worker', {
    ...baseEnvelope,
    goal: 'Refactor by extracting a shared utility module',
    workspace: { ...baseEnvelope.workspace, baseRef: 'task/feature-branch' },
  }),
  mcpClient.callTool('claude_code.spawn_worker', {
    ...baseEnvelope,
    goal: 'Refactor minimally — inline only the duplicate logic',
    workspace: { ...baseEnvelope.workspace, baseRef: 'task/feature-branch' },
  }),
]);

const best = [resultA, resultB, resultC]
  .filter(r => r.exitReason === 'success')
  .sort(byCriteriaScore)[0];
```

Each worker is a fully isolated Kubernetes Job. A failure in one does not affect the others. The Reviewer picks the best result by `successCriteria` score and applies only that diff.

---

## Cost and observability tagging

Every dispatch is tagged with trace context so the Web UI **MCP Call Log** can show a flattened view across outer and inner loops:

```typescript
interface DeepCodingCallRecord {
  id: string;
  ts: string;
  taskId: string;
  runId: string;
  role: AgentRole;
  mode: 'run' | 'spawn_worker';
  envelopeHash: string;
  exitReason: ExitReason;
  inputTokens: number;
  outputTokens: number;
  estimatedCostUsd: number;
  wallMs: number;
  iterations: number;
  totalToolCalls: number;
}
```

Cost ceilings are enforced by the Orchestrator **before** dispatch (via `countTokens()` estimate) and again by the `toolBudget.maxTokens` limit enforced inside the worker.

---

## Failure isolation

| Exit reason | What happens |
|---|---|
| `success` | Outer role evaluates `successCriteria`, commits diff via Git MCP, proceeds to next phase |
| `blocked_hitl` | Outer role calls `askHuman(blockedQuestion)` via Orchestrator; task transitions to `blocked` |
| `timeout` or `over_budget` | Outer role increments retry counter; retries with a larger budget or escalates to HITL |
| `crashed` | Container is already stopped; Orchestrator logs the crash with container exit code; outer role retries up to limit |
| `cancelled` | Task was cancelled or paused; outer role stops immediately; no retry |

A crashing sandboxed worker (Mode B) kills only its own container. The overlay filesystem is discarded. No other tasks or workers are affected.

In-process sessions (Mode A) are cancelled via `AbortSignal`. The SDK guarantees no tool calls are made after the signal fires; the session stops at the next safe yield point (between tool calls).

---

## Why this layering vs "just use Claude Code directly"

Agent Studio still owns platform concerns that Claude Code by itself does not address:

| Concern | Owner |
|---|---|
| Multi-tenancy, JWT, per-tenant DB isolation | Orchestrator |
| Web UI and VS Code extension | Web / Extension packages |
| Persistent cross-session memory (Ruflo) | Agent Runtime + MCP Client |
| Delivery Bundle (code-review-graph) | Reviewer role + Orchestrator |
| HITL approval flows | Orchestrator + HITL primitive |
| MCP Registry and allowlists | MCP Registry + MCP Client |
| Task state machine, audit log | Orchestrator |
| Cost ceilings and enforcement | Orchestrator |

Claude Code owns the deep-work loop concerns the outer roles would otherwise reinvent:

| Concern | Owner |
|---|---|
| Plan mode and todo tracking | Claude Code inner session |
| Iterative edit-run-fix with tool calls | Claude Code inner session |
| SKILLs loading and nested subagents | Claude Code + SDK |
| Permission modes (`acceptEdits`, `bypassPermissions`) | Claude Code |

The `DispatchEnvelope` is the clean contract between the two layers. Neither layer needs to know anything about the other's internals. Claude Code workers can be upgraded or replaced without changing the outer roles; the outer role logic can evolve without touching the inner loop.

---

## Related components

- [Agent Runtime](./agent-runtime.md) — outer roles that assemble and dispatch envelopes
- [MCP Client](./mcp-client.md) — routes `claude_code.*` tool calls, enforces Planner denial
- [Task State](./task-state.md) — checkpoints written after each worker run
- [Execution Control](./execution-control.md) — `task.cancel` sends AbortSignal; `task.pause` honored at next tool-call boundary
- [Hosting and Deployment](./hosting-and-deployment.md) — Kubernetes Job lifecycle for sandboxed workers
- [Human-in-the-Loop](./human-in-the-loop.md) — `blocked_hitl` exit reason triggers `askHuman`

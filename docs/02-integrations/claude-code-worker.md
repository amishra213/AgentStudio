# ClaudeCode Worker MCP — Deep Coding Inner Loop

## Overview

The ClaudeCode Worker MCP is an **internal MCP server** shipped as `packages/deep-coding`. It exposes Claude Code as the **deep-work inner loop** for Agent Studio's Coder, Tester, and Reviewer roles.

The outer 4-role orchestration layer (Planner → Coder → Tester → Reviewer) handles routing, HITL flows, approvals, and delivery assembly. It does not re-implement plan-mode, todo tracking, or iterative edit-run-fix loops. Instead, whenever real task breakdown and deep coding are required, roles dispatch to a Claude Code session through this MCP server.

The **Planner role is explicitly denied access** to all `claude_code.*` tools — this is the anti-nesting invariant (see below).

---

## Tools

| Tool | Description | Modes |
|---|---|---|
| `claude_code.run` | Execute an in-process Claude Code session via the Claude Agent SDK `query()` primitive | Mode A |
| `claude_code.spawn_worker` | Spawn a sandboxed Claude Code process inside a per-task Docker container | Mode B |
| `claude_code.status` | Poll the status of a running worker (for async Mode B dispatches) | Both |
| `claude_code.cancel` | Cancel a running worker and retrieve any partial results | Both |
| `claude_code.stream_events` | Subscribe to streaming progress events (tool calls, todos, messages) from a running worker | Both |

---

## Mode A — In-Process Session (`claude_code.run`)

Implemented directly on top of `query()` from `@anthropic-ai/claude-agent-sdk`. Runs in the same Node.js process as the orchestrator.

**Characteristics:**
- Low latency, no container overhead
- Inherits tenant, workspace, SKILLs directory, and the scoped MCP server subset from the dispatching role
- Streams progress events back to the orchestrator in real time (tool calls, intermediate reasoning, todo updates, plan changes)
- Cost-effective for most coder/tester/reviewer work
- Used by default unless the task requires isolation or parallel exploration

**When to use Mode A:**
- Standard bug fixes and feature implementations
- Test spec generation
- Reviewer structural walks
- Any work that fits within the outer task's time budget

---

## Mode B — Sandboxed Docker Worker (`claude_code.spawn_worker`)

Spawns a full Claude Code process (headless `claude -p` or equivalent SDK entry point) inside a per-task Docker container.

**Characteristics:**
- Full process isolation — a crash or timeout kills only the container
- Read-only mount of the repo snapshot; writes go to an overlay filesystem diffed back at completion
- Scoped MCP client config written into the container — narrowest subset the task needs
- Environment-injected secrets (Anthropic API key resolved from the secrets backend at spawn)
- CPU/memory/time budgets enforced; hard-killed on overrun
- Network egress allowlist: Anthropic API + configured MCP endpoints only
- Supports parallel dispatch (reviewer can fan out multiple workers for A/B exploration)

**When to use Mode B:**
- Long-running refactors
- Untrusted or experimental tasks
- Parallel approach exploration ("try three fixes, pick the winner")
- Any task the operator wants isolated from the main orchestrator process
- When `permissionMode=bypassPermissions` is required (always HITL-gated)

---

## `DispatchEnvelope` Contract

Every `claude_code.run` or `claude_code.spawn_worker` call takes a fully typed `DispatchEnvelope`. The outer role assembles this envelope before dispatching — including pre-fetching memory and knowledge hits so the inner loop starts hot and does not waste its tool budget on retrieval.

```typescript
interface DispatchEnvelope {
  /** Natural language objective for this inner-loop session */
  goal: string;

  /** Workspace context for the inner loop */
  workspace: {
    path: string;           // absolute path to the task working directory
    baseRef: string;        // git ref the workspace was checked out from
    writableGlobs: string[]; // glob patterns the inner loop is allowed to write
                            // (enforced by Filesystem MCP path-jailing + config)
  };

  /** Machine-checkable success criteria */
  successCriteria: {
    tests?: string[];       // shell commands to run; exit 0 = pass
                            // e.g. ["pnpm test -- src/wms/**", "pnpm lint"]
    graphChecks?: string[]; // code-review-graph assertions
                            // e.g. ["graph.impact_radius(<=3)"]
    customScript?: string;  // arbitrary shell script; exit 0 = pass
  };

  /** Budget controls */
  toolBudget: {
    maxToolCalls: number;   // hard limit on MCP tool invocations
    maxTokens: number;      // hard limit on LLM tokens (input + output)
    maxWallSeconds: number; // hard kill timer
  };

  /** MCP servers available to the inner loop — narrowest subset the task needs */
  mcpServers: McpServerSpec[];

  /** SKILLs directory to load at session start (tenant SKILLs or a subset) */
  skillsDir?: string;

  /** Permission mode passed to Claude Code */
  permissionMode: 'default' | 'acceptEdits' | 'plan' | 'bypassPermissions';

  /** Pre-fetched Ruflo memory hits — inner loop starts hot */
  memoryContext: MemoryHit[];

  /** Pre-fetched knowledge.search results — inner loop starts hot */
  knowledgeContext: KnowledgeHit[];

  /** What the outer loop expects back */
  returnShape: 'diff' | 'diff+summary+telemetry';
}

interface WorkerResult {
  exitReason: 'success' | 'crashed' | 'timeout' | 'over_budget' | 'blocked_hitl';
  diff: string;             // unified diff of all changes made
  summary?: string;         // human-readable summary of what was done
  telemetry?: {
    iterations: number;
    toolCallCount: number;
    finalTokenCost: number;
    wallMs: number;
    todosCompleted: number;
    todosRemaining: number;
  };
  envelopeHash: string;     // SHA-256 of the DispatchEnvelope for audit correlation
}
```

---

## Per-Role Allowlist

| Role | Allowed Tools | Notes |
|---|---|---|
| **Coder** | `claude_code.run`, `claude_code.spawn_worker`, `claude_code.status`, `claude_code.cancel`, `claude_code.stream_events` | Both modes; primary user of the worker MCP |
| **Tester** | `claude_code.run`, `claude_code.status`, `claude_code.stream_events` | Mode A only; used for test spec generation |
| **Reviewer** | `claude_code.run`, `claude_code.status`, `claude_code.stream_events` | Mode A only; used for structural review walks |
| **Planner** | **DENIED — all `claude_code.*` tools** | Anti-nesting invariant — see below |

---

## Anti-Nesting Invariant

The Planner role is explicitly denied all `claude_code.*` tools. This is the **most important architectural constraint** of the deep-coding design.

**Why:**

If the Planner were allowed to dispatch a Claude Code session, that inner session could itself plan, which creates a planning loop: outer Planner → inner Claude Code Planner → inner-inner work. This results in:

- Unpredictable cost escalation (two planners means the task budget is effectively doubled without authorization)
- Duplicate or conflicting plans
- Obscured audit trail (inner planning is not visible to the outer orchestrator's task state machine)

**The rule:**

> Planning happens exactly once, inside the inner Claude Code session. The Planner role builds a `DispatchEnvelope` with a `goal` and `successCriteria` and delegates. The Coder's inner loop owns the breakdown.

This is enforced at the MCP allowlist level — the Planner's allowed tool list for the `claude_code.*` prefix is an empty array. Even if the Planner's system prompt tried to call `claude_code.run`, the MCP client would return `ToolDeniedError` before the call was forwarded.

---

## Approval Gating

`claude_code.spawn_worker` with `permissionMode: 'bypassPermissions'` is **always approval-gated**. This is the only combination that grants the inner loop unrestricted filesystem and tool access.

```
Coder → claude_code.spawn_worker({ ..., permissionMode: "bypassPermissions" })
  ↓
MCP client intercepts (approvalRequired=true for bypassPermissions)
  ↓
hitl.question { tool: "claude_code.spawn_worker", permissionMode: "bypassPermissions",
                goal: envelope.goal, budget: envelope.toolBudget }
  ↓
Human reviews: what goal, what budget, why bypassPermissions needed
  ↓
  ├── APPROVE → spawn_worker executed inside Docker sandbox
  └── REJECT  → ToolRejectedError; Coder retries with default permissionMode
```

All other `spawn_worker` calls (with `default`, `acceptEdits`, or `plan` modes) are not approval-gated.

---

## Streaming Progress Events

The outer orchestrator subscribes to progress events from any running worker via `claude_code.stream_events`. Events are forwarded to the Web UI and VS Code extension in real time:

```typescript
// Event types emitted by the worker during a session
type WorkerEvent =
  | { type: 'tool_call'; toolName: string; args: unknown; callId: string }
  | { type: 'tool_result'; callId: string; result: unknown; latencyMs: number }
  | { type: 'message'; role: 'assistant'; content: string }
  | { type: 'todo_update'; todos: { id: string; text: string; status: string }[] }
  | { type: 'plan_update'; plan: string }
  | { type: 'iteration_complete'; iterationNumber: number; successCriteriaMet: boolean }
  | { type: 'exit'; reason: WorkerResult['exitReason']; result: WorkerResult };
```

These events appear in the Web UI's live task view and the VS Code extension's agent transcript panel. The operator can see exactly what the inner Claude Code session is doing without interrupting it.

---

## Cost and Observability

Every dispatch is tagged:

```json
{
  "task": "task-abc123",
  "role": "coder",
  "server": "claude-code-worker",
  "tool": "claude_code.spawn_worker",
  "mode": "B",
  "envelopeHash": "sha256:...",
  "finalCostTokens": 42000,
  "wallMs": 187430,
  "exitReason": "success",
  "permissionMode": "acceptEdits"
}
```

These records appear in the Web UI's MCP call log alongside all other tool calls. The `envelopeHash` links the outer-loop dispatch record to all inner-loop tool call records, producing a flattened view of the full execution path.

Cost ceilings per tenant (`tenants.cost_ceiling`) are checked by the orchestrator before dispatching. If the projected cost of a dispatch (estimated from `toolBudget.maxTokens`) would exceed the ceiling, the task is blocked with a `budget_exceeded` event.

---

## Failure Isolation

| Exit reason | Outer role behaviour |
|---|---|
| `success` | Receive `WorkerResult.diff`, apply to workspace, continue |
| `crashed` | Log the crash; retry with Mode A (cheaper) or escalate to HITL |
| `timeout` | Log timeout; retrieve partial diff; escalate to HITL: "worker timed out — apply partial diff?" |
| `over_budget` | Retrieve partial diff; raise HITL: "worker exceeded budget — retry with larger budget?" |
| `blocked_hitl` | Inner worker needs human input it cannot get; escalate question to outer HITL queue |

A crashing Mode B container kills only that container. The orchestrator pod, the outer role, and all other tasks are unaffected.

---

## Config Snippet

```yaml
# config/mcp-servers.d/claude-code-worker.yaml

name: claude-code-worker
version: "1.0.0"       # matches Agent Studio release
source:
  kind: binary
  package: "/app/packages/deep-coding/dist/server.js"   # in-tree build artefact
transport: stdio
env:
  - name: ANTHROPIC_API_KEY
    valueFrom:
      secret: anthropic-api-key
  - name: WORKER_DOCKER_IMAGE
    value: "agent-studio/claude-code-worker:latest"
  - name: WORKER_CPU_LIMIT
    value: "2"
  - name: WORKER_MEMORY_LIMIT
    value: "4Gi"
  - name: WORKER_WALL_TIME_LIMIT_S
    value: "1800"      # 30 minutes
healthcheck:
  tool: claude_code.status
  intervalMs: 60000
  timeoutMs: 5000
retries:
  maxAttempts: 1       # do not retry spawn failures automatically
  backoffMs: 5000
allowlist:
  planner:  []         # DENIED — anti-nesting invariant
  coder:
    - "claude_code.run"
    - "claude_code.spawn_worker"
    - "claude_code.status"
    - "claude_code.cancel"
    - "claude_code.stream_events"
  tester:
    - "claude_code.run"
    - "claude_code.status"
    - "claude_code.stream_events"
  reviewer:
    - "claude_code.run"
    - "claude_code.status"
    - "claude_code.stream_events"
approvalRequired:
  - "claude_code.spawn_worker"   # only when permissionMode=bypassPermissions;
                                 # MCP server checks the argument before gating
enabled: true
```

> The `approvalRequired` field lists `claude_code.spawn_worker` as approval-gated. The server implementation inspects the `permissionMode` argument and only triggers the approval gate when it equals `"bypassPermissions"`. All other `spawn_worker` calls proceed without approval.

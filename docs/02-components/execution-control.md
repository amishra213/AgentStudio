# Execution Control

Execution control is the set of **steering verbs** that let users guide a running task from either the Web UI or VS Code extension. Every verb is a first-class REST endpoint, a WebSocket message, and a line in the audit log. None of them require a restart or a new task — they act on the live task state machine.

---

## Steering verb table

| Verb | Effect | Allowed states |
|---|---|---|
| `task.submit` | Create a new task record; enqueue Planner job; transition to `not_started → planning` | — (creates a new task) |
| `task.pause` | Set `pauseRequested` flag; honored at next tool-call boundary; transition to `blocked` with `blocked_reason: pause_requested` | `in_progress`, `planning` |
| `task.resume` | Clear `blockedReason`; reload checkpoint; re-enqueue BullMQ job; transition to `in_progress` | `blocked`, `partially_complete` |
| `task.inject_context` | Append text / file / URL / chat message to `pendingContext`; surfaced to next `DispatchEnvelope.memoryContext` at next dispatch | Any live state |
| `task.override_plan` | Replace the current plan or todo list with the operator-supplied version before the next Coder dispatch | `planning`, `blocked` |
| `task.approve` | Record approval for a pending HITL question or approval-gated tool call; resume the task | `blocked` |
| `task.reject` | Record rejection; agent receives a structured rejection error and decides next step | `blocked` |
| `task.cancel` | Kill all sandboxed workers (k8s Job deletion); cancel in-process sessions (AbortSignal); transition to `cancelled` | Any live state |
| `task.branch` | Fork the task at the current checkpoint into a new sibling task record; original continues unaffected | Any state with a checkpoint |
| `task.rollback` | Load a prior checkpoint; transition to `blocked` with the checkpoint context restored; user resumes manually | Any state with ≥ 2 checkpoints |
| `task.set_budget` | Update `task.budgetCeiling.dollarsUsd` / `maxTokens` / `maxWallSeconds` up or down | Any live state |
| `task.retarget_reviewer` | Update `task.hitlRoutingConfig.reviewerUserId` so future HITL questions are routed to a different user | Any state |

---

## Verb semantics in detail

### `task.submit`

```typescript
POST /api/tasks
{
  title: string;
  businessRequirement: string;
  projectId: string;
  workspace: { repoUrl: string; branch: string; };
  budgetCeiling: { dollarsUsd: number; maxTokens?: number; maxWallSeconds?: number; };
  hitlRoutingConfig: { reviewerUserId: string; timeoutMs?: number; };
  toolOverrides?: { disableTools: string[]; };
  modelOverrides?: { planner?: string; coder?: string; };
}
→ { taskId: string; status: 'not_started' }
```

The Orchestrator validates the request, writes the task record, enqueues the Planner job, and returns immediately. The task moves to `planning` asynchronously.

### `task.pause`

```typescript
POST /api/tasks/:id/pause
{ reason?: string }
```

**Semantics:**
1. Orchestrator sets an in-memory `pauseRequested` flag on the task context. This does **not** immediately kill anything.
2. The next time a Deep Coding Worker checks the flag before a tool call, it exits with `exitReason: 'cancelled'`.
3. The outer agent role receives `WorkerResult{ exitReason: 'cancelled' }` and calls `orchestrator.transition(taskId, 'blocked', { blockedReason: 'pause_requested' })`.
4. A full checkpoint is written at this boundary.
5. Any in-flight MCP tool call completes first — partial external writes are avoided.
6. Budget stops accumulating immediately after the checkpoint is written.

**Why at the tool-call boundary?** Stopping mid-tool-call could leave external systems (git remote, GitHub, WMS) in a partially-written state. The boundary guarantee makes pause safe.

### `task.resume`

```typescript
POST /api/tasks/:id/resume
{ context?: string }   // optional injection alongside resume
```

1. Validates that the task is in `blocked` or `partially_complete`.
2. Loads `current_checkpoint_id` from Postgres.
3. If `context` is provided, prepends it to `pendingContext`.
4. Transitions to `in_progress`.
5. Re-enqueues the BullMQ job for the appropriate role (the role stored in the checkpoint).
6. The next `DispatchEnvelope` includes the restored checkpoint state.

### `task.inject_context`

```typescript
POST /api/tasks/:id/inject
{
  type: 'text' | 'file' | 'url' | 'chat';
  content: string;   // text, file path, URL, or chat message body
  label?: string;    // e.g. "API contract clarification"
}
```

Injected context is appended to `task.pendingContext` (array). The next dispatch reads `pendingContext` and folds it into `DispatchEnvelope.memoryContext`. The inner Claude Code session never sees the steering API — it only sees the enriched envelope.

Injection works in any live state. If the task is currently `in_progress`, the context is held in `pendingContext` and applied at the **next** worker dispatch boundary (not interrupting the current one). If the task is `blocked`, the context is applied when `task.resume` is called.

### `task.override_plan`

```typescript
POST /api/tasks/:id/override-plan
{
  plan: PlanGoal[];   // complete replacement of the current plan
  reason: string;     // audit trail entry
}
```

The current plan is replaced atomically. A checkpoint is written with the new plan. The override is recorded in the audit log with the `before` (old plan) and `after` (new plan). The task must be in `planning` or `blocked` — overriding a plan while the Coder is actively executing goals would cause inconsistency.

### `task.approve` / `task.reject`

```typescript
POST /api/tasks/:id/hitl/:questionId/approve
{ answer?: unknown }   // typed against the question's schema

POST /api/tasks/:id/hitl/:questionId/reject
{ reason: string }
```

See [human-in-the-loop.md](./human-in-the-loop.md) for the full approval flow. The approval or rejection is recorded to both the `hitl_approvals` table and the audit log before the task resumes.

### `task.cancel`

```typescript
POST /api/tasks/:id/cancel
{ reason: string }
```

**Hard stop:**
1. Orchestrator sets `status = 'cancelling'` (transient, not a user-visible state).
2. Calls the Kubernetes API to delete all Jobs with label `task-id: <id>` on the worker node pool.
3. Sends `AbortSignal` to any in-process `query()` sessions via the SDK.
4. Voids any pending approval-gated tool calls — they are **not** executed.
5. Writes final checkpoint and transitions to `cancelled`.
6. Emits `task_cancelled` WebSocket event.

Cancel is immediate for sandboxed workers (container killed) and "best-effort immediate" for in-process sessions (SDK aborts at next yield point, which is typically < 1 second).

### `task.branch`

```typescript
POST /api/tasks/:id/branch
{
  fromCheckpointId?: string;  // defaults to current_checkpoint_id
  title?: string;             // name for the new branch task
}
→ { branchedTaskId: string }
```

1. Loads the specified checkpoint.
2. Creates a new task record with `parent_task_id = id`, `status = 'blocked'`, `current_checkpoint = snapshot of fromCheckpoint`.
3. Writes the branch relationship to `task_branches` table.
4. The original task continues unchanged.
5. The new task is visible in the Web UI task list with a branch indicator.

### `task.rollback`

```typescript
POST /api/tasks/:id/rollback
{
  toCheckpointId: string;   // must be an existing checkpoint for this task
  reason: string;
}
```

1. Validates that `toCheckpointId` belongs to this task.
2. Loads the target checkpoint.
3. Transitions task to `blocked` with `blockedReason: 'rollback'` and the checkpoint context restored.
4. Subsequent checkpoints (those after `toCheckpointId`) are retained for audit but orphaned (not reachable from `current_checkpoint_id`).
5. User calls `task.resume` to continue from the rollback point.

Rollback does **not** undo git commits or external system changes already made. It only restores the agent's context to a prior point. If coder commits need to be reverted, the operator uses `git.revert` through the normal tool-use flow.

### `task.set_budget`

```typescript
PATCH /api/tasks/:id/budget
{
  dollarsUsd?: number;
  maxTokens?: number;
  maxWallSeconds?: number;
}
```

Budget changes take effect before the **next** worker dispatch. The change is written to `tasks.budget_ceiling` and recorded to the audit log. Raising the budget un-blocks a task stuck at `blocked_reason: 'cost_ceiling'`. Lowering the budget does not cancel an in-flight dispatch but will stop the next one.

### `task.retarget_reviewer`

```typescript
PATCH /api/tasks/:id/reviewer
{ reviewerUserId: string }
```

Changes who receives future HITL notifications (WebSocket events and email if configured). Takes effect for the next `askHuman` call — does not affect any currently open HITL question (the original reviewer retains the open question).

---

## REST and WebSocket parity

Every verb is available via both transports:

**REST:**
```
POST /api/tasks/:id/<verb>
Authorization: Bearer <JWT>
Content-Type: application/json
```

**WebSocket message:**
```json
{
  "type": "task.pause",
  "taskId": "task-abc123",
  "payload": { "reason": "Weekly sprint review" }
}
```

The WebSocket path is used by the VS Code extension and the Web UI's live-control panel. The REST path is used for programmatic automation, CI/CD integration, and the CLI. Both are gated by the same JWT and RBAC checks.

---

## Checkpoints: the foundation of rollback and branch

Checkpoints are written:

| Trigger | Checkpoint contents |
|---|---|
| Every state transition | Full task state, plan, completed goals, pending context |
| After each Claude Code worker run | + Last diff, final todo list, test results |
| After each Tester pass | + Test report URL, coverage data |
| After each graph operation (Reviewer) | + Graph step result |
| On every steering verb | + Verb applied, actor, reason |

The checkpoint ID is written to the audit log alongside every steering verb, creating an unambiguous link between human actions and the task state at that moment.

---

## Audit log entries for steering verbs

Every verb is recorded in the `audit_log` table:

```
verb:       'task.pause'
actor_type: 'user'
actor_id:   'user-xyz789'
task_id:    'task-abc123'
before:     { status: 'in_progress', checkpointId: 'cp-001' }
after:      { status: 'blocked', blockedReason: 'pause_requested', checkpointId: 'cp-002' }
reason:     'Weekly sprint review'
ts:         '2026-04-11T14:30:00Z'
```

The audit log is queryable from the Web UI under **Settings → Audit Log** and from the API at `GET /api/audit?taskId=<id>`.

---

## Related components

- [Task State](./task-state.md) — the state machine these verbs act on
- [Orchestrator](./orchestrator.md) — processes the verbs and enforces guards
- [Human-in-the-Loop](./human-in-the-loop.md) — `task.approve` / `task.reject` flows
- [Deep Coding Workers](./deep-coding-workers.md) — how `task.cancel` and `task.pause` are propagated
- [Web UI](./web-ui.md) — surfaces all verbs in the task control panel
- [VS Code Extension](./vscode-extension.md) — surfaces the same verbs inline

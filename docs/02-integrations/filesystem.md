# Filesystem MCP — Scoped Workspace I/O

## Overview

The Filesystem MCP server (`@modelcontextprotocol/server-filesystem`) gives agents structured read/write access to the task's working directory. It is the primary mechanism by which the Coder writes source files, and by which all roles read existing code, configuration, and test artefacts.

Access is strictly **path-jailed** to the task working directory. Agents cannot read or write outside this boundary, regardless of which role is active. There are no approval gates — the path-jail is the security boundary.

---

## Transport

**`stdio`** — the Filesystem MCP server is spawned as a child process per orchestrator pod. The server is configured with the task working directory as its only allowed root. A new server instance (or a new configuration of the same instance) is used per task to ensure the root path is correctly scoped.

```
Orchestrator pod → spawns → npx @modelcontextprotocol/server-filesystem --root /tasks/{taskId}/workspace
```

---

## Tools

| Tool | Description | Roles (R / RW) |
|---|---|---|
| `fs.read` | Read a file from the workspace | All roles (R) |
| `fs.write` | Write or overwrite a file in the workspace | Coder only (RW) |
| `fs.list` | List directory contents | All roles (R) |
| `fs.search` | Search file contents by pattern or glob | All roles (R) |

---

## Per-Role Allowlist

| Role | Allowed Tools |
|---|---|
| **Coder** | `fs.read`, `fs.write`, `fs.list`, `fs.search` |
| **Planner** | `fs.read`, `fs.list`, `fs.search` |
| **Tester** | `fs.read`, `fs.list`, `fs.search` |
| **Reviewer** | `fs.read`, `fs.list`, `fs.search` |

Only the Coder can write files. Planners, testers, and reviewers can read and search the workspace to inform their reasoning but cannot modify it. If a tester needs to generate or modify test spec files, it does so by dispatching a `claude_code.run` DispatchEnvelope to the Coder worker, which handles the write.

> **Note:** The Tester's Playwright MCP sandbox has its own isolated filesystem and does not use the Filesystem MCP server for test execution. The Filesystem MCP is used by the Tester only for reading specs, configs, and source to understand context.

---

## Path Jailing

The Filesystem MCP server enforces path jailing at the server level. When the server is spawned, it receives the task workspace root as the `--root` argument (or equivalent config). Any request to access a path outside that root is rejected with a permission error — this enforcement happens inside the MCP server process, not in Agent Studio code.

The path jail boundaries:

```
ALLOWED:   /tasks/{taskId}/workspace/**
DENIED:    /tasks/{otherTaskId}/workspace/**   (other task's workspace)
DENIED:    /etc/**                             (system files)
DENIED:    /var/agent-studio/**               (platform internals)
DENIED:    ../                                (path traversal attempts)
```

---

## No Approval Gating

Filesystem writes are not approval-gated because:

1. Writes are local to the task's sandbox — they have no immediate external side effects.
2. Code changes are committed to Git (via Git MCP) before they have any impact on the repo, and `git.commit` is itself auditable.
3. The human approval gate for code changes is the GitHub PR merge (`github.merge_pr`), not the individual file write.

If an operator wants approval on every file write for a specific task, a task-level allowlist override can remove `fs.write` from the Coder's allowlist for that task. The Coder would then be unable to write files without escalating to HITL.

---

## Relationship with Other MCP Servers

| Interaction | How it works |
|---|---|
| **Filesystem + Git** | Coder writes files via `fs.write`, then stages and commits them via `git.stage` + `git.commit`. The Git MCP operates on the same workspace directory. |
| **Filesystem + code-review-graph** | The code-review-graph MCP reads the same workspace directory to build and update the structural graph. Changes written by the Coder are immediately visible to `graph.update`. |
| **Filesystem + Playwright** | The Playwright sandbox mounts the workspace read-only at `/workspace` inside the container. Test specs written by the Coder (via `fs.write`) are available to Playwright without any additional sync step. |
| **Filesystem + ClaudeCode Worker** | The inner Claude Code worker (Mode A, in-process) inherits the workspace path from the DispatchEnvelope and calls `fs.*` tools through the same MCP client. Mode B (sandboxed Docker worker) uses an overlay filesystem — writes go to the overlay and are diffed back to the workspace on completion. |

---

## Config Snippet

```yaml
# config/mcp-servers.d/filesystem.yaml

name: filesystem
version: "^1.0.0"
source:
  kind: npx
  package: "@modelcontextprotocol/server-filesystem"
transport: stdio
# The --root argument is injected per-task at spawn time by the orchestrator.
# The McpServerSpec below shows the template; {taskId} is substituted at runtime.
command:
  - "npx"
  - "-y"
  - "@modelcontextprotocol/server-filesystem"
  - "--root"
  - "/var/agent-studio/tasks/{taskId}/workspace"
env: []
healthcheck:
  tool: fs.list
  intervalMs: 60000
  timeoutMs: 5000
retries:
  maxAttempts: 3
  backoffMs: 500
allowlist:
  planner:  ["fs.read", "fs.list", "fs.search"]
  coder:    ["fs.read", "fs.write", "fs.list", "fs.search"]
  tester:   ["fs.read", "fs.list", "fs.search"]
  reviewer: ["fs.read", "fs.list", "fs.search"]
approvalRequired: []
enabled: true
```

---

## Error Handling

| Error | Behaviour |
|---|---|
| Path outside jail | Server returns `PermissionDenied`; MCP client surfaces as `ToolCallError`; agent receives the error and must adjust its path |
| File not found (read) | Server returns `NotFound`; agent handles gracefully (e.g. creates the file if it should exist) |
| Disk quota exceeded | Server returns `QuotaExceeded`; orchestrator raises HITL: "workspace disk quota exceeded" |
| Server process crash | MCP client emits `tool_unavailable server=filesystem`; task blocks for HITL |

---

## Workspace Lifecycle

| Event | Action |
|---|---|
| Task created | Orchestrator creates `/var/agent-studio/tasks/{taskId}/workspace/` |
| Task starts | Git MCP clones the repository into the workspace |
| Task runs | Coder reads/writes via Filesystem MCP; commits via Git MCP |
| Task completes | Workspace is archived (tarball) and linked to the task record for audit |
| Archive retention elapsed | Workspace and archive are deleted per tenant data-retention policy |

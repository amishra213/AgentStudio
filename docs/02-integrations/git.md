# Git MCP — Local Repository Operations

## Overview

The Git MCP server gives agents a structured, safe interface to a local Git repository. It is consumed as an upstream distribution — Agent Studio does not build or modify Git tooling. The server is spawned as a `stdio` child process per orchestrator pod and operates on the task's checked-out working directory.

Git MCP handles **local** repository operations only. Remote forge operations (pull requests, issue comments, code search) are handled by the **GitHub MCP** server.

---

## Transport

**`stdio`** — the Git MCP server is spawned via `npx` when the orchestrator pod starts. One server instance is shared across all tasks running on that pod; the working directory passed to each tool call scopes its operation to the correct task workspace.

```
Orchestrator pod → spawns → npx @modelcontextprotocol/server-git
```

If a different Git MCP implementation is preferred (e.g. a pinned binary or a Docker image), the `source.kind` field in the `McpServerSpec` can be changed to `binary` or `docker` without any changes to agent code.

---

## Tools

| Tool | Description | Read / Write |
|---|---|---|
| `git.clone` | Clone a remote repository into the task working directory | Write |
| `git.status` | Show working tree status (modified, staged, untracked files) | Read |
| `git.diff` | Show diff of uncommitted changes or between refs | Read |
| `git.stage` | Stage files for commit (`git add`) | Write |
| `git.commit` | Create a commit with the staged changes and a message | Write |
| `git.branch` | Create, list, or delete branches | Write |
| `git.checkout` | Check out a branch or commit | Write |
| `git.log` | Show commit history for a branch or path | Read |

All write tools operate on the local repository only. There is no `git.push` — pushing to a remote is done through the **GitHub MCP** server's PR creation flow, which is approval-gated.

---

## Per-Role Allowlist

| Role | Allowed Tools |
|---|---|
| **Coder** | All: `git.clone`, `git.status`, `git.diff`, `git.stage`, `git.commit`, `git.branch`, `git.checkout`, `git.log` |
| **Planner** | Read-only: `git.status`, `git.diff`, `git.log` |
| **Tester** | Read-only: `git.status`, `git.diff`, `git.log` |
| **Reviewer** | Read-only: `git.status`, `git.diff`, `git.log` |

The coder is the only role that stages, commits, branches, clones, or checks out. This prevents planners and reviewers from accidentally mutating the working tree.

---

## No Approval Gating

Git write operations are **not approval-gated** because they are local-only. A local commit has no external side effects — it cannot affect the shared repository, trigger CI, or be seen by other users. The human-approval gate is reserved for calls with external side effects (GitHub PR creation, WMS config updates, etc.).

If the operator wishes to add approval gating for specific tasks (e.g. a read-only audit task), the task definition can override the role allowlist to remove write tools for that task without changing the platform default.

---

## How Git MCP Is Used in the Delivery Loop

### 1. Repository Setup (Task Start)

```
Orchestrator assigns task workspace
→ Coder calls git.clone(repoUrl, workDir, ref=baseRef)
→ code-review-graph MCP: graph.build(workDir)  [concurrent]
→ Coder ready to receive DispatchEnvelope
```

### 2. Coder Fix Loop

```
For each fix iteration:
  Coder Claude Code worker edits files via Filesystem MCP
  → Coder calls git.status()                  [verify changes]
  → Coder calls git.diff()                    [review own changes]
  → Coder calls git.stage(files=[...])
  → Coder calls git.commit(message="fix: ...")
  → Orchestrator calls graph.update(workDir)  [incremental graph refresh]
```

Each commit is atomic and produces a stable `HEAD` from which the graph can be updated, the tester can assess changes, and the reviewer can generate an impact report. Commits are also the restore point if the orchestrator needs to roll back to a previous state.

### 3. Branch Management

The coder works on a feature branch created at task start:

```
git.checkout(baseBranch)         [ensure clean start]
git.branch(name=taskBranchName)  [create task branch]
git.checkout(name=taskBranchName)
```

The branch name follows the convention `agent-studio/{taskId}` so it is machine-identifiable in the repository.

### 4. Tester Commits Test Fixes

The tester role commits test spec changes and test infrastructure fixes using the same Git MCP tools:

```
Tester generates/fixes test spec via claude_code.run
→ Tester calls git.stage(files=["tests/..."])
→ Tester calls git.commit(message="test: add/fix specs for ...")
→ Orchestrator calls graph.update(workDir)
```

### 5. Reviewer Reads History

The reviewer calls `git.log` to understand the sequence of changes the coder and tester made during the task. This informs the delivery bundle narrative.

---

## Integration with code-review-graph

After every `git.commit` by the coder or tester, the orchestrator triggers:

```
graph.update(workDir, sinceRef=previousHead)
graph.detect_changes(workDir)
```

This keeps the structural graph in sync with the working tree, ensuring that subsequent `graph.impact_radius`, `graph.tests_for`, and `graph.callers_of` queries reflect the latest committed state. The update completes in approximately 2 seconds on multi-thousand-file repositories.

---

## Config Snippet

```yaml
# config/mcp-servers.d/git.yaml

name: git
version: "^1.0.0"
source:
  kind: npx
  package: "@modelcontextprotocol/server-git"
transport: stdio
env: []                              # Git MCP reads credentials from the host git config / GITHUB_TOKEN
healthcheck:
  tool: git.status
  intervalMs: 60000
  timeoutMs: 5000
retries:
  maxAttempts: 3
  backoffMs: 500
allowlist:
  planner:  ["git.status", "git.diff", "git.log"]
  coder:    ["git.clone", "git.status", "git.diff", "git.stage", "git.commit",
             "git.branch", "git.checkout", "git.log"]
  tester:   ["git.status", "git.diff", "git.log", "git.stage", "git.commit"]
  reviewer: ["git.status", "git.diff", "git.log"]
approvalRequired: []
enabled: true
```

> The tester allowlist includes `git.stage` and `git.commit` because testers commit test spec files and test-infrastructure fixes. If the operator wants to prevent tester commits on a specific task, a task-level allowlist override can remove those tools.

---

## Error Handling

| Error condition | Behaviour |
|---|---|
| Working directory does not exist | `git.clone` fails with a structured error; orchestrator raises HITL: "repository unavailable" |
| Merge conflict after `git.checkout` | `git.checkout` returns conflict details; orchestrator injects conflict context into the coder's next dispatch envelope |
| Empty commit (no staged changes) | `git.commit` returns a `NothingToCommit` error; orchestrator logs and continues — not a failure |
| Server process crashes | MCP client emits `tool_unavailable server=git`; orchestrator blocks task and raises HITL |

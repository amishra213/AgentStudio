# GitHub MCP — Remote Forge Operations

## Overview

The GitHub MCP server provides Agent Studio with access to remote forge operations: creating and merging pull requests, reading and commenting on issues and PRs, and searching code and issues across the organisation's repositories. It is the upstream GitHub-maintained MCP server, consumed as a versioned distribution. Agent Studio does not build or maintain GitHub API client code; the MCP boundary is the contract.

The server is swappable: if the operator's forge is GitLab or Bitbucket, a compatible MCP server for that forge can be registered under the `github` name in the MCP registry. Agent code calls `github.create_pr` regardless of the underlying forge.

---

## Transport

**`streamable-http`** — the GitHub MCP server runs as a central sidecar service (or references GitHub's hosted MCP endpoint). It is shared across all orchestrator replicas so that PR state is consistent.

```
All orchestrator replicas → HTTP → GitHub MCP server → GitHub API
```

Authentication is via a GitHub Personal Access Token (PAT) or GitHub App installation token, resolved from the secrets backend at connection time. The token is never stored in the `McpServerSpec` row.

---

## Tools

| Tool | Description | Read / Write |
|---|---|---|
| `github.create_pr` | Open a pull request from the task branch | Write |
| `github.list_prs` | List open pull requests for a repository | Read |
| `github.get_pr` | Fetch details of a specific pull request | Read |
| `github.add_comment` | Add a comment to a PR or issue | Write |
| `github.search_code` | Search code across the organisation's repositories | Read |
| `github.search_issues` | Search issues and PRs across the organisation | Read |
| `github.merge_pr` | Merge a pull request | Write |

---

## Per-Role Allowlist

| Role | Allowed Tools |
|---|---|
| **Coder** | `github.create_pr` (approval-gated), `github.add_comment`, `github.search_code`, `github.search_issues`, `github.list_prs`, `github.get_pr` |
| **Planner** | `github.search_code`, `github.search_issues`, `github.list_prs`, `github.get_pr` |
| **Tester** | `github.search_code`, `github.search_issues`, `github.list_prs`, `github.get_pr` |
| **Reviewer** | `github.get_pr`, `github.add_comment`, `github.merge_pr` (approval-gated), `github.search_code`, `github.search_issues`, `github.list_prs` |

---

## Approval-Gated Operations

Two tools require HITL approval before execution:

### `github.create_pr`

Opening a PR is a public, irreversible action (the PR appears on GitHub immediately and may trigger CI, notify reviewers, etc.). The coder assembles the PR body from the delivery bundle summary and requests approval:

```
Coder → github.create_pr(title, body, head, base, draft=true)
  ↓
HITL: "Create PR: <title>? [approve/reject]"
  ↓
Human approves → PR created (draft)
  ↓
PR URL recorded in task record
```

Draft PRs are used by default so the human can review before marking ready for review.

### `github.merge_pr`

Merging is the final irreversible action of the delivery loop. The reviewer calls this only after the delivery bundle has been assembled and the human has approved the bundle:

```
Reviewer → github.merge_pr(prNumber, mergeMethod="squash")
  ↓
HITL: "Merge PR #<n> into <base>? [approve/reject]"
  ↓
Human approves → merge executed
  ↓
Task status → completed
```

---

## Authentication

GitHub PAT is stored in the secrets backend under the secret name `github-pat` (configurable per tenant). The MCP client resolves this at connection time and includes it in the `Authorization: Bearer <token>` header for all HTTP requests to the GitHub MCP server.

For GitHub App authentication (recommended for organisation-wide access), the secrets backend holds the App private key and installation ID. The MCP server handles token exchange internally.

---

## Knowledge Retrieval Delegation

The **Knowledge Retrieval MCP** server does **not** implement its own GitHub search adapter. Instead, when its `knowledge.search` tool receives a request with `sources: ["github"]`, it delegates to the GitHub MCP server:

```
knowledge.search(query, sources=["github"], topK=10)
  ↓
Knowledge Retrieval MCP adapter
  ↓
github.search_code(query, perPage=5)   [parallel]
github.search_issues(query, perPage=5) [parallel]
  ↓
Results normalized to KnowledgeHit[]
  ↓
Merged into rank-fusion result set
```

This avoids duplicating GitHub API client code and ensures that GitHub search respects the same auth token, rate limits, and allowlist configuration as all other GitHub tool calls. See [knowledge.md](knowledge.md) for the full Knowledge Retrieval MCP design.

---

## PR Body Template

When the coder calls `github.create_pr`, the orchestrator pre-populates the PR body from the delivery bundle:

```markdown
## Summary

{delivery_bundle.changeSummary}

## Changes

{delivery_bundle.detectChanges}

## Impact Radius

{delivery_bundle.impactRadius}

## Test Coverage

{delivery_bundle.testCoverage}

## Knowledge Sources Used

{knowledgeHits.map(h => `- [${h.title}](${h.url}) (${h.source})`).join('\n')}

---
*Generated by Agent Studio task {taskId} — {taskBranch}*
```

---

## Config Snippet

```yaml
# config/mcp-servers.d/github.yaml

name: github
version: "^1.0.0"
source:
  kind: http
  # GitHub-maintained MCP server endpoint, or self-hosted
  # package: "ghcr.io/github/github-mcp-server:latest"  # if docker
url: "https://api.github.com/mcp"    # or self-hosted endpoint URL
transport: streamable-http
env:
  - name: GITHUB_PERSONAL_ACCESS_TOKEN
    valueFrom:
      secret: github-pat
  # For GitHub App auth instead of PAT:
  # - name: GITHUB_APP_ID
  #   valueFrom: { secret: github-app-id }
  # - name: GITHUB_APP_PRIVATE_KEY
  #   valueFrom: { secret: github-app-private-key }
  # - name: GITHUB_APP_INSTALLATION_ID
  #   valueFrom: { secret: github-app-installation-id }
healthcheck:
  tool: github.list_prs
  intervalMs: 60000
  timeoutMs: 10000
retries:
  maxAttempts: 3
  backoffMs: 2000
allowlist:
  planner:
    - "github.search_code"
    - "github.search_issues"
    - "github.list_prs"
    - "github.get_pr"
  coder:
    - "github.create_pr"
    - "github.add_comment"
    - "github.search_code"
    - "github.search_issues"
    - "github.list_prs"
    - "github.get_pr"
  tester:
    - "github.search_code"
    - "github.search_issues"
    - "github.list_prs"
    - "github.get_pr"
  reviewer:
    - "github.get_pr"
    - "github.add_comment"
    - "github.merge_pr"
    - "github.search_code"
    - "github.search_issues"
    - "github.list_prs"
approvalRequired:
  - github.create_pr
  - github.merge_pr
enabled: true
```

---

## Forge Substitution

To use GitLab or Bitbucket instead of GitHub, register a compatible MCP server under the same `name: github` entry. The allowlist, approval rules, and agent tool calls remain unchanged. Only the `source`, `url`, and `env` sections differ:

```yaml
# GitLab variant
name: github         # keep the same name — agents call github.create_pr regardless
version: "^1.0.0"
source:
  kind: http
url: "https://gitlab.internal.example.com/mcp"
transport: streamable-http
env:
  - name: GITLAB_TOKEN
    valueFrom:
      secret: gitlab-pat
# ... rest identical to GitHub config
```

---

## Rate Limiting

The GitHub API enforces per-token rate limits (5000 requests/hour for PAT; higher for GitHub App). The MCP client's observability log records every tool call with latency and result status. If the GitHub MCP server returns a `429 Too Many Requests`, the MCP client applies the configured retry backoff and emits a `tool_rate_limited` warning event. The orchestrator does not automatically slow down dispatching — it relies on the MCP client retry to absorb transient rate limits. If rate limiting is severe, the operator should switch to GitHub App authentication, which has higher per-installation limits.

# WMS — Enterprise WMS MCP Server Integration

## Overview

The user's enterprise Warehouse Management System (WMS) already ships its own MCP server. Agent Studio is a **pure client** of that server — it reads WMS configurations and source artefacts, and (with HITL approval) updates them. No WMS server code is embedded in or modified by Agent Studio.

The exact tool names, argument schemas, and capabilities of the WMS MCP server are determined by the server's published manifest. The illustrative names in this document (`wms.read_config`, `wms.update_config`, `wms.read_source`, `wms.apply_patch`) must be verified and finalized against the real server manifest before integration. The `McpServerSpec` allowlist should list only tools that actually appear in that manifest.

---

## Transport

The transport is **configured by the user's existing server**. Agent Studio accepts any of the three standard MCP transports:

| Transport | When to use |
|---|---|
| `streamable-http` | The user's WMS MCP server is already running as a network service (most common for enterprise servers) |
| `sse` | Legacy HTTP streaming endpoint |
| `stdio` | The WMS server can be invoked as a local binary or script (rare; typically only in dev/test environments) |

The `McpServerSpec` `url` field points to the user's existing server endpoint. Agent Studio does not start or manage the WMS server process — it only connects to it.

---

## Tools

> **Disclaimer:** The names below are illustrative. The canonical list is the tool manifest advertised by the user's WMS MCP server. Finalize against that manifest before implementing.

| Tool | Description | Roles Allowed | Approval-Gated? |
|---|---|---|---|
| `wms.read_config` | Read a WMS configuration object by name or path | coder, planner, reviewer, tester | No |
| `wms.update_config` | Update a WMS configuration field or object | coder only | **Yes — HITL required** |
| `wms.read_source` | Read WMS source code or module definition | coder, planner, reviewer, tester | No |
| `wms.apply_patch` | Apply a structured patch (diff) to a WMS source module | coder only | **Yes — HITL required** |

Any additional tools advertised by the WMS server manifest that are not listed in the `allowlist` section of the `McpServerSpec` default to **DENIED** for all roles. This is the standard upgrade-safety behaviour of the MCP Registry.

---

## Per-Role Allowlist

```
Planner   → wms.read_config, wms.read_source
Coder     → wms.read_config, wms.update_config, wms.read_source, wms.apply_patch
Tester    → wms.read_config, wms.read_source
Reviewer  → wms.read_config, wms.read_source
```

The coder is the only role allowed to issue write calls. All write calls go through the HITL approval gate before the MCP client forwards them to the WMS server. Planner and reviewer have read-only access so they can reason about WMS state without making changes.

---

## Approval-Gated Writes

Any call to `wms.update_config` or `wms.apply_patch` triggers the HITL primitive:

```
Coder → calls wms.update_config(args)
  ↓
MCP client intercepts (approvalRequired=true)
  ↓
hitl.question event emitted to orchestrator
  ↓
Orchestrator pauses the task run
  ↓
Notification sent to VS Code extension + web UI
  ↓
Human reviews: tool name, arguments, risk context
  ↓
  ├── APPROVE → MCP client forwards call to WMS server → result returned to Coder
  └── REJECT  → ToolRejectedError returned to Coder → Coder may propose alternative
```

The approval interaction — question schema, answer schema, actor recording — is the same HITL primitive used for `github.create_pr`, `github.merge_pr`, and `claude_code.spawn_worker`. See `docs/02-components/human-in-the-loop.md` for the full contract.

Every approval (and rejection) is appended to the task's `audit_log` with: actor identity, timestamp, tool name, full argument snapshot, and the human's stated reason (optional free-text field).

---

## Referencing the User's Server Endpoint

The user supplies their WMS MCP server endpoint and authentication credentials when registering Agent Studio for their tenant. These are stored in the `mcp_server_registrations` table as a `McpServerSpec` with secrets referenced by name from the secrets backend — never stored as plaintext.

The `McpServerSpec.url` field holds the server base URL. The `McpServerSpec.env` block references the auth credential by secret name. The MCP client resolves the secret at connection time and injects it into the HTTP `Authorization` header (or as an environment variable for stdio transports).

---

## Failure Mode

If the WMS MCP server is **unreachable** when a coder or planner issues a read call:

1. The MCP client emits `tool_unavailable` tagged `server=wms`.
2. The orchestrator pauses the task run.
3. A `hitl.question` event is raised asking the human operator to either retry, provide a cached value, or cancel the WMS-dependent sub-task.
4. The task is flagged `blocked` until the human responds.

If the WMS server becomes unreachable **during a write call** (after the user approved it):

1. The MCP client returns a `ToolCallError` with the HTTP error or connection timeout detail.
2. The orchestrator pauses the coder's run and raises a HITL event: "WMS write call failed after approval — retry, skip, or cancel?"
3. The approval record is updated to include the failure outcome.

There is no automatic retry of write calls — the human must explicitly choose to retry, to ensure the operator is always aware of partial-write scenarios.

---

## Config Snippet

```yaml
# Tenant override in mcp_server_registrations table
# (or per-project agent-studio.mcp.yaml)

name: wms
version: "1.0.0"           # pin to the exact version of the user's server
source:
  kind: http               # user's server runs as a network service
url: "https://wms-mcp.internal.example.com/mcp"
transport: streamable-http
env:
  - name: WMS_AUTH_TOKEN
    valueFrom:
      secret: wms-api-token          # resolved from Vault/KMS at connection time
  - name: WMS_TENANT_ID
    valueFrom:
      secret: wms-tenant-id
healthcheck:
  tool: wms.read_config              # lightweight read as a ping
  intervalMs: 60000
  timeoutMs: 10000
retries:
  maxAttempts: 2
  backoffMs: 2000
allowlist:
  planner:  ["wms.read_config", "wms.read_source"]
  coder:    ["wms.read_config", "wms.update_config", "wms.read_source", "wms.apply_patch"]
  tester:   ["wms.read_config", "wms.read_source"]
  reviewer: ["wms.read_config", "wms.read_source"]
approvalRequired:
  - wms.update_config
  - wms.apply_patch
enabled: true
```

### stdio variant (dev/test — if the WMS server can be invoked locally)

```yaml
name: wms
version: "1.0.0"
source:
  kind: binary
  package: "/usr/local/bin/wms-mcp-server"
transport: stdio
env:
  - name: WMS_CONFIG_PATH
    value: "/etc/wms/config.yaml"
  - name: WMS_AUTH_TOKEN
    valueFrom:
      secret: wms-api-token
allowlist:
  planner:  ["wms.read_config", "wms.read_source"]
  coder:    ["wms.read_config", "wms.update_config", "wms.read_source", "wms.apply_patch"]
  tester:   ["wms.read_config", "wms.read_source"]
  reviewer: ["wms.read_config", "wms.read_source"]
approvalRequired:
  - wms.update_config
  - wms.apply_patch
enabled: true
```

---

## Sequence Diagram: WMS Write with HITL Approval

```mermaid
sequenceDiagram
    participant C as Coder Agent
    participant MC as MCP Client
    participant O as Orchestrator
    participant H as Human (VS Code / Web UI)
    participant W as WMS MCP Server

    C->>MC: wms.update_config(configId, patch)
    MC->>MC: Check allowlist → coder allowed
    MC->>MC: approvalRequired=true → intercept
    MC->>O: hitl.question { tool: "wms.update_config", args, riskContext }
    O->>O: Pause task run
    O->>H: Notify: approval required
    H->>O: POST /tasks/:id/approve { reason: "reviewed, OK" }
    O->>O: Resume task run; record approval to audit_log
    O->>MC: Forward approved call
    MC->>W: wms.update_config(configId, patch)
    W-->>MC: { success: true, configVersion: "v42" }
    MC-->>C: Tool result: { success: true, configVersion: "v42" }
    C->>C: Continue delivery loop
```

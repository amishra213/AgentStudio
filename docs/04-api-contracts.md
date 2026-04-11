# API Contracts — REST and WebSocket

Agent Studio exposes a **REST API** for task management and control, and a **WebSocket API** for real-time event streaming. Both APIs share the same authentication model (JWT), the same error envelope, and the same tenant/project/user identity propagation.

All endpoints are served by the Fastify orchestrator service over HTTPS. The base URL is `https://api.agent-studio.example.com/v1`.

---

## Authentication

All requests require a valid JWT in one of:

- **HTTP Header:** `Authorization: Bearer <token>`
- **WebSocket query param:** `wss://api.agent-studio.example.com/v1/ws?token=<token>`

JWTs are short-lived (15-minute expiry) and contain the following claims:

```json
{
  "sub": "user-uuid",
  "tenantId": "tenant-uuid",
  "projectId": "project-uuid-or-null",
  "roles": ["member"],          // "member" | "admin" | "tenant-admin"
  "iat": 1712500000,
  "exp": 1712500900
}
```

Tokens are issued by the platform's OAuth PKCE flow (see `docs/06-security.md`). Silent refresh is performed by clients before expiry; a `401 Unauthorized` on a refresh attempt requires the user to re-authenticate.

---

## Common Patterns

### Pagination

List endpoints use cursor-based pagination:

```
GET /tasks?limit=25&cursor=<opaque-cursor>
```

Response includes:

```json
{
  "data": [...],
  "pagination": {
    "limit": 25,
    "nextCursor": "eyJpZCI6IjEyMyJ9",   // null if no more pages
    "hasMore": true
  }
}
```

### Error Envelope

All error responses use a consistent shape:

```json
{
  "error": {
    "code": "TASK_NOT_FOUND",            // machine-readable error code
    "message": "Task abc123 not found.", // human-readable message
    "details": {}                        // optional structured details
  }
}
```

HTTP status codes follow standard semantics:

| Code | Meaning |
|---|---|
| `200` | Success |
| `201` | Created |
| `202` | Accepted (async operation started) |
| `400` | Bad request (validation failure) |
| `401` | Unauthorized (missing or invalid JWT) |
| `403` | Forbidden (valid JWT, insufficient role) |
| `404` | Not found |
| `409` | Conflict (e.g. task already in terminal state) |
| `422` | Unprocessable entity |
| `429` | Rate limited |
| `500` | Internal server error |

### Rate Limiting Headers

All responses include:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 987
X-RateLimit-Reset: 1712501000     # Unix timestamp when the window resets
Retry-After: 13                    # seconds (only on 429 responses)
```

Rate limits are per-tenant and per-endpoint family. Defaults: 1000 requests/minute for the task family; 100 requests/minute for the MCP registry family.

---

## REST Endpoints

### `POST /tasks`

Submit a new task for autonomous delivery.

**Request:**

```json
{
  "projectId": "project-uuid",
  "requirement": "Add a configurable timeout to the WMS order processor module. Default 30s. Expose via wms_config.yaml.",
  "budgetTokens": 200000,
  "budgetWallSeconds": 1800,
  "mcpOverrides": [],            // optional: per-task McpServerSpec overrides (can only tighten, not widen)
  "skillsDir": null              // optional: override project-level SKILLs directory for this task
}
```

**Response `201 Created`:**

```json
{
  "data": {
    "id": "task-uuid",
    "projectId": "project-uuid",
    "tenantId": "tenant-uuid",
    "status": "not_started",
    "requirement": "Add a configurable timeout...",
    "createdAt": "2026-04-11T09:00:00Z",
    "updatedAt": "2026-04-11T09:00:00Z",
    "budgetTokens": 200000,
    "budgetWallSeconds": 1800,
    "checkpointId": null
  }
}
```

---

### `GET /tasks/:id`

Retrieve the current state of a task.

**Response `200 OK`:**

```json
{
  "data": {
    "id": "task-uuid",
    "projectId": "project-uuid",
    "tenantId": "tenant-uuid",
    "status": "in_progress",
    "requirement": "Add a configurable timeout...",
    "createdAt": "2026-04-11T09:00:00Z",
    "updatedAt": "2026-04-11T09:01:30Z",
    "budgetTokens": 200000,
    "budgetWallSeconds": 1800,
    "checkpointId": "checkpoint-uuid",
    "currentRole": "coder",
    "costTokensUsed": 43210,
    "wallSecondsElapsed": 90
  }
}
```

---

### `GET /tasks/:id/events`

Retrieve the event history for a task. Paginated.

**Query params:** `limit` (default 50), `cursor`, `eventType` (optional filter)

**Response `200 OK`:**

```json
{
  "data": [
    {
      "id": "event-uuid",
      "taskId": "task-uuid",
      "taskRunId": "run-uuid",
      "eventType": "mcp.tool_called",
      "payload": {
        "server": "git",
        "tool": "git.commit",
        "args": { "message": "fix: add timeout to WMS order processor" },
        "latencyMs": 234,
        "resultStatus": "success"
      },
      "createdAt": "2026-04-11T09:01:15Z"
    }
  ],
  "pagination": {
    "limit": 50,
    "nextCursor": "eyJpZCI6Ijc4OSJ9",
    "hasMore": true
  }
}
```

---

### `POST /tasks/:id/pause`

Pause a running task after the current role completes its current atomic operation. The task transitions to `blocked`.

**Request body:** `{}` (no body required) or `{ "reason": "operator override" }`

**Response `202 Accepted`:**

```json
{
  "data": {
    "taskId": "task-uuid",
    "status": "blocked",
    "message": "Task pause requested. Will pause after current operation completes."
  }
}
```

---

### `POST /tasks/:id/resume`

Resume a paused or blocked task.

**Request body:** `{}` or `{ "fromCheckpointId": "checkpoint-uuid" }` (optional rollback to checkpoint before resume)

**Response `202 Accepted`:**

```json
{
  "data": {
    "taskId": "task-uuid",
    "status": "in_progress",
    "message": "Task resumed."
  }
}
```

---

### `POST /tasks/:id/inject`

Inject a human message or additional context into a running or paused task. The injected content is made available to the currently active role on its next tool-use iteration.

**Request body:**

```json
{
  "content": "The WMS config uses TOML format, not YAML. Please update the parser accordingly.",
  "role": "coder"   // optional: target role (defaults to currently active role)
}
```

**Response `202 Accepted`:**

```json
{
  "data": {
    "taskId": "task-uuid",
    "injectedAt": "2026-04-11T09:05:00Z",
    "message": "Context injected into task. The active role will receive it on its next iteration."
  }
}
```

---

### `POST /tasks/:id/approve`

Approve a pending HITL request (tool call approval or clarification answer).

**Request body:**

```json
{
  "hitlRequestId": "hitl-uuid",
  "answer": { "approved": true },    // or { "value": "30" } for clarification answers
  "reason": "Reviewed the patch — looks correct."
}
```

**Response `200 OK`:**

```json
{
  "data": {
    "hitlRequestId": "hitl-uuid",
    "taskId": "task-uuid",
    "answeredAt": "2026-04-11T09:06:00Z",
    "actor": "user@example.com",
    "approved": true
  }
}
```

---

### `POST /tasks/:id/reject`

Reject a pending HITL request.

**Request body:**

```json
{
  "hitlRequestId": "hitl-uuid",
  "reason": "The patch modifies the wrong config section."
}
```

**Response `200 OK`:**

```json
{
  "data": {
    "hitlRequestId": "hitl-uuid",
    "taskId": "task-uuid",
    "answeredAt": "2026-04-11T09:06:30Z",
    "actor": "user@example.com",
    "approved": false,
    "reason": "The patch modifies the wrong config section."
  }
}
```

---

### `POST /tasks/:id/cancel`

Cancel a running or paused task. Terminals immediately; in-flight MCP calls are interrupted.

**Request body:** `{}` or `{ "reason": "requirements changed" }`

**Response `202 Accepted`:**

```json
{
  "data": {
    "taskId": "task-uuid",
    "status": "cancelled",
    "cancelledAt": "2026-04-11T09:10:00Z"
  }
}
```

---

### `POST /tasks/:id/branch`

Create a named branch of a task's current state. The branch is a new task that starts from the current checkpoint of the source task. The source task continues unchanged.

**Request body:**

```json
{
  "branchName": "try-different-approach",
  "requirement": "Add a configurable timeout using environment variables instead of config file.",
  "fromCheckpointId": "checkpoint-uuid"   // optional; defaults to current checkpoint
}
```

**Response `201 Created`:**

```json
{
  "data": {
    "branchedTaskId": "new-task-uuid",
    "sourceTaskId": "task-uuid",
    "fromCheckpointId": "checkpoint-uuid",
    "status": "not_started"
  }
}
```

---

### `POST /tasks/:id/rollback`

Roll back a task to a previous checkpoint. The task is paused, its state is restored to the checkpoint, and the workspace git ref is reset. Any work after the checkpoint is discarded.

**Request body:**

```json
{
  "toCheckpointId": "checkpoint-uuid",
  "reason": "The coder took a wrong approach — rolling back to post-planning state."
}
```

**Response `202 Accepted`:**

```json
{
  "data": {
    "taskId": "task-uuid",
    "rolledBackToCheckpointId": "checkpoint-uuid",
    "status": "blocked",
    "message": "Task rolled back. Resume when ready."
  }
}
```

---

### `GET /mcp/servers`

List all MCP servers registered for the current tenant (tenant overrides + platform defaults).

**Response `200 OK`:**

```json
{
  "data": [
    {
      "name": "ruflo",
      "version": "^0.3.0",
      "transport": "streamable-http",
      "enabled": true,
      "health": "healthy",
      "lastHealthCheckAt": "2026-04-11T09:00:00Z",
      "toolCount": 4,
      "source": "platform-default"   // "platform-default" | "project-yaml" | "tenant-override"
    }
  ],
  "pagination": { "limit": 50, "nextCursor": null, "hasMore": false }
}
```

---

### `POST /mcp/servers`

Register a new MCP server (tenant override). Requires `tenant-admin` role.

**Request body:** A full `McpServerSpec` object (see `docs/02-integrations/README.md` for schema).

**Response `201 Created`:**

```json
{
  "data": {
    "id": "registration-uuid",
    "name": "my-custom-server",
    "version": "1.0.0",
    "enabled": true,
    "createdAt": "2026-04-11T09:15:00Z"
  }
}
```

---

### `DELETE /mcp/servers/:name`

Remove a tenant override MCP registration. Requires `tenant-admin` role. Platform defaults cannot be deleted (only disabled).

**Response `200 OK`:**

```json
{
  "data": {
    "name": "my-custom-server",
    "removedAt": "2026-04-11T09:20:00Z"
  }
}
```

---

### `GET /health`

Health check endpoint. Returns platform health and the status of all MCP servers.

**Response `200 OK`:**

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime": 3600,
  "mcpServers": {
    "ruflo": "healthy",
    "git": "healthy",
    "github": "healthy",
    "playwright": "healthy",
    "filesystem": "healthy",
    "fetch": "healthy",
    "code-review-graph": "healthy",
    "claude-code-worker": "healthy",
    "knowledge": "healthy",
    "wms": "degraded"
  },
  "db": "healthy",
  "redis": "healthy"
}
```

Returns `503 Service Unavailable` if `db` or `redis` is unhealthy.

---

## WebSocket API

### Connection

```
wss://api.agent-studio.example.com/v1/ws?token=<jwt>
```

Or with header auth (supported by some WebSocket clients):

```
GET /v1/ws
Upgrade: websocket
Authorization: Bearer <jwt>
```

After the handshake, the client sends a **subscribe** message to begin receiving events:

```json
{
  "type": "subscribe",
  "taskId": "task-uuid"
}
```

Multiple tasks can be subscribed in a single connection. The server responds with a `subscribed` acknowledgement:

```json
{
  "type": "subscribed",
  "taskId": "task-uuid"
}
```

### Message Envelope

Every message (client → server and server → client) uses this envelope:

```typescript
interface WsMessage {
  type: string;           // event type (see catalogue below)
  taskId: string | null;  // null for connection-level events
  payload: unknown;       // event-specific payload
  sequenceNumber?: number; // server-assigned; monotonically increasing per task
  timestamp: string;      // ISO 8601 UTC
}
```

### Server → Client Event Types

| `type` | `payload` | Description |
|---|---|---|
| `task.state_changed` | `{ from: TaskStatus, to: TaskStatus, reason?: string }` | Task lifecycle transition |
| `agent.message` | `{ role: AgentRole, content: string, runId: string }` | Agent produced a message visible to the operator |
| `mcp.tool_called` | `{ server: string, tool: string, latencyMs: number, resultStatus: string }` | MCP tool invoked (without sensitive args/results) |
| `hitl.question` | `{ hitlRequestId: string, question: string, schema: object, toolName?: string }` | Human input required |
| `hitl.resolved` | `{ hitlRequestId: string, answeredAt: string, actor: string, approved?: boolean }` | Human input provided |
| `task.delivery_bundle_ready` | `{ bundleRef: string, prUrl?: string, impactRadius: string[], testCoverage: object }` | Delivery bundle assembled and ready for review |
| `task.error` | `{ code: string, message: string }` | Non-fatal error (e.g. MCP server degraded) |
| `ping` | `{}` | Keepalive — client should respond with `pong` |

### Client → Server Message Types

| `type` | `payload` | Description |
|---|---|---|
| `subscribe` | `{ taskId: string }` | Subscribe to events for a task |
| `unsubscribe` | `{ taskId: string }` | Unsubscribe from a task |
| `pong` | `{}` | Keepalive response to `ping` |

Steering operations (pause, resume, approve, etc.) use the REST API, not the WebSocket. The WebSocket is receive-only for task events.

### Reconnection

Clients should reconnect with exponential backoff on disconnect. On reconnection, the client can replay missed events by:

1. Calling `GET /tasks/:id/events?cursor=<last-seen-event-id>` to retrieve events since disconnect.
2. Re-subscribing on the new WebSocket connection.

The `sequenceNumber` field on each message allows clients to detect gaps.

---

## API Versioning

The API is versioned at the URL prefix level (`/v1`). Breaking changes bump the version. Non-breaking additions (new optional fields, new event types) are made within the same version. The `v1` API will be supported for at least 12 months after `v2` is released.

Clients should treat unknown event types and unknown JSON fields gracefully (ignore rather than error), as new event types may be added within a version.

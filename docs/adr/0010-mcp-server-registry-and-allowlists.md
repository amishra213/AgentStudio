# ADR-0010: MCP Server Registry with Typed McpServerSpec and Per-Role Tool Allowlists

**Status:** Accepted  
**Date:** 2026-04-11  
**Deciders:** Agent Studio Architecture Team

## Context

Agent Studio connects to a fleet of MCP servers: Ruflo, code-review-graph, Git, GitHub, Playwright, Filesystem, Fetch, WMS, the internal Knowledge Retrieval server, and the internal ClaudeCode Worker server. Without a governance layer, any agent role could call any tool on any server — a Planner could call `git.push`; a Tester could call `wms.update_config`; a Coder could call `playwright.*` tools it has no reason to access. Beyond correctness concerns, this is a security risk: a compromised or misbehaving agent in one role could affect other tenants' data, push unauthorized code, or trigger expensive browser automation outside the controlled test loop.

There are two common approaches to controlling tool access: (1) building role-awareness into each MCP server (requiring every server to know about Agent Studio's roles), and (2) controlling access on the client side via a registry that maintains allowlists per role. Approach 1 is not viable: external servers (Ruflo, code-review-graph, GitHub, Playwright) are upstream distributions that Agent Studio does not control, and adding Agent Studio role semantics to them would require forks (rejected in ADR-0009 and ADR-0006). Approach 2 keeps all access control logic inside Agent Studio's `mcp-client` package, where it can be tested, audited, and updated without touching any external server.

The allowlist must be enforced at the point of tool invocation, not just at prompt construction. If allowlists are only used to decide which tools to describe to the LLM in the system prompt, a sufficiently creative or adversarial model generation could still construct a tool-call JSON payload for a disallowed tool. The `mcp-client` package's dispatch layer must reject disallowed tool calls at the protocol level, before forwarding them to the server, regardless of how the call was generated.

An additional requirement is the approval gate: certain high-consequence tools (git push, github merge, wms write operations, claude_code spawn_worker with bypassPermissions) must require explicit human approval before the MCP client forwards them to the server. This approval mechanism is the HITL primitive for tool-call-level decisions, distinct from the task-level HITL for clarification questions.

## Decision

All MCP servers are declared in a typed `McpServerSpec` registry. Every spec entry includes a `allowlist` map from role name to a list of glob patterns matching permitted tool names (e.g. `"playwright.*"`, `"memory.search"`, `"git.{clone,status,diff,log}"`). The `mcp-client` package enforces allowlists at dispatch time: when an agent role requests a tool call, the client checks the tool name against the role's allowlist for that server before forwarding the call. A tool name that does not match any pattern in the role's allowlist is rejected with a structured `tool_denied` error event, which the orchestrator logs and may surface to HITL.

Per-task overrides can tighten allowlists (remove tools from a role's permitted set for a specific task) but can never widen them (add tools not already in the role's base allowlist). This asymmetry is enforced in the override-merge logic: overrides are computed as the intersection of the base allowlist and the override set, never the union. Any tool flagged `requiresApproval: true` in the `McpServerSpec` causes the `mcp-client` to pause before forwarding the call, emit a `tool_approval_requested` event to the orchestrator, wait for a human approval signal, and only forward the call after receiving it. Rejections are logged and the tool call returns a `tool_approval_denied` result to the agent.

Example role boundaries enforced by default allowlists: Planner gets read-only access to `graph.*`, `memory.search`, `knowledge.search` — never `git.*` write tools or `claude_code.*`; Coder gets `git.*` (all), `graph.{update,detect_changes,impact_radius,callers_of,callees_of}`, `memory.*`, `fs.*`, `claude_code.{run,spawn_worker,status,cancel,stream_events}`; Tester gets `playwright.*`, `graph.{tests_for,impact_radius}`, `memory.search`, `knowledge.search`, `claude_code.run` (spec generation only); Reviewer gets all `graph.*` (delivery bundle), `github.{create_pr,add_comment}` (approval-gated), `memory.*`, `knowledge.search`.

## Consequences

### Positive
- Role boundaries are enforced at the protocol level, not just at prompt construction — a disallowed tool call is blocked regardless of how the LLM generated it.
- The approval gate for high-consequence tools (push, merge, WMS writes, sandboxed worker spawn) creates an auditable HITL checkpoint at the precise point where irreversible actions occur.
- Allowlists are declared in config alongside server specs, making the full permission surface inspectable without reading agent prompt code — operators can audit "what can the Coder actually do?" from a single YAML file.
- Per-task tightening enables read-only audit tasks, sandbox exploration tasks, and other restricted modes without changing the base role configuration.
- Every denied tool call is logged; repeated denials from a specific role may indicate a prompt engineering issue or an adversarial input pattern, both of which are surfaced in the audit dashboard.

### Negative / Trade-offs
- Glob-pattern allowlists require careful authoring; overly broad patterns (e.g. `"*"`) defeat the purpose, and overly narrow patterns may block legitimate tool calls. Initial patterns must be validated against real agent runs.
- Per-task override logic (intersection, never union) may surprise operators who expect overrides to be additive; documentation and UI affordances must make the asymmetry explicit.
- The approval gate introduces latency and human availability as dependencies for approval-gated tool calls; tasks that require many such calls (e.g. multiple git pushes in a refactor) will be slow if approvals are manual. Batch approval UX mitigates this for known-safe sequences.
- Maintaining allowlists across server upgrades (new tools appearing in upgraded manifests) requires the allowlist-diff check on every upgrade (ADR-0011); operators must review and explicitly grant new tools.

### Neutral
- The `McpServerSpec` schema is defined in `shared-types` and validated at registry load time with Zod; malformed specs are rejected at startup, not at tool-call time.
- The `tool_denied` and `tool_approval_requested` events are first-class event types in the task event stream, visible in the Web UI's MCP call log alongside successful tool calls.

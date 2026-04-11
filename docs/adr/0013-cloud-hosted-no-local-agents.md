# ADR-0013: Cloud-Hosted Deployment — Agents Never Run Locally

**Status:** Accepted  
**Date:** 2026-04-11  
**Deciders:** Agent Studio Architecture Team

## Context

When designing a developer tool that integrates with VS Code and performs autonomous coding work, a natural question is where the agent processes run: on the developer's local machine (where the code already lives and where the developer's credentials are available), or on a central hosted service. Local execution has an intuitive appeal — no latency from shipping code to a remote service, no need to manage a cloud deployment, and the agent runs with the same file system access as the developer. Several existing agent coding tools (including Claude Code in its default mode) operate locally.

However, Agent Studio is not a personal productivity tool — it is a platform designed to serve multiple users, multiple projects, and multiple tenants concurrently, with shared memory (Ruflo), shared code analysis (code-review-graph), a shared MCP server fleet, and organizational-level governance (HITL approvals, audit logs, cost ceilings). Local execution of agents is fundamentally incompatible with these requirements. If agents run on each developer's machine, there is no shared Ruflo instance across sessions — memory is siloed per developer. There is no shared code-review-graph instance — each machine would need its own persistent graph, and the graph would not be accessible to other team members reviewing the Delivery Bundle. There is no central MCP server fleet — each machine would need to spawn and manage its own fleet of MCP server processes, and the fleet configuration could diverge across machines.

Security is the second major concern. Local agent execution means the agent process runs with the developer's credentials and file system access, without any tenant-scoped isolation. An agent that writes to the wrong path, executes code that modifies system files, or exfiltrates data via the Fetch MCP server would have the full access rights of the developer's shell. The Docker sandboxing model for Playwright and Claude Code workers (ADRs 0007, 0012) is only meaningful if the Docker daemon is controlled by the platform operator, not the developer's laptop. Multi-tenancy — the requirement to isolate one tenant's tasks, memory, and data from another — is simply not achievable in a local-execution model without building a local isolation layer that would essentially recreate a cloud deployment on each machine.

## Decision

Agent Studio is deployed as a hosted service; all agent processes (Planner, Coder, Tester, Reviewer, and all Claude Code workers) run in the hosted environment. Users never run agent code locally. The VS Code extension and the Next.js Web UI are both thin clients — they open a WebSocket connection to the hosted orchestrator, display streamed events, and send user input (task submissions, HITL approvals, steering commands). Neither client executes any agent logic. The VS Code extension and Web UI share the same session token and the same WebSocket event stream, so switching between IDE and browser is seamless and stateless from the platform's perspective.

The hosted deployment topology places the following components centrally: stateless Fastify orchestrator pods behind a load balancer (horizontally scalable, reading/writing state in managed PostgreSQL); Redis (BullMQ task queue and WebSocket pub/sub fan-out); a central Ruflo service with a persistent volume (shared across all orchestrator replicas for cross-session, cross-replica memory); code-review-graph sidecar containers per tenant-project (with persistent SQLite volumes); ephemeral Kubernetes Jobs for sandboxed Claude Code workers (per-task containers with CPU/memory/time limits, killed at TTL); stdio MCP servers spawned as child processes of the orchestrator pods (Git, Filesystem, Fetch); HTTP/SSE MCP servers running as central sidecars (GitHub, Playwright, Ruflo, code-review-graph); secrets managed via HashiCorp Vault or cloud KMS, resolved at spawn time, never persisted or logged; and the Next.js Web UI deployed separately behind the same load balancer with CDN.

Every request carries a tenant/project/user triple on its JWT. DB rows are tenant-scoped; MCP tool calls inherit the tenant; secret lookups are tenant-keyed; Ruflo scopes and code-review-graph workspaces are per-tenant-per-project; cost ceilings and token quotas are enforced per tenant before any Claude Code dispatch. The hosted model is the only model in which these multi-tenancy guarantees can be provided consistently.

## Consequences

### Positive
- Shared Ruflo instance across all orchestrator replicas ensures that memory written during one task run is available to subsequent runs by any user on any replica — cross-session learning works as intended.
- Shared code-review-graph sidecar per tenant-project means all team members reviewing the Delivery Bundle in the Web UI see the same graph, the same wiki, and the same impact visualization.
- Docker sandboxing of Claude Code workers and Playwright is meaningful and enforceable — the Docker daemon is under platform operator control, not the developer's.
- Centralized secrets management (Vault/KMS) means no credentials are stored on developer machines or in local config files; secrets are resolved at spawn time in the hosted environment.
- Cost ceilings, quotas, and audit logs are enforced uniformly at the hosted orchestrator — there is no mechanism for a local agent to bypass them.
- Horizontal scalability of the orchestrator is straightforward in a hosted model: add pods. In a local model, scaling would require coordination across developer machines.

### Negative / Trade-offs
- Developers working offline (no network access) cannot use Agent Studio — all agent processing requires connectivity to the hosted orchestrator. This is an explicit non-goal; Agent Studio targets professional development environments where connectivity is assumed.
- Shipping large code repositories to the hosted environment for agent analysis introduces latency and bandwidth cost. This is mitigated by the code-review-graph's token-efficient code understanding (6.8x–49x token reduction) and by the Git MCP server's ability to clone shallowly from the hosted environment's perspective.
- The hosted deployment introduces operational concerns (Kubernetes cluster management, managed database operation, Vault management) that are absent in a local-execution tool. These are accepted as the cost of providing a multi-tenant, enterprise-grade platform.
- Latency between the developer's VS Code extension and the hosted orchestrator adds a small delay to HITL interactions (approve/reject tool calls). In practice, this is negligible (sub-100ms on a well-routed connection) compared to the agent turn time.

### Neutral
- The VS Code extension is a thin WebSocket client with no agent logic; its release cadence is independent of the orchestrator's. Extension updates are published to the VS Code Marketplace and do not require orchestrator deployments.
- The deployment is described as "the customer's cloud" — Agent Studio can be self-hosted on AWS, GCP, Azure, or on-premises Kubernetes. It is not exclusively a SaaS offering; the architecture is the same in all deployment targets.
- Local development of Agent Studio itself (for contributors to the platform) uses a local orchestrator process, local Docker for sandboxed workers, and a local Ruflo instance — this is a developer-only configuration, not a supported end-user mode.

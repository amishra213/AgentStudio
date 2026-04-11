# Hosting and Deployment

Agent Studio is designed from the ground up as a **centrally hosted platform** — users never run agents locally. They connect to a hosted Orchestrator from VS Code or a browser. This document covers the cloud topology, multi-tenancy model, and the three deployment footprints (dev, staging, production).

ADR-0013 records the cloud-first / no-local-agents decision.

---

## Deployment layer table

| Layer | Deployment model | Notes |
|---|---|---|
| **Orchestrator service** | Stateless Fastify pods behind a load balancer; horizontally scalable | Reads/writes state in Postgres; subscribes to Redis pub/sub for live WebSocket fan-out |
| **Postgres** | Managed (AWS RDS / GCP Cloud SQL / Azure DB for PostgreSQL) | Holds tasks, runs, events, MCP registry, audit log, tenant/project rows; pgvector extension for optional local embeddings |
| **Redis** | Managed (AWS ElastiCache / GCP Memorystore / Azure Cache for Redis) | BullMQ task queue + pub/sub for WebSocket fan-out across Orchestrator replicas |
| **Ruflo** | Central sidecar service with a persistent volume | One instance per deployment, shared across Orchestrator replicas so memory is tenant-global; pinned version |
| **`code-review-graph`** | Sidecar container, one per tenant-project | Python distribution; SQLite graph on a persistent volume; pinned version via MCP Registry |
| **Claude Code sandboxed workers** | Ephemeral Kubernetes Jobs on a dedicated worker node pool | Per-task containers; overlayFS writes; scoped MCP config; CPU/mem/time limits; killed at TTL |
| **Stdio MCP servers** (Git, Filesystem, Fetch, Knowledge, ClaudeCode Worker) | Spawned per Orchestrator pod; managed by MCP client | Short-lived child processes; one per connected tenant per server type |
| **HTTP/SSE MCP servers** (GitHub, central Ruflo, central code-review-graph) | Central sidecars or standalone services; referenced by URL from MCP Registry | Shared across Orchestrator replicas |
| **Secrets** | HashiCorp Vault or cloud KMS (AWS Secrets Manager / GCP Secret Manager / Azure Key Vault) | Never in DB, never in config files, never in logs; resolved at server-spawn time only |
| **Web UI (Next.js)** | Separate deployment behind the same load balancer and CDN | Talks to Orchestrator over HTTPS + WebSocket; same tenant/session model as VS Code extension |

---

## Multi-tenancy model

Every request carries a **tenant / project / user** triple on the JWT:

```typescript
interface AgentStudioJWT {
  sub: string;           // user ID
  tenantId: string;
  projectId: string;
  roles: string[];       // e.g. ['tenant-admin', 'developer']
  exp: number;
  iat: number;
}
```

Isolation is enforced at every layer:

| Layer | Isolation mechanism |
|---|---|
| **Postgres** | Every table includes a `tenant_id` column; all queries include `WHERE tenant_id = $tenantId`; Row-Level Security (RLS) policies as a second defence |
| **MCP tool calls** | MCP client passes `tenantId` in every call; servers validate it against their own access control |
| **Ruflo** | Ruflo scopes (`user/project/local`) are keyed by `tenantId + projectId`; cross-tenant reads are structurally impossible |
| **code-review-graph** | One sidecar container per tenant-project; SQLite graph file on a per-tenant-project volume |
| **Secret lookups** | All secret references are namespaced: `vault path: secrets/tenants/{tenantId}/{secretName}` |
| **Cost ceilings** | Tenant aggregate budget enforced in Postgres; per-task ceiling also enforced |
| **k8s Jobs (sandboxed workers)** | Each Job runs in the worker namespace with a per-task service account; no cross-task filesystem access |

---

## Deployment footprints

### Footprint A — Development (docker-compose)

Single-node, no Kubernetes. Intended for contributors and local demos.

```yaml
# docker-compose.yml (simplified)
services:
  orchestrator:
    image: agent-studio/orchestrator:dev
    ports: ["3001:3001"]
    environment:
      DATABASE_URL: postgres://postgres:dev@db:5432/agent_studio
      REDIS_URL: redis://redis:6379
      VAULT_ADDR: ""          # secrets from .env file in dev
    depends_on: [db, redis, ruflo]

  db:
    image: postgres:16
    volumes: [pgdata:/var/lib/postgresql/data]

  redis:
    image: redis:7-alpine

  ruflo:
    image: ghcr.io/ruvnet/ruflo:pinned
    volumes: [ruflo-data:/data]
    ports: ["8080:8080"]

  code-review-graph:
    image: ghcr.io/tirth8205/code-review-graph:pinned
    volumes: [crg-data:/data]

  web:
    image: agent-studio/web:dev
    ports: ["3000:3000"]
```

Claude Code sandboxed workers run as Docker containers spawned by the MCP client directly (no Kubernetes). SQLite is used for the graph volume. Secrets come from a `.env` file (never committed).

### Footprint B — Staging (single Kubernetes namespace)

Small worker pool, managed Postgres and Redis (cloud-provided), Vault for secrets. Used for integration testing and pre-production validation.

```
Namespace: agent-studio-staging
├── Deployment: orchestrator (2 replicas, 2 vCPU / 4 GiB each)
├── Deployment: web (2 replicas)
├── StatefulSet: ruflo (1 replica, 10 GiB PVC)
├── StatefulSet: code-review-graph (1 PVC per tenant-project)
├── External: RDS PostgreSQL (db.t3.medium)
├── External: ElastiCache Redis (cache.t3.micro)
├── External: HashiCorp Vault (shared staging instance)
└── NodePool: worker-nodes (2× c5.xlarge, auto-scaled 0–8)
```

### Footprint C — Production (HA)

```
┌─────────────────────────────────────────────────────┐
│  Load Balancer / CDN (CloudFront / Cloudflare)       │
│  - HTTPS termination, WAF, rate limiting             │
└─────────────────────────────────────────────────────┘
         │                        │
    ┌────▼────┐               ┌───▼────┐
    │  Web UI  │               │ Orch.  │
    │ (Next.js)│               │ pods   │
    │ 3+ pods  │               │ 3+ pods│
    └──────────┘               └───┬────┘
                                   │
              ┌────────────────────┼──────────────────┐
              │                    │                  │
        ┌─────▼──────┐      ┌──────▼─────┐   ┌───────▼──────┐
        │  Managed   │      │  Managed   │   │  HashiCorp   │
        │  Postgres  │      │   Redis    │   │    Vault     │
        │  (RDS HA)  │      │ (ElastiC.) │   │   (HA raft) │
        └────────────┘      └────────────┘   └──────────────┘
              │
    ┌─────────┴───────────────────┐
    │  Sidecar services           │
    │  ├── Ruflo (StatefulSet, 2r)│
    │  └── code-review-graph      │
    │      (per-tenant PVC)       │
    └─────────────────────────────┘
              │
    ┌─────────▼──────────────────────┐
    │  Worker Node Pool              │
    │  (dedicated, spot-tolerant)    │
    │  ├── Sandboxed k8s Jobs        │
    │  ├── Playwright containers     │
    │  └── Custom MCP docker servers │
    └────────────────────────────────┘
```

---

## Production deployment diagram (Mermaid)

```mermaid
graph TD
    subgraph Internet edge
        CDN[CloudFront / Cloudflare<br/>WAF + HTTPS termination]
    end

    subgraph Kubernetes cluster — system namespace
        LB[Internal Load Balancer]
        ORCH[Orchestrator pods<br/>3+ replicas<br/>Fastify + WebSocket]
        WEB[Web UI pods<br/>3+ replicas<br/>Next.js]
        RUFLO[Ruflo StatefulSet<br/>2 replicas<br/>shared across tenants]
        CRG[code-review-graph<br/>StatefulSet<br/>per-tenant-project PVC]
    end

    subgraph Kubernetes cluster — worker namespace
        WN[Worker Node Pool<br/>dedicated, spot-tolerant]
        JOBS[Sandboxed k8s Jobs<br/>per-task, ephemeral]
        PW[Playwright containers<br/>Docker-in-Docker or containerd]
    end

    subgraph Managed cloud services
        PG[(Managed Postgres<br/>RDS Multi-AZ)]
        REDIS[(Managed Redis<br/>ElastiCache cluster)]
        VAULT[HashiCorp Vault<br/>HA Raft cluster]
        S3[Object Storage<br/>S3 / GCS — reports + artifacts]
    end

    subgraph External MCP servers
        GH[GitHub MCP<br/>HTTP endpoint]
        WMS[WMS MCP server<br/>user-hosted]
    end

    CDN --> LB
    LB --> ORCH
    LB --> WEB
    ORCH <--> PG
    ORCH <--> REDIS
    ORCH --> RUFLO
    ORCH --> CRG
    ORCH -->|k8s Job API| JOBS
    JOBS --> PW
    ORCH --> VAULT
    JOBS --> VAULT
    ORCH --> GH
    ORCH --> WMS
    JOBS -->|write artifacts| S3
    ORCH -->|read artifacts| S3
    WEB -->|HTTPS + WS| ORCH
```

---

## Horizontal scaling

The Orchestrator is stateless. All state lives in Postgres and Redis. To scale horizontally:

1. Add Orchestrator pod replicas — the load balancer distributes WebSocket connections.
2. BullMQ workers on each pod compete for jobs from the shared Redis queue.
3. Redis pub/sub ensures all pods forward the correct WebSocket events to the correct connected sessions.
4. Ruflo is a central service (not per-pod) — it needs a stable hostname and a persistent volume. Use a StatefulSet with `podAntiAffinity` to spread across AZs.

Worker node pool scales independently via Kubernetes cluster autoscaler. Jobs are submitted as Kubernetes Jobs and run on whatever node has capacity.

---

## Secrets management

No secret is ever stored in:
- Any database table (not even encrypted in DB)
- Any Kubernetes ConfigMap
- Any config file committed to git
- Any log line

All secrets are stored in Vault (or cloud KMS) and resolved at runtime:

```
Vault path convention:
  secrets/tenants/{tenantId}/anthropic-api-key
  secrets/tenants/{tenantId}/github-pat
  secrets/tenants/{tenantId}/confluence-api-token
  secrets/tenants/{tenantId}/sharepoint-client-secret
  secrets/tenants/{tenantId}/wms-auth-token
  secrets/platform/ruflo-endpoint-secret
  secrets/platform/playwright-browsers-cache

Resolved by:
  - Orchestrator: at startup for long-lived secrets (e.g. DB URL)
  - MCP client: at server-spawn time for each external server's credentials
  - k8s Jobs: injected as environment variables via Vault Agent Injector or External Secrets Operator
```

Vault tokens themselves are issued via Kubernetes service account authentication (no static tokens). Job-specific tokens have a TTL equal to the job's `maxWallSeconds`.

---

## Network security

| Boundary | Control |
|---|---|
| Public internet → LB | WAF rules, TLS 1.3 only, rate limiting |
| LB → Orchestrator | mTLS (cert-manager issued) |
| Orchestrator → Postgres | Private subnet, SSL required, RDS IAM auth |
| Orchestrator → Redis | Private subnet, AUTH token, TLS |
| Orchestrator → Vault | Private subnet, k8s service account auth |
| Sandboxed k8s Jobs | Network policy: egress allowed only to Anthropic API + configured MCP endpoints; deny all ingress |
| Playwright containers | Egress allowed only to app-under-test on loopback + configured test hosts; no public internet |

---

## Observability stack

| Signal | Tool | Notes |
|---|---|---|
| Metrics | Prometheus + Grafana | Orchestrator exports `/metrics`; BullMQ job counts, latency, error rates, cost per tenant |
| Traces | OpenTelemetry → Jaeger / Tempo | Trace spans from REST request → BullMQ job → agent role → MCP calls → worker |
| Logs | Structured JSON → CloudWatch / Datadog / Splunk | All logs include `{tenantId, projectId, taskId, runId}` |
| Audit | Postgres `audit_log` + exported to log sink | Append-only; exported daily to S3 for long-term retention |
| Alerts | PagerDuty / Opsgenie | Alert on: Orchestrator pod down, BullMQ dead-letter count > 0, cost ceiling breach, Ruflo unreachable |

---

## Related components

- [Orchestrator](./orchestrator.md) — the service being deployed
- [MCP Registry](./mcp-registry.md) — server registrations stored in Postgres
- [Deep Coding Workers](./deep-coding-workers.md) — k8s Job lifecycle
- [Security](../../06-security.md) — auth, tenancy, sandbox isolation details
- [ADR-0013](../adr/0013-cloud-hosted-no-local-agents.md) — rationale for cloud-first hosting

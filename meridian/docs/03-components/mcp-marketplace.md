# Component: MCP Server Marketplace & Enablement

> Differentiator **D7** — new MCP servers enabled from a marketplace *or registered privately*,
> changing agent capability with no redeploy. Builds on
> [`02-data-model.md`](../02-data-model.md) (`McpListing`, `McpVersion`, `McpInstallation`).

---

## 1. What the Marketplace Is — and Isn't

It is a **catalog and an enablement layer**. It is not a hosting platform: MCP servers run wherever
their publisher or the customer runs them. Meridian indexes them, validates their manifests,
tracks versions and health, and governs who may call them — the same relationship a package
registry has to packages.

Two acquisition paths, both first-class:

| Path | Use | `McpListing.source` |
|---|---|---|
| **Marketplace** | Public or org-internal catalog; browsable, versioned, certified | `marketplace` |
| **Private registration** | An admin points Meridian at an MCP server directly — an internal service, a vendor server under NDA, a local stdio binary next to the harness | `private` |

Private registration matters as much as the catalog: most enterprises' highest-value tools are
internal and will never be published anywhere. A private server is never listed publicly and skips
certification, but is otherwise identical — same manifest validation, same grants, same audit.

---

## 2. The Manifest

An `McpVersion` carries the server's manifest, which Meridian validates before the server can be
enabled:

| Field | Purpose |
|---|---|
| `protocol_version` | MCP version spoken |
| `transport` | `stdio`, `streamable_http`, or `sse` |
| `endpoint` | for HTTP transports; for stdio, the command the harness runs locally |
| `tools[]` | each with name, description, JSON-Schema input, and a declared **effect class** (below) |
| `capability_tags` | how the harness finds it during routing — `["itsm","incident"]`, `["git","review"]` |
| `required_secrets[]` | secret *names* the installation must supply; never values |
| `data_egress` | what leaves the customer boundary when tools are called — required for review |
| `rate_limits` | publisher-declared limits, used for backoff |

### Effect classes

Every tool declares one, and this drives default policy:

| Class | Meaning | Default treatment |
|---|---|---|
| `read` | No state change anywhere | Grantable freely |
| `write_internal` | Changes state inside the customer's own systems | Grantable; logged |
| `write_external` | Visible outside the org (emails a customer, posts publicly, deploys) | Defaults to `requires_approval` on grant |
| `destructive` | Irreversible (delete, terminate, release funds) | Defaults to `requires_approval`; blocked entirely for `unverified` tier |

A manifest whose declared effect classes are contradicted during certification testing fails
certification. This is the mechanism that prevents "read-only integration" turning out to send
email.

---

## 3. Certification Tiers

| Tier | Requirements | Effect |
|---|---|---|
| `unverified` | Manifest schema valid | Explicit admin override to enable; `destructive` tools blocked; flagged in UI |
| `community` | Automated conformance suite passed (protocol compliance, schema honesty, error handling, timeout behaviour, effect-class verification) | Enablable by default |
| `verified` | `community` + manual review of `data_egress` and effect classes + usage track record | Featured; eligible for default grants |
| `enterprise` | `verified` + data-processing agreement and security attestation | Eligible in regulated workspaces |

Certification is **per version**, not per listing — a publisher cannot coast on an old version's
review after shipping a regressed one. Privately registered servers carry tier `private` and
inherit the customer's own trust decision.

---

## 4. Enabling a Server (D7)

Enabling creates an `McpInstallation` in the workspace:

1. Admin picks a listing + version (or registers a private server's manifest and endpoint).
2. **Version is pinned.** Upgrades are explicit, with a diff of manifest changes shown — a new
   tool or a widened effect class is not something to acquire silently.
3. Admin sets `project_scope` (which projects may use it) and supplies `secret_refs` resolved from
   the secrets backend at call time.
4. Health check runs; the installation goes `enabled`.

**Enabling does not grant anyone access.** It makes the server *available to be granted*. The
separate `McpGrant` step (see [`permissions-rbac.md`](permissions-rbac.md) §3) is what lets a
specific agent profile call it. Keeping these apart is deliberate: enabling is a procurement and
integration decision, granting is a security decision, and they are usually made by different
people at different times.

Once granted, the server is usable by the profile **on its next run** — no redeploy, no restart
(SC-4).

---

## 5. Health, Versions, and Deprecation

- Each installation is health-checked on a schedule; `degraded`/`unreachable` states surface to
  admins and are visible to the harness during routing, so it can prefer a healthy alternative.
- Publishers can mark a version deprecated with a sunset date; workspaces pinned to it get advance
  warning in the admin UI rather than a surprise failure.
- Repeated call failures from a specific installation (see
  [`agent-harness.md`](agent-harness.md) §8) auto-mark it degraded before an admin notices.

---

## 6. Trust Signals

Alongside star ratings, objective signals aggregated across workspaces that opted into anonymised
benchmarking:

- Call success rate and p95 latency
- Frequency of `denied_by_policy` (a signal the manifest over-asks)
- Median cost per call
- Handoff rate on tickets where this server was the primary tool (high rate suggests the server
  doesn't actually do what its tags claim)

Aggregates strip tenant identity — a reviewer never learns which workspace produced which data
point, preserving tenant confidentiality (G12) while keeping the signals public.

---

## 7. Billing

Metered server usage produces `CostEntry` rows of kind `mcp_call`, tied to the `ExecutionLeg` and
therefore to a ticket, a sprint/phase, and an ROI rollup. Settlement between workspace and
publisher runs through a third-party payments provider; Meridian reports usage and never custodies
funds.

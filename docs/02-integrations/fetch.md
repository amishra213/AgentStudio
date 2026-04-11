# Fetch MCP — URL to Markdown

## Overview

The Fetch MCP server (`@modelcontextprotocol/server-fetch`) retrieves the content of a URL and returns it as Markdown. It is the lowest-level building block for external content retrieval in Agent Studio — used primarily by the Knowledge Retrieval MCP to expand search results into full page content, and available to all roles for ad-hoc reference lookups.

The Fetch MCP is **read-only** and enforces a **domain allowlist** to prevent credential exfiltration or data leakage via crafted URLs.

---

## Transport

**`stdio`** — spawned as a child process per orchestrator pod. No persistent state.

```
Orchestrator pod → spawns → npx @modelcontextprotocol/server-fetch
```

---

## Tools

| Tool | Description |
|---|---|
| `fetch.url` | Fetch the content of a URL and return it as Markdown. The server follows redirects, strips navigation/ads, and returns the main content. |

This is the server's only tool. There is no `fetch.post`, `fetch.upload`, or any write variant — the server is strictly GET-only.

---

## Per-Role Allowlist

All four roles are allowed to call `fetch.url`. Fetch is a read-only operation and does not require role differentiation:

```yaml
allowlist:
  planner:  ["fetch.url"]
  coder:    ["fetch.url"]
  tester:   ["fetch.url"]
  reviewer: ["fetch.url"]
```

---

## Domain Allowlist

The domain allowlist is the primary security control for the Fetch MCP. It prevents agents from fetching URLs that could:

- Exfiltrate secrets via DNS or HTTP request contents
- Fetch malicious content from attacker-controlled servers
- Bypass network egress controls by routing traffic through the Fetch server

The allowlist is configured in the `McpServerSpec` as an environment variable and enforced by the Fetch MCP server process itself. Any request to a domain not on the allowlist is rejected before the HTTP call is made.

### Default allowlist

The platform ships with a permissive-but-bounded default allowlist covering common reference sources:

```
# Public documentation and references
docs.anthropic.com
developer.mozilla.org
nodejs.org
npmjs.com
pypi.org
pkg.go.dev
crates.io
docs.python.org
learn.microsoft.com
cloud.google.com
docs.aws.amazon.com

# Public knowledge bases
stackoverflow.com
github.com                 # public repositories only
raw.githubusercontent.com

# Search engine result pages (used by Knowledge Retrieval web adapter)
# Note: actual web search is done via Tavily/Brave/SerpAPI APIs, not raw fetch
```

### Tenant-specific additions

Operators can extend the allowlist with internal domains (Confluence, SharePoint, internal wikis) via the `McpServerSpec` tenant override in the MCP registry:

```yaml
env:
  - name: FETCH_DOMAIN_ALLOWLIST
    value: "docs.anthropic.com,developer.mozilla.org,wiki.internal.example.com,confluence.internal.example.com"
```

### Explicitly blocked categories

Regardless of allowlist configuration, the following are never permitted:

- `169.254.0.0/16` (AWS EC2 IMDS — prevents metadata endpoint access)
- `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` (private IP ranges — prevents SSRF against internal services not exposed via MCP)
- `localhost`, `127.0.0.1`, `::1` (loopback)

These blocks are enforced at the network level (egress firewall rules on the orchestrator pod) in addition to the Fetch MCP server's allowlist, providing defence-in-depth.

---

## How Knowledge Retrieval Uses Fetch

The Knowledge Retrieval MCP's web adapter calls `fetch.url` to expand search results:

```
knowledge.search(query, sources=["web"])
  ↓
Web adapter: Tavily/Brave/SerpAPI API → returns { title, url, snippet }[]
  ↓
For each result where snippet is insufficient:
  fetch.url(result.url) → full page Markdown
  ↓
Normalize to KnowledgeHit { source, title, url, snippet=fullContent, score }
  ↓
Merge into rank-fusion result set
```

`fetch.url` is called only for results that need expansion — short snippets that don't contain enough context for the agent to act on. Results with rich snippets skip the fetch step. This keeps fetch calls to a minimum and avoids fetching pages that are already well-summarized by the search engine.

---

## Config Snippet

```yaml
# config/mcp-servers.d/fetch.yaml

name: fetch
version: "^1.0.0"
source:
  kind: npx
  package: "@modelcontextprotocol/server-fetch"
transport: stdio
env:
  - name: FETCH_DOMAIN_ALLOWLIST
    # Comma-separated list of allowed domains.
    # Tenant-specific additions are appended via the mcp_server_registrations override.
    value: "docs.anthropic.com,developer.mozilla.org,nodejs.org,npmjs.com,github.com,raw.githubusercontent.com,stackoverflow.com,pypi.org,learn.microsoft.com,cloud.google.com,docs.aws.amazon.com"
  - name: FETCH_USER_AGENT
    value: "AgentStudio/1.0 (+https://agent-studio.example.com/bot)"
  - name: FETCH_TIMEOUT_MS
    value: "15000"
  - name: FETCH_MAX_CONTENT_BYTES
    value: "524288"      # 512 KB limit on returned content
healthcheck:
  tool: fetch.url
  intervalMs: 120000
  timeoutMs: 10000
retries:
  maxAttempts: 2
  backoffMs: 1000
allowlist:
  planner:  ["fetch.url"]
  coder:    ["fetch.url"]
  tester:   ["fetch.url"]
  reviewer: ["fetch.url"]
approvalRequired: []
enabled: true
```

---

## Error Handling

| Error | Behaviour |
|---|---|
| Domain not in allowlist | Server returns `DomainNotAllowed` error; agent receives error and adjusts (e.g. try a different URL or skip fetch) |
| Private IP blocked | Server returns `PrivateAddressBlocked` error |
| HTTP 404 / 403 | Server returns the HTTP error code; agent receives it and handles gracefully |
| Timeout | Server returns `FetchTimeout` after `FETCH_TIMEOUT_MS`; agent retries or skips |
| Content too large | Server truncates to `FETCH_MAX_CONTENT_BYTES` and returns a `truncated: true` flag |
| Server process crash | MCP client emits `tool_unavailable server=fetch`; Knowledge Retrieval degrades to snippet-only results |

---

## Security Notes

- The Fetch MCP server runs with no filesystem write access and no process spawn capability. It is a pure HTTP client.
- The `FETCH_USER_AGENT` header identifies requests as coming from Agent Studio, allowing web operators to block or rate-limit the bot if desired.
- Fetched content is never persisted to the orchestrator's database. It flows directly from the Fetch MCP server response through the MCP client to the requesting agent, in memory only.
- The `FETCH_MAX_CONTENT_BYTES` limit prevents an oversized page from consuming excessive memory in the orchestrator process.

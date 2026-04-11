# ADR-0001: TypeScript/Node.js Monorepo with pnpm and Turborepo

**Status:** Accepted  
**Date:** 2026-04-11  
**Deciders:** Agent Studio Architecture Team

## Context

Agent Studio is a greenfield platform spanning multiple distinct concerns: a central orchestrator service, an agent runtime with four specialist roles, a deep-coding worker layer, an LLM abstraction, an MCP client, a knowledge retrieval server, a testing pipeline, a Next.js web UI, a VS Code extension, and a shared-types library. All of these must interoperate closely — the orchestrator hands typed task envelopes to the agent runtime; the agent runtime constructs typed dispatch envelopes for deep-coding workers; the web UI and VS Code extension consume the same typed WebSocket event stream. If these packages diverge in their type definitions, runtime mismatches become a maintenance problem that compounds over time.

The team evaluated three packaging strategies: (1) a single-package monolith, (2) independently versioned packages published to a private npm registry, and (3) a monorepo with a unified build graph. A monolith collapses isolation — the VS Code extension would bundle server-side orchestrator code; the MCP client would pull in UI dependencies. Independently versioned packages introduce versioning friction across a small team: every cross-package change requires coordinated publish-and-bump cycles before integration can be tested end-to-end. A monorepo avoids both problems by keeping packages independently importable while sharing a single `node_modules` tree and build cache.

The language choice is TypeScript across the board. All server-side packages (orchestrator, agent-runtime, deep-coding, llm, mcp-client, knowledge) are Node.js services or libraries. The web UI is a Next.js application. The VS Code extension is a TypeScript Extension Host program. MCP servers for knowledge retrieval and the Claude Code worker are also TypeScript/Node.js so they share the `shared-types` package directly rather than via generated code. External MCP servers (Ruflo, code-review-graph, Git, GitHub, Playwright, Filesystem, Fetch) are consumed as upstream distributions and are not part of this monorepo.

pnpm is selected as the package manager for its content-addressable store (fast installs, minimal disk use in CI), native workspace protocol, and excellent Turborepo compatibility. Turborepo provides the task pipeline (`build`, `test`, `lint`, `typecheck`) with remote caching so unchanged packages are never rebuilt. The `shared-types` package is the sole declared dependency of every other package; Turborepo enforces build order so type changes always propagate before dependents compile.

## Decision

Agent Studio is structured as a single pnpm + Turborepo monorepo containing the following packages under `packages/`: `orchestrator`, `agent-runtime`, `deep-coding`, `llm`, `mcp-client`, `knowledge`, `testing`, `web`, `vscode-extension`, and `shared-types`. There is no standalone `memory` package (persistent memory is delegated to Ruflo via MCP) and no standalone `code-graph` package (structural code analysis is delegated to the `code-review-graph` MCP server). TypeScript is the sole language across all packages. Every package extends a root `tsconfig.base.json` and references `@agent-studio/shared-types` for all cross-package type contracts.

The monorepo structure enables a single `turbo run build` from the root to produce all deployable artifacts (Docker images for the orchestrator, a `.vsix` for the extension, a Next.js build for the web UI) in dependency order with full caching. A single `turbo run typecheck` validates the entire type surface across all packages in one command, making cross-package type regressions visible in CI before merge.

## Consequences

### Positive
- Shared TypeScript types across all packages eliminate an entire class of runtime type-mismatch bugs between the orchestrator, agent runtime, web UI, and VS Code extension.
- A single `pnpm install` bootstraps the entire development environment; contributors do not need to manually link or publish packages to iterate locally.
- Turborepo remote cache means CI build times scale sub-linearly as the codebase grows — only changed packages and their dependents are rebuilt.
- Eliminating standalone `memory` and `code-graph` packages keeps the package count lean; those capabilities are consumed as MCP servers without bespoke integration code.
- Uniform tooling (ESLint, Prettier, Vitest) configured once at the root applies consistently to all packages.
- One PR can atomically change a shared type, update all consumers, and land as a single reviewed diff with no publish cycle.

### Negative / Trade-offs
- A monorepo is a larger mental model for new contributors than a single-package project; onboarding requires understanding the workspace protocol, `turbo.json` pipeline, and package boundary conventions.
- All packages must agree on major dependency versions (TypeScript, Node.js, `@modelcontextprotocol/sdk`). Upgrading a foundational dependency requires coordinated changes across all packages simultaneously.
- The VS Code extension's bundler (esbuild) must be configured to resolve workspace packages correctly; misconfiguration can accidentally bundle Node.js built-ins incompatible with the Extension Host sandbox.
- Large monorepos can develop slow `git status` / `git log` times; mitigated with `git sparse-checkout` for contributors focused on a single surface.

### Neutral
- External MCP servers (Ruflo, code-review-graph, Git, etc.) are referenced by npm package name or Docker image tag in `McpServerSpec` config, not as workspace packages. Their versioning is managed through the MCP Registry independently of the monorepo release cycle.
- TypeScript is compiled to CommonJS for server packages and ESM for the web app; the dual-output is handled per-package via `tsconfig.build.json` variants and does not affect the monorepo structure.

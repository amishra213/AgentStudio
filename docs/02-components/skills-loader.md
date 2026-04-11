# Skills Loader

The Skills Loader allows users to extend every Agent Studio Claude Code session with custom, reusable capabilities by dropping files into a SKILLs repository. Skills are discovered at session start, registered with the Claude Agent SDK, and made available to all inner Claude Code sessions dispatched during a task.

---

## What a skill is

A skill is a named, self-describing capability that an agent can invoke by name. In the Claude Agent SDK, skills appear as first-class tools in the agent's context alongside MCP tools. The difference is that skills are **user-defined, stored in a git repository, and versioned with the user's code** rather than being installed from an external registry.

Typical skill examples:

| Skill name | What it does |
|---|---|
| `deploy-to-staging` | Runs a project-specific deploy script and waits for health |
| `lint-and-format` | Runs ESLint + Prettier with project-specific config |
| `generate-migration` | Scaffolds a DB migration file for a given schema change |
| `refresh-api-types` | Regenerates TypeScript types from an OpenAPI spec |
| `notify-slack` | Posts a Slack message to a configured channel |

---

## Directory layout contract

A SKILLs repository (or directory within a monorepo) must follow this layout:

```
skills/
├── deploy-to-staging/
│   ├── SKILL.md          # required — name, description, arguments, examples
│   └── run.sh            # optional — executable invoked when skill is called
├── generate-migration/
│   ├── SKILL.md
│   └── generate.ts       # optional — any executable file (ts-node, python, etc.)
├── refresh-api-types/
│   └── SKILL.md          # script-less skill: pure prompt instructions only
└── _shared/
    └── helpers.sh        # optional — shared scripts not exposed as skills
```

### `SKILL.md` format

```markdown
---
name: generate-migration
version: 1.2.0
description: >
  Scaffolds a database migration file for a given schema change.
  Reads the existing schema from prisma/schema.prisma and produces
  a timestamped migration in prisma/migrations/.
arguments:
  - name: change_description
    type: string
    required: true
    description: Human-readable description of the schema change.
  - name: dry_run
    type: boolean
    required: false
    default: false
    description: If true, print the migration content without writing to disk.
examples:
  - input: "Add nullable phone_number column to users table"
    description: Generates a migration adding the column.
executor:
  type: script          # script | inline | mcp_tool
  command: ts-node generate.ts
  timeout_seconds: 30
tags: [database, schema, prisma]
---

## Instructions

When invoked, run the executor command with `change_description` as the first argument.
If `dry_run=true`, pass `--dry-run` to the command.
After the script exits, report the path of the generated migration file.
```

**`executor.type` values:**

| Type | Meaning |
|---|---|
| `script` | Execute `command` as a subprocess. Stdout is returned as the skill result. |
| `inline` | No subprocess. The `SKILL.md` body is the complete instruction for the agent to follow. |
| `mcp_tool` | Delegate to a named MCP tool (e.g. `git.commit`). The skill becomes a typed alias. |

---

## Mounting options

### Option A — Filesystem mount

The SKILLs directory is mounted directly into the orchestrator pod (or Docker Compose volume). The path is configured in `agent-studio.config.ts`:

```typescript
skillsLoader: {
  mount: {
    type: 'filesystem',
    path: '/mnt/skills',       // absolute path inside the container
  },
}
```

This is the simplest option for single-tenant or development deployments.

### Option B — Git clone at session start

The Skills Loader clones (or pulls) the SKILLs repository into a local workspace at session start. The repo URL and credentials are resolved from the secrets backend.

```typescript
skillsLoader: {
  mount: {
    type: 'git',
    repoUrl: 'https://github.com/acme/agent-skills',
    branch: 'main',
    authSecretRef: 'skills-repo-token',    // resolved from secrets backend
    cloneDepth: 1,                          // shallow clone
    cacheDir: '/tmp/skills-cache',          // reused across sessions within a pod
  },
}
```

The clone is cached per pod. A `git pull --ff-only` is performed at the start of each task session to pick up new skills without restarting. If the pull fails (network, auth), the loader falls back to the cached clone and emits a warning event.

---

## Scan and registration

At session start the Skills Loader performs:

```
1. Resolve the skills root directory (filesystem mount or git clone).
2. Walk the directory tree looking for SKILL.md files (max depth: 3).
3. Parse each SKILL.md (YAML front matter + markdown body).
4. Validate: required fields present, version is semver, executor command exists if type=script.
5. Register valid skills with the Claude Agent SDK skill-loading hook.
6. Emit skill_loaded event per skill (visible in Web UI session log).
7. Log a warning for any skill that failed validation; continue loading others.
```

```typescript
// packages/agent-runtime/src/skills-loader.ts

export async function loadSkills(
  sdk: ClaudeAgentSDK,
  config: SkillsConfig,
  tenantId: string,
  projectId: string,
): Promise<SkillLoadResult> {
  const root = await resolveSkillsRoot(config);
  const manifests = await scanSkillManifests(root);
  const valid = manifests.filter(m => validateManifest(m).ok);

  for (const manifest of valid) {
    sdk.registerSkill({
      name: manifest.name,
      description: manifest.description,
      inputSchema: buildJsonSchema(manifest.arguments),
      handler: buildHandler(manifest, root),
    });
  }

  return { loaded: valid.length, skipped: manifests.length - valid.length };
}
```

---

## Precedence rules

Skills from multiple sources can overlap. The loader resolves conflicts in priority order (highest first):

| Priority | Source | Description |
|---|---|---|
| 1 | **Tenant-level skills** | Repo or directory configured in tenant settings; applies across all projects |
| 2 | **Project-level skills** | `skillsDir` declared in the project's `agent-studio.mcp.yaml` |
| 3 | **Platform defaults** | Skills shipped with Agent Studio in `packages/agent-runtime/default-skills/` |

When two skills share the same `name`, the higher-priority source wins. The lower-priority skill is not registered and a warning is emitted (`skill_shadowed` event).

```
Precedence resolution example:
  tenant-skills/deploy-to-staging/SKILL.md   (priority 1) → REGISTERED
  project-skills/deploy-to-staging/SKILL.md  (priority 2) → SHADOWED, warning emitted
  platform-defaults/deploy-to-staging/SKILL.md (priority 3) → SHADOWED
```

The active skill registry is visible in the Web UI **Settings → Skills** panel, which shows the name, version, source, and priority of every registered skill.

---

## How agents discover and invoke skills

Once registered, skills appear in the Claude Agent SDK's tool list alongside MCP tools. Agents see them as first-class tools and invoke them by name:

```
Agent internal tool call:
  tool: generate-migration
  arguments: { change_description: "Add index on orders.created_at", dry_run: false }
```

The SDK routes this to the registered handler. For `type: script` skills, the Skills Loader forks a subprocess with the configured command, passes arguments as environment variables and stdin JSON, captures stdout, and returns it as the tool result. The subprocess runs with the task workspace as its working directory.

For `type: inline` skills, the SDK injects the `SKILL.md` body as additional context for the agent's reasoning step — no subprocess is spawned.

For `type: mcp_tool` skills, the SDK calls the delegated MCP tool through the MCP client. Allowlist and approval rules of the underlying tool apply.

---

## Security constraints

- **Script execution is sandboxed.** Scripts invoked via `type: script` run in the task's Docker container (sandboxed worker mode) or within the Orchestrator process with a restricted PATH, no internet access beyond the MCP egress allowlist, and a wall-time limit (`executor.timeout_seconds`).
- **No network access from inline skills.** `type: inline` skills are prompt-only; they cannot make network calls directly.
- **Secrets are not available to skill scripts by default.** If a skill script requires a secret (e.g. a Slack token), it must declare it in `SKILL.md` under a `secrets` stanza; the Orchestrator then resolves and injects it as an environment variable at invocation time. Undeclared secrets are never in the subprocess environment.
- **Tenant-level skills require admin approval.** Adding or modifying tenant-level skills requires tenant-admin RBAC and is audit-logged.

---

## Version pinning

Each skill declares a `version` in its front matter. The skills repository should use standard git tags or a lockfile to pin to known-good skill versions. The platform does not enforce version constraints at runtime beyond logging the version with each `skill_loaded` event; pinning responsibility lies with the repository maintainer.

---

## Related components

- [Agent Runtime](./agent-runtime.md) — roles that consume registered skills
- [LLM Abstraction](./llm-abstraction.md) — Claude adapter exposes the SDK skill-loading hook
- [Deep Coding Workers](./deep-coding-workers.md) — inner sessions inherit the skills directory from `DispatchEnvelope.skillsDir`
- [MCP Registry](./mcp-registry.md) — parallel pattern: MCP servers follow the same install/list/enable lifecycle

# LLM Abstraction

The LLM abstraction layer provides a **provider-agnostic interface** that decouples every Agent Studio component from any specific large-language-model vendor. Claude (`@anthropic-ai/claude-agent-sdk`) is the default and best-supported provider. OpenAI, Gemini, and Ollama adapters exist as stubs ready for production implementation.

---

## Design goals

| Goal | How it is achieved |
|---|---|
| Vendor swap without role logic changes | All roles interact only with `LLMProvider`; no Anthropic types leak into `agent-runtime` |
| Per-role model selection | Config supplies a `{ provider, model }` entry per role; the runtime resolves it at startup |
| Token counting before dispatch | `countTokens()` lets the Orchestrator estimate cost before committing budget |
| Cost tracking hooks | `onUsage` callback fired after every call; Orchestrator accumulates into `task.totalTokensUsed` |
| Streaming for real-time UI | `stream()` yields `StreamChunk` objects forwarded over WebSocket to both surfaces |
| Embeddings for semantic recall | `embed()` used by the MemoryClient when a Ruflo fallback vector store is needed |

---

## TypeScript interface

```typescript
// packages/llm/src/provider.ts

export interface Message {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string | ContentBlock[];
  toolCallId?: string;   // for role='tool' responses
  name?: string;         // for role='tool' — the tool name
}

export interface ContentBlock {
  type: 'text' | 'tool_use' | 'tool_result' | 'image';
  text?: string;
  toolUse?: { id: string; name: string; input: unknown };
  toolResult?: { toolUseId: string; content: string; isError?: boolean };
  imageSource?: { type: 'base64'; mediaType: string; data: string };
}

export interface GenerateOptions {
  model?: string;               // override per-call; default from config
  maxTokens?: number;           // default: provider max
  temperature?: number;         // default: 0 for deterministic roles
  stopSequences?: string[];
  tools?: ToolDefinition[];     // MCP tool schemas passed through
  toolChoice?: 'auto' | 'any' | 'none' | { type: 'tool'; name: string };
  systemPrompt?: string;        // injected once at top of context
  signal?: AbortSignal;         // propagated from Orchestrator cancel
  onUsage?: (usage: TokenUsage) => void;  // cost tracking hook
}

export interface TokenUsage {
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens?: number;
  cacheWriteTokens?: number;
  totalTokens: number;
  estimatedCostUsd?: number;
}

export interface GenerateResult {
  content: ContentBlock[];
  stopReason: 'end_turn' | 'tool_use' | 'max_tokens' | 'stop_sequence';
  usage: TokenUsage;
  model: string;          // resolved model name as confirmed by provider
}

export interface StreamChunk {
  type: 'text_delta' | 'tool_use_start' | 'tool_use_delta' | 'tool_use_end' | 'usage' | 'error';
  delta?: string;
  toolUse?: Partial<ContentBlock['toolUse']>;
  usage?: TokenUsage;
  error?: string;
}

export interface ToolDefinition {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;  // JSON Schema
}

export interface LLMProvider {
  /** Non-streaming generation — preferred for short role turns */
  generate(messages: Message[], options?: GenerateOptions): Promise<GenerateResult>;

  /** Streaming generation — used for real-time UI forwarding */
  stream(messages: Message[], options?: GenerateOptions): AsyncIterable<StreamChunk>;

  /** Embedding — used by MemoryClient for local vector fallback */
  embed(text: string | string[]): Promise<number[][]>;

  /** Token count estimate without making a generation call */
  countTokens(messages: Message[], options?: Pick<GenerateOptions, 'tools' | 'systemPrompt'>): Promise<number>;

  /** Health check — returns true if the provider endpoint is reachable */
  ping(): Promise<boolean>;
}
```

---

## Claude adapter (default)

The Claude adapter wraps `@anthropic-ai/claude-agent-sdk`. It is the only adapter that enables the full skill-loading and subagent features.

```typescript
// packages/llm/src/adapters/claude.ts
import { ClaudeAgentSDK } from '@anthropic-ai/claude-agent-sdk';

export class ClaudeAdapter implements LLMProvider {
  private sdk: ClaudeAgentSDK;

  constructor(config: ClaudeAdapterConfig) {
    this.sdk = new ClaudeAgentSDK({
      apiKey: config.apiKey,       // resolved from secrets backend, never from env directly
      baseURL: config.baseURL,     // optional: Anthropic API proxy
      defaultModel: config.model,
      maxRetries: 3,
    });
  }

  async generate(messages, options) { /* ... */ }
  async *stream(messages, options) { /* ... */ }
  async embed(text) { /* delegates to claude-3-haiku for embeddings */ }
  async countTokens(messages, options) { /* uses SDK token-counting endpoint */ }
  async ping() { /* HEAD /v1/models */ }
}
```

**Skill loading:** When a Claude adapter is used in a role that has a `skillsDir`, the adapter passes the directory to the SDK's skill-loading hook before the first turn. See [skills-loader.md](./skills-loader.md).

**Subagent support:** The Claude adapter is the only adapter that supports spawning SDK subagents (used internally in the Deep Coding Worker's in-process mode). Non-Claude adapters can still run outer role turns; they simply cannot spawn in-process `query()` sessions.

---

## OpenAI adapter (stub)

```typescript
// packages/llm/src/adapters/openai.ts
export class OpenAIAdapter implements LLMProvider {
  // Uses openai npm package
  // generate() → chat.completions.create({ stream: false })
  // stream()   → chat.completions.create({ stream: true })
  // embed()    → embeddings.create({ model: 'text-embedding-3-small' })
  // countTokens() → tiktoken approximation (no round-trip)
  // NOTE: tool-call schema maps MCP ToolDefinition → OpenAI function schema
}
```

Tool schema translation: MCP tools expose a JSON Schema `inputSchema`. The OpenAI adapter converts this to OpenAI's `{ type: 'function', function: { name, description, parameters } }` shape. The reverse mapping converts OpenAI tool call responses back to the internal `ContentBlock` format.

---

## Gemini adapter (stub)

```typescript
// packages/llm/src/adapters/gemini.ts
export class GeminiAdapter implements LLMProvider {
  // Uses @google/generative-ai package
  // generate() → model.generateContent()
  // stream()   → model.generateContentStream()
  // embed()    → model.embedContent()
  // NOTE: Gemini function-calling schema differs; adapter normalises both directions
}
```

---

## Ollama adapter (stub)

```typescript
// packages/llm/src/adapters/ollama.ts
export class OllamaAdapter implements LLMProvider {
  // Targets local Ollama HTTP API (http://localhost:11434)
  // Useful for air-gapped deployments or cost-free experimentation
  // generate() → POST /api/chat
  // stream()   → POST /api/chat { stream: true }
  // embed()    → POST /api/embeddings
  // countTokens() → no native endpoint; uses character-based heuristic
  // ping()     → GET /api/version
}
```

---

## Provider factory and registration

```typescript
// packages/llm/src/factory.ts

const adapterRegistry = new Map<string, AdapterConstructor>([
  ['claude',  ClaudeAdapter],
  ['openai',  OpenAIAdapter],
  ['gemini',  GeminiAdapter],
  ['ollama',  OllamaAdapter],
]);

export function createProvider(spec: ProviderSpec): LLMProvider {
  const Adapter = adapterRegistry.get(spec.provider);
  if (!Adapter) throw new Error(`Unknown LLM provider: ${spec.provider}`);
  return new Adapter(resolveSecrets(spec));
}

// Custom providers: call registerAdapter() at startup
export function registerAdapter(name: string, ctor: AdapterConstructor): void {
  adapterRegistry.set(name, ctor);
}
```

---

## Model selection per role

Model selection is configured in `agent-studio.config.ts` and resolved at startup. Each role gets its own provider instance:

```typescript
agentRuntime: {
  models: {
    planner: {
      provider: 'claude',
      model: 'claude-opus-4-5',       // highest capability for decomposition
    },
    coder: {
      provider: 'claude',
      model: 'claude-sonnet-4-5',     // fast + capable for code tasks
    },
    tester: {
      provider: 'claude',
      model: 'claude-sonnet-4-5',
    },
    reviewer: {
      provider: 'claude',
      model: 'claude-opus-4-5',       // highest capability for risk assessment
    },
  },
  // Override for a specific project:
  // projectOverrides: { 'project-123': { coder: { model: 'gpt-4o' } } }
},
```

Per-task overrides can be submitted via the `task.submit` API. Project-level overrides are declared in `agent-studio.mcp.yaml`. Tenant-level defaults are stored in the `tenant_settings` Postgres table.

---

## Token counting and cost estimation

Before dispatching any Claude Code worker, the Orchestrator calls `provider.countTokens()` to estimate the cost of the dispatch:

```typescript
const estimatedInput = await provider.countTokens(envelope.messages, {
  tools: envelope.mcpServers.flatMap(s => s.tools),
  systemPrompt: role.systemPrompt,
});

const estimatedCost = estimatedInput * MODEL_COST_PER_INPUT_TOKEN[config.model]
                    + EXPECTED_OUTPUT_TOKENS * MODEL_COST_PER_OUTPUT_TOKEN[config.model];

if (task.budgetRemaining.dollarsUsd < estimatedCost) {
  throw new BudgetExceededError(estimatedCost, task.budgetRemaining.dollarsUsd);
}
```

Model cost tables are maintained in `packages/llm/src/costs.ts` and updated as providers publish new pricing. The `onUsage` hook fires with actual usage after each call and feeds into the Orchestrator's `cost_update` event.

---

## Swapping providers

To switch a role from Claude to a different provider:

1. Set the `provider` key in `agent-studio.config.ts` for that role.
2. Supply the credentials via the secrets backend (the adapter resolves them at startup).
3. If the role's system prompt uses Claude-specific capabilities (e.g. extended thinking), update the prompt for the new provider's idioms.
4. Restart the Orchestrator pod (or hot-reload if the runtime supports it).

For production multi-provider failover (e.g. fall back from Claude to OpenAI on rate-limit), the `LLMProvider` interface supports a `FailoverProvider` wrapper:

```typescript
const coderProvider = new FailoverProvider([
  createProvider({ provider: 'claude',  model: 'claude-sonnet-4-5' }),
  createProvider({ provider: 'openai',  model: 'gpt-4o' }),
], { strategy: 'on_error', maxRetries: 2 });
```

The `FailoverProvider` is transparent to the rest of the system — it satisfies `LLMProvider` and routes calls internally.

---

## Observability

Every call through `LLMProvider` is wrapped in an instrumentation layer that emits:

```typescript
interface LLMCallSpan {
  traceId: string;
  taskId: string;
  role: AgentRole;
  provider: string;
  model: string;
  inputTokens: number;
  outputTokens: number;
  latencyMs: number;
  stopReason: string;
  estimatedCostUsd: number;
  cached: boolean;
}
```

Spans are written to the `llm_call_log` table and surfaced on the Web UI **MCP Call Log** tab alongside MCP tool calls, so operators can see the full cost breakdown across a task run.

---

## Related components

- [Agent Runtime](./agent-runtime.md) — roles that consume `LLMProvider`
- [Deep Coding Workers](./deep-coding-workers.md) — Claude adapter's `query()` used for in-process workers
- [Skills Loader](./skills-loader.md) — skills registered via Claude adapter's SDK hook
- [Hosting and Deployment](./hosting-and-deployment.md) — secrets management for API keys

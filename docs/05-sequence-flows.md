# Sequence Flows — End-to-End Execution Diagrams

This document presents three Mermaid sequence diagrams that trace the most important execution paths through Agent Studio:

1. **Happy path** — task submitted through to delivery bundle and merged PR
2. **Test failure retry loop** — how the system recovers from a failing test using memory and knowledge retrieval
3. **HITL mid-task approval** — how a WMS write call is intercepted, approved by a human, and continued

---

## 1. Happy Path — Task Submitted to Delivery Bundle

This diagram traces a complete successful run: the user submits a task, the orchestrator dispatches it through all four roles, and the human approves the final PR merge.

```mermaid
sequenceDiagram
    actor U as User
    participant UI as VS Code / Web UI
    participant O as Orchestrator
    participant R as Ruflo (Memory MCP)
    participant G as code-review-graph MCP
    participant GH as GitHub MCP
    participant PL as Planner Role
    participant CO as Coder Role
    participant CCW as ClaudeCode Worker
    participant FS as Filesystem MCP
    participant GIT as Git MCP
    participant TE as Tester Role
    participant PW as Playwright MCP
    participant RE as Reviewer Role

    U->>UI: Submit task: "Add timeout to WMS order processor"
    UI->>O: POST /tasks { requirement, budgetTokens }
    O->>O: Create task record (status=not_started)
    O-->>UI: 201 Created { taskId }
    O->>O: Enqueue task in BullMQ

    note over O,GIT: Task start — repository setup
    O->>GIT: git.clone(repoUrl, workDir)
    GIT-->>O: cloned
    O->>G: graph.build(workDir)
    G-->>O: graph built

    note over O,PL: Planner phase
    O->>O: status → planning
    O->>R: memory.search("WMS order processor timeout")
    R-->>O: [MemoryHit: "similar timeout added to WMS v1.2, used env var"]
    O->>PL: Dispatch planner with memory context
    PL->>G: graph.architecture_overview()
    G-->>PL: Module summary (WMS service, config loader, order processor)
    PL->>G: graph.semantic_search("order processor timeout configuration")
    G-->>PL: [OrderProcessor.ts, wms_config.ts, config.schema.json]
    PL->>R: memory.store(scope=project, kind=decision, payload=plan)
    PL->>O: DispatchEnvelope { goal, workspace, successCriteria, mcpServers, memoryContext }

    note over O,CCW: Coder phase
    O->>O: status → in_progress
    O->>CO: Dispatch coder with DispatchEnvelope
    CO->>CCW: claude_code.run(envelope)

    loop Fix iterations (typically 1-2)
        CCW->>G: graph.impact_radius([OrderProcessor.ts])
        G-->>CCW: affected nodes
        CCW->>G: graph.callers_of(OrderProcessor.processOrder)
        G-->>CCW: call sites
        CCW->>FS: fs.read("src/wms/OrderProcessor.ts")
        FS-->>CCW: file content
        CCW->>FS: fs.write("src/wms/OrderProcessor.ts", updatedContent)
        FS-->>CCW: written
        CCW->>FS: fs.write("config/wms_config.yaml", updatedConfig)
        FS-->>CCW: written
        CCW->>GIT: git.stage(["src/wms/OrderProcessor.ts", "config/wms_config.yaml"])
        GIT-->>CCW: staged
        CCW->>GIT: git.commit("feat: add configurable timeout to WMS order processor")
        GIT-->>CCW: committed
        O->>G: graph.update(workDir, sinceRef=prevHead)
        O->>G: graph.detect_changes(workDir)
    end

    CCW-->>CO: WorkerResult { exitReason: success, diff }
    CO->>R: memory.store(scope=project, kind=fix, payload=diffSummary)
    CO->>O: Handoff to tester

    note over O,PW: Tester phase
    O->>TE: Dispatch tester
    TE->>G: graph.tests_for([OrderProcessor.ts, wms_config.ts])
    G-->>TE: ["tests/wms/OrderProcessor.spec.ts", "tests/wms/config.spec.ts"]
    TE->>G: graph.impact_radius([OrderProcessor.ts])
    G-->>TE: full impact set
    TE->>CCW: claude_code.run({ goal: "generate timeout test cases", ... })
    CCW->>FS: fs.write("tests/wms/OrderProcessor.spec.ts", newSpecs)
    CCW-->>TE: spec files generated
    TE->>GIT: git.stage(["tests/wms/OrderProcessor.spec.ts"])
    TE->>GIT: git.commit("test: add timeout test cases")
    O->>G: graph.update(workDir, sinceRef=prevHead)
    TE->>PW: playwright.run_test({ files: ["tests/wms/OrderProcessor.spec.ts"] })
    PW-->>TE: { passed: 12, failed: 0, coverage: 94% }
    TE->>PW: playwright.get_report()
    PW-->>TE: HTML report
    TE->>R: memory.store(scope=project, kind=test_result, payload=testSummary)
    TE->>O: Handoff to reviewer (tests passed)

    note over O,RE: Reviewer phase
    O->>RE: Dispatch reviewer
    RE->>G: graph.impact_radius([OrderProcessor.ts, wms_config.ts])
    G-->>RE: full impact set
    RE->>G: graph.detect_changes(workDir)
    G-->>RE: risk-scored change summary
    RE->>G: graph.wiki_generate(taskSubgraph)
    G-->>RE: Markdown docs
    RE->>G: graph.visualize(impactedNodes)
    G-->>RE: interactive HTML graph
    RE->>O: Delivery bundle assembled

    note over O,GH: PR creation (HITL-gated)
    O->>UI: WebSocket: task.delivery_bundle_ready
    UI->>U: "Delivery bundle ready — review and approve PR creation"
    CO->>GH: github.create_pr(title, body=bundleSummary, head=agentBranch, draft=true)
    note over CO,GH: Intercepted by HITL gate
    O->>UI: hitl.question { tool: "github.create_pr", title, body }
    U->>UI: Approve PR creation
    UI->>O: POST /tasks/:id/approve { hitlRequestId }
    O->>GH: github.create_pr (forwarded)
    GH-->>O: { prNumber: 42, prUrl: "..." }
    O->>UI: WebSocket: hitl.resolved

    note over O,GH: Merge (HITL-gated)
    RE->>GH: github.merge_pr(prNumber=42, mergeMethod=squash)
    note over RE,GH: Intercepted by HITL gate
    O->>UI: hitl.question { tool: "github.merge_pr", prNumber: 42 }
    U->>UI: Approve merge
    UI->>O: POST /tasks/:id/approve { hitlRequestId }
    O->>GH: github.merge_pr (forwarded)
    GH-->>O: merged
    O->>O: status → completed
    O->>R: memory.store(scope=project, kind=summary, payload=deliverySummary)
    O->>UI: WebSocket: task.state_changed { to: "completed" }
    UI->>U: Task completed — PR merged
```

---

## 2. Test Failure Retry Loop

This diagram shows how the system recovers when a test fails: it searches Ruflo memory first, then the Knowledge Retrieval MCP, uses the found context to build a targeted fix dispatch, and re-runs tests.

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant TE as Tester Role
    participant PW as Playwright MCP
    participant R as Ruflo (Memory MCP)
    participant K as Knowledge Retrieval MCP
    participant CO as Coder Role
    participant CCW as ClaudeCode Worker
    participant GIT as Git MCP
    participant G as code-review-graph MCP
    participant GH as GitHub MCP

    note over TE,PW: Test run — failure detected
    TE->>PW: playwright.run_test({ files: ["tests/wms/OrderProcessor.spec.ts"] })
    PW-->>TE: { passed: 8, failed: 4, errors: ["Timeout exceeded 30s default", ...] }
    TE->>PW: playwright.get_report()
    PW-->>TE: report with stack traces

    note over TE,R: Stage 1 — local memory lookup
    TE->>R: memory.search("WMS OrderProcessor timeout exceeded 30s")
    R-->>TE: [] (no matching memory hit above threshold)

    note over TE,K: Stage 2 — federated knowledge search
    TE->>K: knowledge.search("WMS timeout exceeded 30s test failure", sources=["web", "github", "confluence"])

    par Web search
        K->>K: Tavily.search("WMS timeout exceeded 30s test failure")
    and GitHub search
        K->>GH: github.search_code("WMS order processor timeout 30s")
        K->>GH: github.search_issues("WMS timeout test failure")
    and Confluence search
        K->>K: CQL search("WMS AND timeout AND test")
    end

    GH-->>K: [{ title: "Fix: WMS processor default timeout was hardcoded", url: "...", snippet: "The timeout should default to env var WMS_ORDER_TIMEOUT_MS, falling back to 30000" }]
    K->>K: RRF re-rank all results
    K-->>TE: [KnowledgeHit { source: "github", title: "Fix: WMS processor default...", snippet, score: 0.91 }]

    note over TE,CCW: Build fix dispatch with knowledge context pre-loaded
    TE->>CCW: claude_code.run(DispatchEnvelope {
    note right of TE: goal: "Fix failing timeout tests — see knowledgeContext",
    note right of TE: knowledgeContext: [KnowledgeHit],
    note right of TE: memoryContext: [],
    note right of TE: successCriteria: { tests: ["pnpm test tests/wms/OrderProcessor.spec.ts"] }
    TE->>CCW: })

    CCW->>CCW: Read knowledgeContext: env var WMS_ORDER_TIMEOUT_MS is the fix
    CCW->>GIT: git.diff()
    GIT-->>CCW: current diff showing hardcoded 30000
    CCW->>CCW: Fix: replace hardcoded value with process.env.WMS_ORDER_TIMEOUT_MS ?? 30000
    CCW->>CCW: fs.write("src/wms/OrderProcessor.ts", fixedContent)
    CCW->>CCW: fs.write("tests/wms/OrderProcessor.spec.ts", updatedTest)
    CCW->>GIT: git.stage([...])
    CCW->>GIT: git.commit("fix: use WMS_ORDER_TIMEOUT_MS env var for default timeout")
    GIT-->>CCW: committed
    CCW-->>TE: WorkerResult { exitReason: success, diff }

    note over O,G: Graph update after fix commit
    O->>G: graph.update(workDir, sinceRef=prevHead)
    G-->>O: graph updated

    note over TE,PW: Re-run tests
    TE->>PW: playwright.run_test({ files: ["tests/wms/OrderProcessor.spec.ts"] })
    PW-->>TE: { passed: 12, failed: 0, coverage: 94% }
    TE->>R: memory.store(scope=project, kind=fix, payload={
    note right of TE: error: "Timeout exceeded 30s",
    note right of TE: fix: "Use WMS_ORDER_TIMEOUT_MS env var",
    note right of TE: knowledgeSource: "github issue #742"
    TE->>R: })
    TE->>R: pattern.store({
    note right of TE: description: "WMS hardcoded timeout — use env var pattern",
    note right of TE: tags: ["wms", "timeout", "env-var"]
    TE->>R: })
    TE->>O: Tests pass — handoff to reviewer
```

---

## 3. HITL Mid-Task Approval — WMS Config Write

This diagram shows how a coder's call to `wms.update_config` is intercepted by the HITL approval gate, presented to the human in both VS Code and the web UI, and then either approved (forwarded to WMS) or rejected (Coder proposes alternative).

```mermaid
sequenceDiagram
    actor U as User
    participant VSC as VS Code Extension
    participant WEB as Web UI
    participant O as Orchestrator
    participant MC as MCP Client
    participant CO as Coder Role
    participant CCW as ClaudeCode Worker
    participant WMS as WMS MCP Server

    note over CO,CCW: Coder is mid-fix — needs to update WMS config
    CCW->>MC: wms.update_config({
    note right of CCW: configId: "order-processor",
    note right of CCW: patch: { orderTimeoutMs: 45000 }
    CCW->>MC: })

    note over MC,O: MCP Client intercepts — tool is approval-gated
    MC->>MC: Check allowlist: coder → wms.update_config ✓
    MC->>MC: Check approvalRequired: wms.update_config → true
    MC->>O: Raise HITL: { hitlRequestId, tool: "wms.update_config", args, riskContext: "WMS config write" }

    note over O: Task run paused; HITL record created
    O->>O: Create hitl_requests row (answered_at=NULL)
    O->>O: Pause CCW iteration (suspend tool call)

    par Notify both surfaces
        O->>VSC: WebSocket: hitl.question { hitlRequestId, tool, args, question }
        O->>WEB: WebSocket: hitl.question { hitlRequestId, tool, args, question }
    end

    VSC->>U: Notification: "Approval needed: wms.update_config { orderTimeoutMs: 45000 }"
    WEB->>U: HITL approval card shown in task view

    alt User approves
        U->>WEB: Click "Approve" + enter reason "45s is correct per RFC-0042"
        WEB->>O: POST /tasks/:id/approve { hitlRequestId, answer: { approved: true }, reason }
        O->>O: Update hitl_requests (answered_at, actor, answer)
        O->>O: Append to audit_log { verb: "hitl.approve", actor, before, after, reason }

        note over O,MC: Resume suspended tool call
        O->>MC: Forward approved tool call
        MC->>WMS: wms.update_config({ configId: "order-processor", patch: { orderTimeoutMs: 45000 } })
        WMS-->>MC: { success: true, configVersion: "v43" }
        MC-->>CCW: Tool result: { success: true, configVersion: "v43" }

        par Notify both surfaces
            O->>VSC: WebSocket: hitl.resolved { hitlRequestId, approved: true, actor }
            O->>WEB: WebSocket: hitl.resolved { hitlRequestId, approved: true, actor }
        end

        CCW->>CCW: Continue fix loop with config updated
        CCW->>CCW: git.stage + git.commit("fix: update WMS order timeout to 45s")

    else User rejects
        U->>VSC: Click "Reject" + enter reason "45s is too long — use 30s"
        VSC->>O: POST /tasks/:id/reject { hitlRequestId, reason }
        O->>O: Update hitl_requests (answered_at, actor, answer=null)
        O->>O: Append to audit_log { verb: "hitl.reject", actor, reason }

        note over O,MC: Return rejection to CCW
        O->>MC: Return ToolRejectedError to pending call
        MC-->>CCW: ToolRejectedError { reason: "45s is too long — use 30s" }

        par Notify both surfaces
            O->>VSC: WebSocket: hitl.resolved { hitlRequestId, approved: false, actor, reason }
            O->>WEB: WebSocket: hitl.resolved { hitlRequestId, approved: false, actor, reason }
        end

        CCW->>CCW: Handle rejection: re-read reason
        CCW->>MC: wms.update_config({ configId: "order-processor", patch: { orderTimeoutMs: 30000 } })
        note over MC,O: New approval gate triggered for revised value
    end
```

---

## Notes on Diagram Conventions

- **Parallel `par` blocks** show operations that happen concurrently, typically fan-out to multiple adapters or notifications.
- **`note` annotations** label phase boundaries (task start, planner phase, etc.) for readability.
- **`alt` blocks** show branching paths (approve vs. reject).
- The diagrams omit retry backoff, MCP health-check polling, and Redis pub/sub fan-out for clarity. See `docs/02-components/orchestrator.md` and `docs/02-components/mcp-client.md` for those details.
- Tool call arguments are abbreviated in the diagrams; full schemas are in the individual integration docs under `docs/02-integrations/`.

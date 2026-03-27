# Continuation Prompt — After Phase 6 Multi-Agent System Design

**Paste this into a new Claude Code session to continue development.**

---

## Context

Nobla Agent is at commit `2852174` on `main`. **344 tests passing.**

### What was just completed:

**Phase 6 — Multi-Agent System DESIGN (spec + 14-task implementation plan):**

1. **Design Spec** (`docs/superpowers/specs/2026-03-27-multi-agent-system-design.md`):
   - Orchestrator-centric architecture (Approach A): all agent communication flows through a central `AgentOrchestrator` via `NoblaEventBus`
   - 8 design sections approved: models, BaseAgent ABC, registry/executor, A2A protocol/orchestrator, workspace/memory isolation, MCP client+server, built-in agents, gateway wiring
   - Spec reviewed (13 issues found and fixed): AgentConnectionState for ToolParams, kill_all() + kill switch wiring, tier validation, orchestrator split into 3 files, etc.

2. **Implementation Plan** (`docs/superpowers/plans/2026-03-27-multi-agent-system.md`):
   - 14 tasks with full TDD flow (write failing test → verify fail → implement → verify pass → commit)
   - Plan reviewed (7 issues found and fixed): workflow status logic, delegation handler documented as v1 stub, query_capabilities deferred, etc.
   - Complete code provided for every file — ~120 tests expected

3. **Gateway refactored** — extracted `lifespan.py` from `app.py` (was 516 lines, now 51 + 505). Ready for agent wiring without exceeding 750-line limit.

4. **Documentation updated** — README.md, CLAUDE.md, backend/README.md all reflect Multi-Agent design status.

### Architecture decisions to preserve:
- **Orchestrator-centric**: agents never talk directly — all A2A goes through orchestrator via event bus
- **AgentConnectionState**: synthetic `ConnectionState` with `connection_id=f"agent:{instance_id}"` for ToolExecutor pipeline compatibility
- **Tier validation**: agent tier cannot exceed spawning user's tier — enforced at spawn time
- **Phase 6 v1 simplification**: orchestrator executes tasks synchronously (TODO for async parallel via A2A protocol in v2)
- **Delegation handler**: v1 stub with TODO — full depth-limited delegation deferred to v2
- **query_capabilities**: deferred to v2 (NotImplementedError)
- **MCP transport**: pluggable via `_do_connect` / `_do_call_tool` override pattern
- **WorkspaceConfig** (Pydantic) vs **WorkflowState** (@dataclass) — intentional: config needs validation, workflow state is mutable scratch

### Module structure (all files to create):
```
backend/nobla/agents/
├── __init__.py          # Lazy imports
├── models.py            # AgentConfig, AgentTask, AgentMessage, WorkflowState, enums
├── base.py              # BaseAgent ABC
├── registry.py          # AgentRegistry (stateless, no constructor deps)
├── workspace.py         # AgentWorkspace (scoped tool/memory/resource sandbox)
├── executor.py          # AgentExecutor (spawn/stop/kill with tier validation)
├── communication.py     # A2AProtocol (task-based messaging, asyncio.Future wait)
├── decomposer.py        # TaskDecomposer (LLM-driven + heuristic fallback)
├── orchestrator.py      # AgentOrchestrator (workflow lifecycle + event handlers)
├── bridge.py            # AgentToolBridge (agent as BaseTool)
├── cloning.py           # clone_agent() config copier
├── mcp_client.py        # MCPClientManager (external MCP consumption)
├── mcp_server.py        # MCPServer (expose Nobla via MCP)
└── builtins/
    ├── __init__.py
    ├── researcher.py    # ResearcherAgent (STANDARD tier, balanced LLM)
    └── coder.py         # CoderAgent (ELEVATED tier, strong LLM)
```

### Existing files to modify:
- `backend/nobla/tools/models.py` — add `ToolCategory.AGENT = "agent"`
- `backend/nobla/config/settings.py` — add `AgentSettings`, `MCPClientSettings`, `MCPServerSettings`
- `backend/nobla/gateway/lifespan.py` — wire agent services + kill switch

### What to do next:

**Execute the implementation plan.** The plan has 14 tasks with complete code. Use:

```
Read docs/superpowers/plans/2026-03-27-multi-agent-system.md and execute it using superpowers:subagent-driven-development (or superpowers:executing-plans). All code is provided inline — implement task by task with TDD.
```

### Task dependency order:
1. Models & Enums + Settings + ToolCategory.AGENT
2. BaseAgent ABC
3. AgentRegistry
4. AgentWorkspace
5. AgentExecutor
6. A2A Protocol
7. TaskDecomposer
8. AgentOrchestrator
9. AgentToolBridge & Cloning
10. MCP Client
11. MCP Server
12. Built-in Agents (Researcher + Coder)
13. Gateway Wiring + Integration Tests
14. Final Verification + CLAUDE.md Update

Tasks 1-4 can be parallelized. Tasks 10-12 can be parallelized after Task 8.

### Test commands:
```bash
# Run existing tests (344 should pass)
cd backend && pytest tests/test_telegram.py tests/test_discord_adapter.py tests/test_scheduler.py tests/test_channels.py tests/test_event_bus.py tests/test_skills.py -v

# Run agent tests (after implementation)
pytest tests/test_agents.py -v

# Run all together
pytest tests/test_telegram.py tests/test_discord_adapter.py tests/test_scheduler.py tests/test_channels.py tests/test_event_bus.py tests/test_skills.py tests/test_agents.py -v
```

### Key files to read first:
- `CLAUDE.md` — Full project guide with all phase status
- `docs/superpowers/plans/2026-03-27-multi-agent-system.md` — The implementation plan (execute this)
- `docs/superpowers/specs/2026-03-27-multi-agent-system-design.md` — Design spec (reference)
- `backend/nobla/gateway/lifespan.py` — Where agent services get wired
- `backend/nobla/events/bus.py` — Event bus (backbone for A2A)
- `backend/nobla/tools/executor.py` — ToolExecutor (agents call tools through this)
- `backend/nobla/automation/confirmation.py` — asyncio.Future pattern to follow

# Continuation Prompt — After Phase 6 Multi-Agent System Implementation

**Paste this into a new Claude Code session to continue development.**

---

## Context

Nobla Agent is at commit `8d3bc19` on `main`. **436 tests passing.**

### What was just completed:

**Phase 6 — Multi-Agent System IMPLEMENTATION (14 tasks, all complete):**

1. **Models & Enums** (`agents/models.py`): AgentConfig, AgentTask, AgentMessage, WorkflowState, ResourceLimits, 5 enums (AgentStatus, TaskStatus, IsolationLevel, MessageType). Added ToolCategory.AGENT and AgentSettings/MCPClientSettings/MCPServerSettings to config.

2. **BaseAgent ABC** (`agents/base.py`): Abstract base with config delegation, lifecycle hooks (on_start/on_stop), convenience methods (think → LLMRouter, use_tool → workspace, delegate → event bus, report → event bus).

3. **AgentRegistry** (`agents/registry.py`): Stateless facade — register/unregister/get/list_all/list_by_role/get_manifest. Mirrors ToolRegistry pattern.

4. **AgentWorkspace** (`agents/workspace.py`): Scoped execution sandbox — tool whitelist enforcement, synthetic ConnectionState (`agent:{instance_id}`), resource tracking (tool_calls, llm_tokens, memory_writes, elapsed), scoped memory with shared pool support, artifact collection.

5. **AgentExecutor** (`agents/executor.py`): Spawn/stop/kill/kill_all with tier validation (agent tier ≤ user tier), concurrency limits, transactional spawn (rollback on on_start failure), event emission.

6. **A2AProtocol** (`agents/communication.py`): Task-based messaging over event bus — send_task/send_result/send_error/send_status, asyncio.Future-based wait_for_result with timeout, query_capabilities deferred to v2.

7. **TaskDecomposer** (`agents/decomposer.py`): LLM-driven decomposition with heuristic fallback, keyword-based agent selection.

8. **AgentOrchestrator** (`agents/orchestrator.py`): Workflow lifecycle — decompose → spawn → assign → execute → collect → status. v1 synchronous execution. Delegation handler is v1 stub (TODO for depth-limited delegation in v2).

9. **AgentToolBridge** (`agents/bridge.py`) & **Cloning** (`agents/cloning.py`): Bridge wraps agent as BaseTool (ToolCategory.AGENT). clone_agent() uses Pydantic model_copy.

10. **MCPClientManager** (`agents/mcp_client.py`): Pluggable transport via _do_connect/_do_call_tool override pattern. Connection management, tool cache, event emission.

11. **MCPServer** (`agents/mcp_server.py`): Exposes tools/agents via MCP protocol handlers (initialize, tools/list, tools/call). Agent tools routed through orchestrator.

12. **Built-in Agents**: ResearcherAgent (STANDARD, balanced LLM, SHARED_READWRITE) and CoderAgent (ELEVATED, strong LLM, SHARED_READ).

13. **Gateway Wiring** (`gateway/lifespan.py`): All agent services wired — registry, executor, protocol, decomposer, orchestrator. Built-in agents registered. Kill switch integration (soft_kill → stop_all + kill_all_workflows, hard_kill → kill_all).

14. **Final Verification**: 436 tests passing (344 existing + 92 new), all files under 750 lines, CLAUDE.md updated.

### Architecture decisions to preserve:
- **Orchestrator-centric**: agents never talk directly — all A2A goes through orchestrator via event bus
- **Synthetic ConnectionState**: `connection_id=f"agent:{instance_id}"` for ToolExecutor pipeline compatibility
- **Tier validation**: agent tier ≤ user tier — enforced at spawn time in AgentExecutor
- **v1 synchronous execution**: orchestrator runs tasks sequentially (TODO for async parallel via A2A protocol in v2)
- **v1 delegation stub**: _handle_delegation logs only (TODO for depth-limited sub-agent spawning in v2)
- **query_capabilities**: deferred to v2 (raises NotImplementedError)
- **MCP transport**: pluggable via `_do_connect` / `_do_call_tool` override pattern
- **Test split**: test_agents.py (Part 1: models→A2A, 699 lines) + test_agents_advanced.py (Part 2: decomposer→integration)

### Module structure (all files implemented):
```
backend/nobla/agents/
├── __init__.py          # Lazy imports
├── models.py            # AgentConfig, AgentTask, AgentMessage, WorkflowState, enums
├── base.py              # BaseAgent ABC
├── registry.py          # AgentRegistry
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

### What to do next — choose one:

**Option A: Phase 6 v2 enhancements (async parallel, delegation, capability discovery)**
- Make orchestrator execute tasks in parallel via A2A protocol + wait_for_result
- Implement depth-limited delegation in _handle_delegation
- Implement query_capabilities request/response pattern
- Add real MCP transport (stdio/SSE) to MCPClientManager

**Option B: Phase 4E — Flutter Tool UI (design complete, 12-task plan ready)**
- Screen mirror widget, activity feed, tool browser, approval dialog redesign
- Plan at `docs/superpowers/plans/2026-03-27-phase4e-flutter-tool-ui.md`

**Option C: Phase 5 — Remaining channel adapters (WhatsApp, Slack, Signal, Teams, etc.)**
- 15 platform adapters following the Telegram/Discord pattern

**Option D: Phase 6 — Webhooks & Workflows**
- Receive and process external events
- Multi-step workflow builder in natural language

### Test commands:
```bash
# Run all agent tests (92 tests)
cd backend && pytest tests/test_agents.py tests/test_agents_advanced.py -v

# Run full suite (436 tests)
pytest tests/test_telegram.py tests/test_discord_adapter.py tests/test_scheduler.py tests/test_channels.py tests/test_event_bus.py tests/test_skills.py tests/test_agents.py tests/test_agents_advanced.py -v

# Verify line counts
wc -l backend/nobla/agents/*.py backend/nobla/agents/builtins/*.py
```

### Key files to read first:
- `CLAUDE.md` — Full project guide with all phase status
- `backend/nobla/agents/orchestrator.py` — Central workflow coordinator
- `backend/nobla/agents/executor.py` — Agent lifecycle management
- `backend/nobla/agents/communication.py` — A2A protocol with Future-based wait
- `backend/nobla/gateway/lifespan.py` — Where all services are wired
- `backend/nobla/events/bus.py` — Event bus backbone

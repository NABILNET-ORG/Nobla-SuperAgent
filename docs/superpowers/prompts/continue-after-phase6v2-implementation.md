# Continuation Prompt — After Phase 6 v2 Multi-Agent System Enhancement

**Paste this into a new Claude Code session to continue development.**

---

## Context

Nobla Agent is on `main`. **586 tests passing (85 Flutter + 501 backend).**

### What was just completed:

**Phase 6 v2 — Async Parallel Orchestration & Real MCP Transport (10 tasks, all complete):**

1. **Task dependency model** (`agents/models.py`): Added `depends_on: list[str]` field to AgentTask. Implemented `topological_sort_tasks()` using Kahn's algorithm — groups tasks into execution tiers where each tier can run in parallel. Validates missing refs and detects cycles.

2. **Decomposer dependency awareness** (`agents/decomposer.py`): Updated LLM prompt to request `id` and `depends_on` fields per task. Two-pass parsing: first pass maps LLM-assigned ids to real UUIDs, second pass resolves dependency references. Heuristic fallback produces independent (parallel) tasks.

3. **Parallel orchestrator** (`agents/orchestrator.py`): Rewrote `run_workflow()` to sort tasks via `topological_sort_tasks()`, then execute each tier concurrently with `asyncio.gather()`. Tasks with failed dependencies are cascade-marked as FAILED and skipped. Extracted `_resolve_agent()` and `_execute_task()` helpers. Added protocol lifecycle events (`send_task`/`send_result`/`send_error`). Added `depth` parameter for delegation support.

4. **Depth-limited delegation** (`agents/orchestrator.py`): Implemented full `_handle_delegation()` — finds parent workflow depth via `_find_agent_depth()`, checks `depth + 1 < max_workflow_depth`, inherits user context via `_find_agent_context()`, spawns sub-workflow with incremented depth. Replaces the v1 stub that only logged.

5. **Capability discovery** (`agents/communication.py`, `agents/base.py`): Implemented `query_capabilities()` in A2AProtocol using Future pattern over event bus (`agent.a2a.capability.query`/`response`). Added `_pending_caps` dict and `_on_capability_response()` handler. Added `get_capabilities()` method to BaseAgent returning name, role, tools, tier info.

6. **MCP stdio transport** (`agents/mcp_client.py`): `StdioTransport` class — spawns subprocess via `asyncio.create_subprocess_exec`, newline-delimited JSON-RPC 2.0 framing, async `_read_loop()` resolving pending Futures, `send_notification()` for one-way messages, graceful `close()` with terminate/kill fallback.

7. **MCP SSE transport** (`agents/mcp_client.py`): `SSETransport` class — httpx async client, `_sse_loop()` reads Server-Sent Events stream, discovers message endpoint from `endpoint` event, POST for requests, SSE for responses, URL resolution for relative endpoints, `_handle_message()` resolves Futures.

8. **MCP Server endpoints** (`agents/mcp_server.py`): Added `create_router()` returning FastAPI APIRouter. `GET /mcp/sse` — SSE stream per client with keepalive, sends endpoint URL on connect. `POST /mcp/message` — receives JSON-RPC 2.0, dispatches to `initialize`/`tools/list`/`tools/call` handlers, pushes response via SSE. Client tracking with `_clients: dict[str, asyncio.Queue]`.

9. **Tests** (`tests/test_agents_phase6v2.py`): 56 new tests covering all v2 features — topological sort (8), decomposer deps (4), parallel orchestrator (5), delegation (6), capability discovery (4), StdioTransport (4), SSETransport (6), MCP server dispatch (8), MCP client transport (6), AgentTask.depends_on (3). Plus 2 helper classes.

10. **Gateway wiring + docs** (`gateway/lifespan.py`, `CLAUDE.md`): MCP server router mounted via `app.include_router(mcp_server.create_router())` when `settings.agents.mcp_server.enabled`. Gated behind existing `settings.agents.enabled` check. CLAUDE.md, README.md, backend/README.md, Plan.md all updated.

### Architecture decisions to preserve:
- **Topological sort tiers**: Tasks grouped by dependency depth — tasks within same tier run via `asyncio.gather()`, tiers execute sequentially
- **Cascade failure**: If task A fails, all tasks with `depends_on` containing A are auto-marked FAILED without spawning
- **LLM id→UUID mapping**: Decomposer uses two-pass: first creates tasks (maps LLM short ids like "t1" to real UUIDs), second resolves `depends_on` refs
- **Protocol lifecycle**: `_execute_task()` calls `send_task` before execution and `send_result`/`send_error` after — full event bus observability
- **Delegation depth check**: `_find_agent_depth()` scans `_active_workflows` for the assigning agent's instance_id, rejects if `depth + 1 >= max_workflow_depth`
- **Context inheritance**: Delegated sub-workflows inherit `user_id` and `user_tier` from parent workflow
- **Capability Future pattern**: Same pattern as `wait_for_result()` — correlation_id `"cap-{sender}-{recipient}"`, stored in `_pending_caps`
- **Transport abstraction**: `MCPTransport` ABC with `send_request()`/`send_notification()`/`close()`. StdioTransport and SSETransport are concrete implementations
- **Stdio**: Newline-delimited JSON-RPC 2.0, `_read_loop` task auto-resolves Futures by matching request id
- **SSE client**: httpx `stream("GET", "/sse")` for events, `POST /message` for requests, endpoint discovered from first SSE `endpoint` event
- **SSE server**: Per-client `asyncio.Queue[str]`, 30s keepalive ping, client cleanup on disconnect
- **Mock fallback**: Unknown transport type in `_do_connect` returns mock MCPConnection (backward compatible with tests)
- **MCP handshake**: All real transports do `initialize` request + `notifications/initialized` notification + `tools/list` discovery

### Module structure (modified files):
```
backend/nobla/agents/
├── models.py              # +depends_on field, +topological_sort_tasks()
├── decomposer.py          # Updated prompt, two-pass dep resolution
├── orchestrator.py        # Parallel tiers, _execute_task, _resolve_agent, delegation, depth helpers
├── communication.py       # +query_capabilities, +_pending_caps, +_on_capability_response
├── base.py                # +get_capabilities()
├── mcp_client.py          # +MCPTransport ABC, +StdioTransport, +SSETransport, transport dispatch
└── mcp_server.py          # +dispatch(), +create_router(), +client tracking, +FastAPI SSE/message endpoints

backend/nobla/gateway/
└── lifespan.py            # +MCP server router wiring (gated on settings)

backend/tests/
└── test_agents_phase6v2.py # 56 new tests (NEW FILE)
```

### What to do next — choose one:

**Option A: Phase 5 — Remaining channel adapters (WhatsApp, Slack, Signal, Teams, etc.)**
- 15 platform adapters following the Telegram/Discord pattern

**Option B: Phase 6 — Webhooks & Workflows**
- Receive and process external events
- Multi-step workflow builder in natural language

**Option C: Phase 7 — Full Feature Set**
- Media, finance, health, social, smart home tools

**Option D: MCP marketplace**
- Discover and install MCP servers
- Community MCP server registry

### Test commands:
```bash
# Run all Flutter tests (85 tests)
cd app && flutter test

# Run all backend tests (501 tests)
cd backend && pytest tests/ -v

# Run agent tests only (148 tests)
cd backend && pytest tests/test_agents.py tests/test_agents_advanced.py tests/test_agents_phase6v2.py -v

# Run flutter analyze
cd app && flutter analyze

# Verify line counts (750-line limit)
wc -l backend/nobla/agents/*.py backend/nobla/agents/builtins/*.py
```

### Key files to read first:
- `CLAUDE.md` — Full project guide with all phase status
- `backend/nobla/agents/orchestrator.py` — Parallel orchestrator with delegation
- `backend/nobla/agents/models.py` — AgentTask.depends_on + topological_sort_tasks()
- `backend/nobla/agents/communication.py` — A2A protocol + capability discovery
- `backend/nobla/agents/mcp_client.py` — Transport abstraction (StdioTransport, SSETransport)
- `backend/nobla/agents/mcp_server.py` — FastAPI SSE/message endpoints
- `backend/nobla/agents/decomposer.py` — Dependency-aware task decomposition
- `backend/nobla/gateway/lifespan.py` — Multi-agent + MCP server wiring
- `backend/nobla/config/settings.py` — MCPServerSettings (enabled, host, port)

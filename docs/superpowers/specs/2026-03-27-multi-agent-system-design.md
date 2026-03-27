# Multi-Agent System Design — Phase 6

**Date:** 2026-03-27
**Status:** Approved
**Approach:** Orchestrator-Centric (Approach A)

## Overview

A full multi-agent framework for Nobla Agent: agent definition, registry, execution, orchestration, task-based A2A protocol, configurable memory isolation, bidirectional MCP integration, and 2-3 reference agents. All communication flows through a central orchestrator via the event bus.

## Scope

- **Agent framework:** BaseAgent ABC, AgentRegistry, AgentExecutor
- **Orchestration:** AgentOrchestrator with LLM-driven task decomposition
- **A2A protocol:** Task-based messaging (assign/result/status/error) over NoblaEventBus
- **Memory isolation:** Per-agent workspaces, configurable shared pools (FULL_ISOLATED / SHARED_READ / SHARED_READWRITE)
- **MCP:** Client (consume external MCP servers) + Server (expose Nobla tools/agents)
- **Built-in agents:** Researcher, Coder as reference implementations
- **Constraints:** 750-line file limit, 4-tier security, event-driven, sandbox execution

## Module Structure

```
backend/nobla/agents/
├── __init__.py          # Lazy imports (same pattern as channels)
├── models.py            # AgentConfig, AgentTask, AgentMessage, AgentStatus enums
├── base.py              # BaseAgent ABC
├── registry.py          # AgentRegistry (register/discover/query agents)
├── executor.py          # AgentExecutor (run agent in isolated context)
├── orchestrator.py      # AgentOrchestrator (lifecycle, delegation, workflow coordination)
├── workspace.py         # AgentWorkspace (isolated memory + tool scope per agent)
├── communication.py     # A2A protocol (task-based message routing via event bus)
├── cloning.py           # Agent instance spawning (from config templates)
├── bridge.py            # AgentToolBridge (expose agent as a BaseTool)
├── mcp_client.py        # MCP client (consume external MCP servers)
├── mcp_server.py        # MCP server (expose Nobla tools/agents to external clients)
└── builtins/
    ├── __init__.py
    ├── researcher.py    # Reference: web search, summarize, extract
    └── coder.py         # Reference: code generation, debugging, review
```

## Section 1: Models (`models.py`)

### AgentConfig

Pydantic model defining an agent type:

- `name: str` — unique agent type name (e.g. "researcher")
- `description: str` — what this agent does
- `role: str` — system prompt / role instruction
- `llm_tier: str` — preferred LLM tier ("cheap" / "balanced" / "strong")
- `allowed_tools: list[str]` — tool whitelist
- `requires_approval: bool` — whether spawning needs user approval
- `max_concurrent_tasks: int` — per-instance task limit
- `default_isolation: IsolationLevel` — workspace isolation default
- `resource_limits: ResourceLimits` — token/call/time caps

### AgentTask

The A2A unit of work:

- `task_id: str` — UUID
- `parent_task_id: str | None` — for sub-task tracking
- `workflow_id: str` — groups tasks in a workflow
- `assigner: str` — who assigned (orchestrator ID or agent instance_id)
- `assignee: str` — target agent instance_id
- `instruction: str` — what to do
- `status: TaskStatus` — PENDING / RUNNING / COMPLETED / FAILED / CANCELLED
- `artifacts: list[dict]` — output results
- `created_at: datetime`
- `deadline: datetime | None`
- `retry_count: int`

### AgentMessage

Envelope for A2A communication:

- `message_type: MessageType` — TASK_ASSIGN / TASK_UPDATE / TASK_RESULT / TASK_ERROR / CAPABILITY_QUERY / CAPABILITY_RESPONSE
- `sender: str` — instance_id
- `recipient: str` — instance_id
- `task: AgentTask | None` — task reference
- `payload: dict` — additional data
- `correlation_id: str` — for tracing

### Enums

- `AgentStatus`: IDLE, BUSY, PAUSED, STOPPED, ERROR
- `TaskStatus`: PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
- `IsolationLevel`: FULL_ISOLATED, SHARED_READ, SHARED_READWRITE
- `MessageType`: TASK_ASSIGN, TASK_UPDATE, TASK_RESULT, TASK_ERROR, CAPABILITY_QUERY, CAPABILITY_RESPONSE

### ResourceLimits

- `max_tool_calls: int = 50`
- `max_llm_tokens: int = 100_000`
- `max_memory_writes: int = 200`
- `max_runtime_seconds: int = 600`

## Section 2: BaseAgent ABC (`base.py`)

```python
class BaseAgent(ABC):
    # Identity
    name: str
    description: str
    role: str

    # Configuration
    config: AgentConfig
    status: AgentStatus
    instance_id: str            # UUID, set by executor at spawn time

    # Injected dependencies
    workspace: AgentWorkspace
    event_bus: NoblaEventBus
    router: LLMRouter

    @abstractmethod
    async def handle_task(self, task: AgentTask) -> AgentTask:
        """Process an assigned task. Return updated task with artifacts/status."""

    async def on_start(self) -> None:
        """Optional hook: called when agent instance starts."""

    async def on_stop(self) -> None:
        """Optional hook: called when agent instance is shutting down."""

    async def think(self, prompt: str) -> str:
        """Send prompt to LLM router with agent's tier preference."""

    async def use_tool(self, tool_name: str, params: dict) -> ToolResult:
        """Execute a tool through workspace's scoped executor."""

    async def delegate(self, instruction: str, target: str | None = None) -> AgentTask:
        """Request orchestrator to assign a sub-task to another agent."""

    async def report(self, task: AgentTask, artifacts: list[dict]) -> None:
        """Report task completion with artifacts back to orchestrator."""
```

### Lifecycle

```
AgentConfig → Executor.spawn() → instance_id assigned
    → workspace created → on_start() → status = IDLE
    → orchestrator assigns tasks via handle_task()
    → agent calls think(), use_tool(), delegate()
    → reports results via report()
    → on_stop() → workspace cleaned up
```

### Design decisions

- `handle_task` is the single entry point — simple, testable
- `think()` and `use_tool()` are convenience methods, not abstract
- `delegate()` goes through orchestrator (Approach A), never direct
- Dependencies injected by executor at spawn time

## Section 3: AgentRegistry & AgentExecutor

### AgentRegistry (`registry.py`)

Mirrors ToolRegistry. Manages agent type definitions (classes + default configs).

- `register(agent_cls, config, allow_overwrite=False)` — register agent type
- `unregister(name)` — remove agent type
- `get(name)` — look up class + config
- `list_all()` — all registered configs
- `list_by_role(keyword)` — search by role description
- `get_manifest()` — for LLM function-calling and MCP

### AgentExecutor (`executor.py`)

Spawns and manages running agent instances.

Constructor dependencies: `AgentRegistry`, `ToolRegistry`, `ToolExecutor`, `NoblaEventBus`, `LLMRouter`, `MemoryOrchestrator | None`, `max_concurrent_agents=10`.

- `spawn(agent_name, config_overrides=None, parent_id=None)` — transactional: look up class, apply overrides, create workspace, instantiate, inject deps, assign instance_id, call on_start(), emit `agent.spawned`
- `stop(instance_id, reason)` — graceful: set STOPPED, cancel tasks, on_stop(), cleanup workspace, emit `agent.stopped`
- `kill(instance_id)` — immediate termination for kill switch, no hooks
- `get(instance_id)` — look up running instance
- `list_running()` — all instances with status
- `stop_all()` — gateway shutdown

### Design decisions

- Registry holds classes, executor holds instances — clean separation
- Semaphore-based concurrency limit (`max_concurrent_agents`)
- `spawn()` is transactional — rollback on failure, emit `agent.spawn_failed`
- `kill()` bypasses hooks — for security kill switch
- `parent_id` tracking for sub-agent trees
- Config overrides at spawn time for workflow-specific tuning

## Section 4: A2A Protocol & AgentOrchestrator

### A2AProtocol (`communication.py`)

Task-based messaging over event bus.

Event types:
- `agent.a2a.task.assign` — orchestrator → agent
- `agent.a2a.task.result` — agent → orchestrator
- `agent.a2a.task.status` — progress update
- `agent.a2a.task.error` — failure report
- `agent.a2a.capability.*` — discovery
- `agent.spawned` / `agent.stopped` — lifecycle
- `agent.task.delegate` — agent requests sub-task delegation

Methods:
- `send_task(sender, recipient, task)` — assign
- `send_result(sender, task)` — complete
- `send_status(sender, task)` — progress
- `send_error(sender, task, error)` — failure
- `query_capabilities(sender, recipient)` — discovery
- `wait_for_result(task_id, timeout=300)` — asyncio.Future pattern (from confirmation.py)

### AgentOrchestrator (`orchestrator.py`)

Central coordination. Constructor: `AgentExecutor`, `A2AProtocol`, `LLMRouter`, `NoblaEventBus`, `ToolRegistry`, `max_workflow_depth=5`, `max_tasks_per_workflow=20`.

Main entry: `run_workflow(instruction, user_id, agent_team=None)`:
1. LLM decomposes instruction into task graph
2. Select/spawn agents (explicit team or auto-select)
3. Assign root tasks via A2A protocol
4. Monitor progress, handle delegation requests
5. Collect artifacts, assemble final result
6. Clean up: stop spawned agents, close workflow

Event handlers:
- `handle_delegation(event)` — check depth limit, select agent, spawn if needed, assign
- `handle_result(event)` — update state, unblock dependents, finalize if done
- `handle_error(event)` — retry policy (1 retry default), reassign or escalate
- `kill_workflow(workflow_id)` — emergency stop, kill switch integration

### WorkflowState

```python
@dataclass
class WorkflowState:
    workflow_id: str
    user_id: str
    instruction: str
    task_graph: dict[str, AgentTask]
    agent_assignments: dict[str, str]  # task_id -> instance_id
    status: str                         # running / completed / failed / cancelled
    depth: int
    created_at: datetime
```

### Design decisions

- LLM-driven decomposition, not hardcoded logic
- Workflow depth limit (5) prevents infinite delegation
- Task count limit (20) for cost protection
- asyncio.Future for wait_for_result (event-driven, not polling)
- Auto-select vs explicit team
- Failed tasks get 1 retry on different instance before user escalation
- kill_workflow wired to existing security kill switch

## Section 5: AgentWorkspace & Memory Isolation

### AgentWorkspace (`workspace.py`)

Scoped execution environment per agent instance. Created by executor at spawn, cleaned up on stop.

**Tool execution:**
- `execute_tool(tool_name, params)` — whitelist check → inject workspace context → delegate to ToolExecutor → track usage → emit `agent.tool.used`
- `available_tools()` — whitelisted tool names

**Memory (scoped):**
- `store(key, value, layer="episodic")` — write to `agent:{instance_id}:{key}`
- `recall(query, layer=None)` — search own scope; if SHARED_READ/READWRITE, also search shared pools
- `store_shared(pool, key, value)` — write to shared pool (SHARED_READWRITE only)

**Artifacts:**
- `add_artifact(artifact)` — collect output
- `get_artifacts()` — all artifacts

**Resources:**
- `usage()` — tool_calls, llm_tokens, memory_writes, elapsed_time
- `within_limits()` — check against ResourceLimits

**Cleanup:**
- `cleanup()` — FULL_ISOLATED: delete agent scope. Shared: leave shared pools. Emit `agent.workspace.cleaned`

### Isolation levels

| Level | Own Memory | Shared Read | Shared Write | Cleanup |
|-------|-----------|-------------|--------------|---------|
| FULL_ISOLATED | R/W | No | No | Delete all |
| SHARED_READ | R/W | Yes | No | Delete own |
| SHARED_READWRITE | R/W | Yes | Yes | Delete own |

### Shared pool lifecycle

1. Orchestrator creates workflow-scoped pool at workflow start
2. Agents with SHARED_READ/READWRITE get pool ID in WorkspaceConfig
3. Researcher stores findings → coder reads them
4. Pool cleaned up when workflow completes

### Design decisions

- Tool whitelist enforced at workspace level (defense in depth)
- Resource limits are hard caps, checked before every operation
- Memory scope namespacing prevents collision
- Shared pools opt-in per workflow
- Artifacts separate from memory (return value vs scratch space)

## Section 6: MCP Integration

### MCPClientManager (`mcp_client.py`)

Manages connections to external MCP servers.

- `connect(server_uri, transport="stdio", auth=None)` — handshake, discover tools, cache, return connection_id
- `disconnect(connection_id)` — graceful close
- `call_tool(connection_id, tool_name, arguments)` — invoke remote tool with timeout
- `list_tools(connection_id)` — available tools (cached)
- `list_connections()` — all active with health
- `health_check(connection_id)` — ping, reconnect if stale
- `disconnect_all()` — gateway shutdown

Transports: stdio, SSE, HTTP.

### MCPServer (`mcp_server.py`)

Exposes Nobla tools/agents as MCP server.

- `start()` — build manifest, register handlers, listen on SSE
- `stop()` — close sessions
- `expose_tool(tool_name)` / `hide_tool(tool_name)` — opt-in exposure
- `expose_agent(agent_name)` — agent appears as MCP tool to external clients

Protocol handlers:
- `handle_initialize(params)` — server info + capabilities
- `handle_tools_list()` — exposed tools + agents
- `handle_tools_call(tool_name, arguments, client_id)` — route to ToolExecutor or AgentOrchestrator
- `handle_resources_list()` — optional: memory/knowledge as MCP resources

### Integration flow

External client → MCPServer → handle_tools_call → ToolExecutor or orchestrator.run_workflow → result

Agent → workspace.execute_tool("external.tool") → MCPClientManager.call_tool → external MCP server → result

### Settings

```python
class MCPClientSettings(BaseModel):
    enabled: bool = False
    max_connections: int = 20
    default_timeout: float = 30.0
    allowed_servers: list[str] = []    # empty = allow all

class MCPServerSettings(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8100
    transport: str = "sse"
    require_auth: bool = True
    default_tier: str = "STANDARD"
    exposed_tools: list[str] = []
    exposed_agents: list[str] = []
```

### Design decisions

- Explicit opt-in exposure (not all tools should be external)
- MCP requests get STANDARD tier by default — security non-negotiable
- Agents exposed as MCP tools — external clients see a simple tool interface
- Client manager is agent-agnostic — any component can request connections
- Server URI allowlist for client connections
- Protocol implemented directly (simple JSON-RPC), can swap in SDK later

## Section 7: Built-in Agents

### ResearcherAgent (`builtins/researcher.py`)

- **Role:** Web search, document analysis, information extraction, summarization
- **Tools:** search.web, search.knowledge, memory read/write
- **LLM tier:** balanced (medium tasks)
- **Isolation:** SHARED_READWRITE (shares findings with team)

### CoderAgent (`builtins/coder.py`)

- **Role:** Code generation, debugging, code review, git operations
- **Tools:** code.run, code.generate, code.debug, git.ops
- **LLM tier:** strong (hard tasks — code generation)
- **Isolation:** SHARED_READ (reads researcher findings, doesn't write back)

Both serve as reference implementations and templates for user-defined agents.

## Section 8: Gateway Wiring

Services initialized in gateway lifespan after existing services:

```python
# After event_bus, router, tool_registry, tool_executor...
agent_registry = AgentRegistry(event_bus=event_bus)
agent_executor = AgentExecutor(
    registry=agent_registry, tool_registry=tool_registry,
    tool_executor=tool_executor, event_bus=event_bus,
    router=router, memory_orchestrator=memory_orchestrator,
)
a2a_protocol = A2AProtocol(event_bus=event_bus)
orchestrator = AgentOrchestrator(
    executor=agent_executor, protocol=a2a_protocol,
    router=router, event_bus=event_bus, tool_registry=tool_registry,
)

# Register built-in agents
agent_registry.register(ResearcherAgent, researcher_config)
agent_registry.register(CoderAgent, coder_config)

# MCP (if enabled)
if settings.mcp_client.enabled:
    mcp_client = MCPClientManager(event_bus=event_bus)
if settings.mcp_server.enabled:
    mcp_server = MCPServer(tool_registry=tool_registry, ...)
    await mcp_server.start()

await orchestrator.start()
```

## Event Types Summary

| Event | Source | Description |
|-------|--------|-------------|
| `agent.spawned` | executor | New instance started |
| `agent.stopped` | executor | Instance shut down |
| `agent.spawn_failed` | executor | Spawn rolled back |
| `agent.a2a.task.assign` | orchestrator/protocol | Task assigned |
| `agent.a2a.task.result` | protocol | Task completed |
| `agent.a2a.task.status` | protocol | Progress update |
| `agent.a2a.task.error` | protocol | Task failed |
| `agent.a2a.capability.*` | protocol | Discovery |
| `agent.task.delegate` | agent | Delegation request |
| `agent.tool.used` | workspace | Agent used a tool |
| `agent.workspace.cleaned` | workspace | Workspace torn down |
| `mcp.client.connected` | mcp_client | Connected to external server |
| `mcp.client.disconnected` | mcp_client | Disconnected |
| `mcp.client.tool_called` | mcp_client | Invoked external tool |
| `mcp.server.started` | mcp_server | Server listening |
| `mcp.server.tool_called` | mcp_server | External client invoked tool |

## Testing Strategy

- Unit tests per module (models, base, registry, executor, workspace, communication, orchestrator, mcp_client, mcp_server, bridge, builtins)
- Mock LLMRouter, ToolExecutor, MemoryOrchestrator, EventBus where needed
- Integration tests: full workflow (orchestrator → spawn → assign → result → cleanup)
- Target: 90%+ coverage (security-critical)
- Expected: ~120-150 tests

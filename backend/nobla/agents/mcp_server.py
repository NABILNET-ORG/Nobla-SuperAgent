"""MCPServer — expose Nobla tools/agents as MCP server (Phase 6).

External clients connect via SSE and invoke Nobla capabilities.
Tools are opt-in via expose_tool()/expose_agent().
Serves HTTP+SSE transport via FastAPI router.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

from nobla.security.permissions import Tier

if TYPE_CHECKING:
    from nobla.agents.orchestrator import AgentOrchestrator
    from nobla.agents.registry import AgentRegistry
    from nobla.events.bus import NoblaEventBus
    from nobla.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class MCPServer:
    """Exposes Nobla tools and agents as an MCP-compliant server."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        agent_registry: AgentRegistry,
        orchestrator: AgentOrchestrator,
        event_bus: NoblaEventBus | None = None,
        host: str = "127.0.0.1",
        port: int = 8100,
        default_tier: Tier = Tier.STANDARD,
    ) -> None:
        self._tool_registry = tool_registry
        self._agent_registry = agent_registry
        self._orchestrator = orchestrator
        self._event_bus = event_bus
        self._host = host
        self._port = port
        self._default_tier = default_tier
        self._exposed_tools: set[str] = set()
        self._exposed_agents: set[str] = set()

        self._clients: dict[str, asyncio.Queue[str]] = {}

    async def start(self) -> None:
        if self._event_bus:
            from nobla.events.models import NoblaEvent
            await self._event_bus.emit(NoblaEvent(
                event_type="mcp.server.started",
                source="mcp.server",
                payload={"host": self._host, "port": self._port},
            ))
        logger.info("mcp_server_started on %s:%d", self._host, self._port)

    async def stop(self) -> None:
        for q in self._clients.values():
            await q.put("")  # signal close
        self._clients.clear()
        logger.info("mcp_server_stopped")

    def expose_tool(self, tool_name: str) -> None:
        self._exposed_tools.add(tool_name)

    def hide_tool(self, tool_name: str) -> None:
        self._exposed_tools.discard(tool_name)

    def expose_agent(self, agent_name: str) -> None:
        self._exposed_agents.add(agent_name)

    # ── MCP Protocol Handlers ──

    async def handle_initialize(self, params: dict) -> dict:
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "nobla-agent", "version": "0.1.0"},
            "capabilities": {"tools": {"listChanged": False}},
        }

    async def handle_tools_list(self) -> list[dict]:
        tools = []
        for name in self._exposed_tools:
            tool = self._tool_registry.get(name)
            if tool:
                tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": {"type": "object", "properties": {}},
                })
        for name in self._exposed_agents:
            entry = self._agent_registry.get(name)
            if entry:
                _, config = entry
                tools.append({
                    "name": f"agent.{config.name}",
                    "description": config.description,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "instruction": {
                                "type": "string",
                                "description": "What to do",
                            },
                        },
                        "required": ["instruction"],
                    },
                })
        return tools

    async def handle_tools_call(
        self, tool_name: str, arguments: dict, client_id: str,
    ) -> dict:
        # Check if it's an agent
        if tool_name.startswith("agent."):
            agent_name = tool_name[len("agent."):]
            if agent_name not in self._exposed_agents:
                return {"success": False, "error": f"Agent '{agent_name}' not exposed"}
            try:
                workflow = await self._orchestrator.run_workflow(
                    instruction=arguments.get("instruction", ""),
                    user_id=f"mcp:{client_id}",
                    user_tier=self._default_tier,
                    agent_team=[agent_name],
                )
                artifacts = []
                for task in workflow.task_graph.values():
                    artifacts.extend(task.artifacts)
                return {
                    "success": workflow.status == "completed",
                    "workflow_id": workflow.workflow_id,
                    "artifacts": artifacts,
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

        # Regular tool
        if tool_name not in self._exposed_tools:
            return {"success": False, "error": f"Tool '{tool_name}' not exposed"}

        return {"success": False, "error": "Direct tool execution via MCP not yet implemented"}

    # ── JSON-RPC dispatch ──

    async def dispatch(
        self, method: str, params: dict, client_id: str,
    ) -> dict[str, Any]:
        """Route a JSON-RPC method to the appropriate handler."""
        if method == "initialize":
            return await self.handle_initialize(params)
        if method == "tools/list":
            return {"tools": await self.handle_tools_list()}
        if method == "tools/call":
            return await self.handle_tools_call(
                params.get("name", ""),
                params.get("arguments", {}),
                client_id,
            )
        return {"error": {"code": -32601, "message": f"Unknown method: {method}"}}

    def _send_to_client(self, client_id: str, msg: dict) -> None:
        q = self._clients.get(client_id)
        if q is not None:
            q.put_nowait(json.dumps(msg))

    # ── FastAPI router ──

    def create_router(self) -> Any:
        """Return a FastAPI APIRouter with /sse and /message endpoints."""
        from fastapi import APIRouter, Request
        from fastapi.responses import StreamingResponse

        router = APIRouter(prefix="/mcp", tags=["mcp"])

        @router.get("/sse")
        async def sse_endpoint(request: Request) -> StreamingResponse:
            client_id = str(uuid.uuid4())
            queue: asyncio.Queue[str] = asyncio.Queue()
            self._clients[client_id] = queue

            async def event_stream():
                # First event: tell client where to POST messages
                yield (
                    f"event: endpoint\n"
                    f"data: /mcp/message?client_id={client_id}\n\n"
                )
                try:
                    while True:
                        if await request.is_disconnected():
                            break
                        try:
                            data = await asyncio.wait_for(
                                queue.get(), timeout=30,
                            )
                        except asyncio.TimeoutError:
                            yield ": keepalive\n\n"
                            continue
                        if not data:
                            break
                        yield f"event: message\ndata: {data}\n\n"
                finally:
                    self._clients.pop(client_id, None)

            return StreamingResponse(
                event_stream(), media_type="text/event-stream",
            )

        @router.post("/message")
        async def message_endpoint(
            request: Request, client_id: str = "",
        ) -> dict:
            body = await request.json()
            req_id = body.get("id")
            method = body.get("method", "")
            params = body.get("params", {})

            result = await self.dispatch(method, params, client_id)

            # Notifications have no id — no response needed
            if req_id is None:
                return {"jsonrpc": "2.0", "result": "ok"}

            response = {"jsonrpc": "2.0", "id": req_id}
            if "error" in result and isinstance(result["error"], dict):
                response["error"] = result["error"]
            else:
                response["result"] = result

            # Also push via SSE stream
            self._send_to_client(client_id, response)
            return response

        return router

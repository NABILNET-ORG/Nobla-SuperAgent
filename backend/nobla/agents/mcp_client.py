"""MCPClientManager — consume external MCP servers (Phase 6).

Manages connections, tool discovery, and tool invocation.
Actual transport implementation is pluggable via _do_connect / _do_call_tool.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nobla.events.bus import NoblaEventBus

logger = logging.getLogger(__name__)


@dataclass
class MCPToolDef:
    name: str
    description: str
    input_schema: dict
    connection_id: str


@dataclass
class MCPConnection:
    connection_id: str
    server_uri: str
    transport: str
    server_info: dict
    capabilities: dict
    status: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MCPClientManager:
    """Manages connections to external MCP servers."""

    def __init__(
        self,
        event_bus: NoblaEventBus | None = None,
        max_connections: int = 20,
    ) -> None:
        self._event_bus = event_bus
        self._max_connections = max_connections
        self._connections: dict[str, MCPConnection] = {}
        self._tool_cache: dict[str, list[MCPToolDef]] = {}

    async def connect(
        self,
        server_uri: str,
        transport: str = "stdio",
        auth: dict | None = None,
    ) -> str:
        if len(self._connections) >= self._max_connections:
            raise RuntimeError(
                f"Max MCP connections ({self._max_connections}) reached"
            )
        conn = await self._do_connect(server_uri, transport, auth)
        self._connections[conn.connection_id] = conn

        if self._event_bus is not None:
            from nobla.events.models import NoblaEvent
            await self._event_bus.emit(NoblaEvent(
                event_type="mcp.client.connected",
                source="mcp.client",
                payload={
                    "connection_id": conn.connection_id,
                    "server_uri": server_uri,
                },
            ))
        return conn.connection_id

    async def disconnect(self, connection_id: str) -> None:
        conn = self._connections.pop(connection_id, None)
        if conn is None:
            return
        self._tool_cache.pop(connection_id, None)
        if self._event_bus is not None:
            from nobla.events.models import NoblaEvent
            await self._event_bus.emit(NoblaEvent(
                event_type="mcp.client.disconnected",
                source="mcp.client",
                payload={"connection_id": connection_id},
            ))

    async def disconnect_all(self) -> None:
        for cid in list(self._connections.keys()):
            await self.disconnect(cid)

    async def call_tool(
        self, connection_id: str, tool_name: str, arguments: dict,
    ) -> dict:
        if connection_id not in self._connections:
            raise ValueError(f"MCP connection '{connection_id}' not found")
        result = await self._do_call_tool(connection_id, tool_name, arguments)

        if self._event_bus is not None:
            from nobla.events.models import NoblaEvent
            await self._event_bus.emit(NoblaEvent(
                event_type="mcp.client.tool_called",
                source="mcp.client",
                payload={
                    "connection_id": connection_id,
                    "tool_name": tool_name,
                },
            ))
        return result

    def list_connections(self) -> list[dict]:
        return [
            {
                "connection_id": c.connection_id,
                "server_uri": c.server_uri,
                "status": c.status,
            }
            for c in self._connections.values()
        ]

    async def list_tools(self, connection_id: str) -> list[MCPToolDef]:
        return self._tool_cache.get(connection_id, [])

    # ── Transport layer (override for real implementation) ──

    async def _do_connect(
        self, server_uri: str, transport: str, auth: dict | None,
    ) -> MCPConnection:
        """Perform MCP handshake. Override for real transport."""
        return MCPConnection(
            connection_id=str(uuid.uuid4()),
            server_uri=server_uri,
            transport=transport,
            server_info={"name": "unknown"},
            capabilities={},
            status="connected",
        )

    async def _do_call_tool(
        self, connection_id: str, tool_name: str, arguments: dict,
    ) -> dict:
        """Invoke tool on MCP server. Override for real transport."""
        raise NotImplementedError("MCP transport not configured")

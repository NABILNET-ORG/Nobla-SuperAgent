"""MCPClientManager — consume external MCP servers (Phase 6).

Manages connections, tool discovery, and tool invocation.
Supports stdio and SSE transports via JSON-RPC 2.0.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from nobla.events.bus import NoblaEventBus

logger = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2024-11-05"


# ── Transport layer ──


class MCPTransport(ABC):
    """Base transport for JSON-RPC 2.0 MCP communication."""

    @abstractmethod
    async def send_request(
        self, method: str, params: dict | None = None,
    ) -> dict:
        ...

    async def send_notification(
        self, method: str, params: dict | None = None,
    ) -> None:
        """Send a one-way notification (no response expected)."""

    async def close(self) -> None:
        """Release transport resources."""


class StdioTransport(MCPTransport):
    """JSON-RPC 2.0 over subprocess stdin/stdout (newline-delimited)."""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._proc = process
        self._req_id = 0
        self._pending: dict[int, asyncio.Future[dict]] = {}
        self._reader: asyncio.Task[None] | None = None

    @classmethod
    async def spawn(
        cls,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> StdioTransport:
        proc = await asyncio.create_subprocess_exec(
            command, *(args or []),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        transport = cls(proc)
        transport._reader = asyncio.create_task(transport._read_loop())
        return transport

    async def send_request(
        self, method: str, params: dict | None = None,
    ) -> dict:
        self._req_id += 1
        rid = self._req_id
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params

        assert self._proc.stdin is not None  # noqa: S101
        self._proc.stdin.write(json.dumps(msg).encode() + b"\n")
        await self._proc.stdin.drain()

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict] = loop.create_future()
        self._pending[rid] = future
        return await asyncio.wait_for(future, timeout=30)

    async def send_notification(
        self, method: str, params: dict | None = None,
    ) -> None:
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        assert self._proc.stdin is not None  # noqa: S101
        self._proc.stdin.write(json.dumps(msg).encode() + b"\n")
        await self._proc.stdin.drain()

    async def _read_loop(self) -> None:
        assert self._proc.stdout is not None  # noqa: S101
        try:
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = msg.get("id")
                if rid is not None and rid in self._pending:
                    future = self._pending.pop(rid)
                    if "error" in msg:
                        err = msg["error"]
                        future.set_exception(
                            RuntimeError(err.get("message", "MCP error")),
                        )
                    else:
                        future.set_result(msg.get("result", {}))
        except asyncio.CancelledError:
            pass

    async def close(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
        if self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()


class SSETransport(MCPTransport):
    """MCP over HTTP + Server-Sent Events.

    Client POSTs JSON-RPC requests to *message_endpoint* and reads
    responses from the SSE stream at *server_uri*/sse.
    """

    def __init__(
        self, server_uri: str, auth: dict[str, str] | None = None,
    ) -> None:
        self._base_url = server_uri.rstrip("/")
        self._req_id = 0
        self._pending: dict[int, asyncio.Future[dict]] = {}
        self._message_endpoint: str | None = None
        headers: dict[str, str] = {}
        if auth and auth.get("token"):
            headers["Authorization"] = f"Bearer {auth['token']}"
        self._client = httpx.AsyncClient(headers=headers, timeout=30)
        self._sse_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Connect to SSE stream and discover message endpoint."""
        self._sse_task = asyncio.create_task(self._sse_loop())
        # Wait briefly for the endpoint event
        for _ in range(50):
            if self._message_endpoint is not None:
                return
            await asyncio.sleep(0.1)
        if self._message_endpoint is None:
            raise RuntimeError("SSE stream did not provide message endpoint")

    async def send_request(
        self, method: str, params: dict | None = None,
    ) -> dict:
        if self._message_endpoint is None:
            raise RuntimeError("SSE transport not started")
        self._req_id += 1
        rid = self._req_id
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            body["params"] = params

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict] = loop.create_future()
        self._pending[rid] = future

        resp = await self._client.post(
            self._message_endpoint,
            json=body,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()

        return await asyncio.wait_for(future, timeout=30)

    async def send_notification(
        self, method: str, params: dict | None = None,
    ) -> None:
        if self._message_endpoint is None:
            return
        body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        await self._client.post(
            self._message_endpoint,
            json=body,
            headers={"Content-Type": "application/json"},
        )

    async def _sse_loop(self) -> None:
        """Read the SSE stream, resolve pending futures."""
        try:
            async with self._client.stream(
                "GET", f"{self._base_url}/sse",
            ) as resp:
                event_type = ""
                async for line_bytes in resp.aiter_lines():
                    line = line_bytes.strip()
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data_str = line[5:].strip()
                        if event_type == "endpoint":
                            self._message_endpoint = self._resolve_url(
                                data_str,
                            )
                        elif event_type == "message":
                            self._handle_message(data_str)
                        event_type = ""
        except (httpx.HTTPError, asyncio.CancelledError):
            pass

    def _resolve_url(self, endpoint: str) -> str:
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        return urllib.parse.urljoin(self._base_url, endpoint)

    def _handle_message(self, data_str: str) -> None:
        try:
            msg = json.loads(data_str)
        except json.JSONDecodeError:
            return
        rid = msg.get("id")
        if rid is not None and rid in self._pending:
            future = self._pending.pop(rid)
            if "error" in msg:
                err = msg["error"]
                future.set_exception(
                    RuntimeError(err.get("message", "MCP error")),
                )
            else:
                future.set_result(msg.get("result", {}))

    async def close(self) -> None:
        if self._sse_task is not None:
            self._sse_task.cancel()
        await self._client.aclose()


# ── Data models ──


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
    _transport_obj: MCPTransport | None = field(default=None, repr=False)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


# ── Client manager ──


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
                f"Max MCP connections ({self._max_connections}) reached",
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
        if conn._transport_obj is not None:
            await conn._transport_obj.close()
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

    # ── Transport dispatch ──

    async def _do_connect(
        self, server_uri: str, transport: str, auth: dict | None,
    ) -> MCPConnection:
        """Create transport, perform MCP initialize handshake."""
        transport_obj: MCPTransport | None = None

        if transport == "stdio":
            parts = server_uri.split()
            transport_obj = await StdioTransport.spawn(
                parts[0], args=parts[1:] if len(parts) > 1 else None,
            )
        elif transport == "sse":
            sse = SSETransport(server_uri, auth)
            await sse.start()
            transport_obj = sse

        conn_id = str(uuid.uuid4())

        if transport_obj is None:
            # Fallback: mock connection (tests / unsupported transport)
            return MCPConnection(
                connection_id=conn_id,
                server_uri=server_uri,
                transport=transport,
                server_info={"name": "unknown"},
                capabilities={},
                status="connected",
            )

        # MCP initialize handshake
        result = await transport_obj.send_request("initialize", {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "nobla-agent", "version": "1.0"},
        })
        await transport_obj.send_notification("notifications/initialized")

        conn = MCPConnection(
            connection_id=conn_id,
            server_uri=server_uri,
            transport=transport,
            server_info=result.get("serverInfo", {}),
            capabilities=result.get("capabilities", {}),
            status="connected",
            _transport_obj=transport_obj,
        )

        # Discover tools
        try:
            tools_result = await transport_obj.send_request("tools/list")
            self._tool_cache[conn_id] = [
                MCPToolDef(
                    name=t["name"],
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                    connection_id=conn_id,
                )
                for t in tools_result.get("tools", [])
            ]
        except Exception as exc:
            logger.warning("mcp_tool_discovery_failed: %s", exc)

        return conn

    async def _do_call_tool(
        self, connection_id: str, tool_name: str, arguments: dict,
    ) -> dict:
        """Invoke tool via the connection's transport."""
        conn = self._connections.get(connection_id)
        if conn is None:
            raise ValueError(f"MCP connection '{connection_id}' not found")
        if conn._transport_obj is None:
            raise NotImplementedError("MCP transport not configured")
        return await conn._transport_obj.send_request(
            "tools/call", {"name": tool_name, "arguments": arguments},
        )

"""Phase 4D: SSH Connection Pool.

Manages persistent asyncssh connections with lifecycle controls:
add, get, disconnect, list, halt, prune, reset.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SSHConnection:
    """Metadata for a pooled SSH connection."""

    id: str
    conn: Any  # asyncssh.SSHClientConnection
    host: str
    user: str
    port: int
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    label: str | None = None
    sftp_client: Any | None = None  # asyncssh.SFTPClient


class SSHConnectionPool:
    """Manages persistent SSH sessions with idle/lifetime timeouts."""

    def __init__(self) -> None:
        self._connections: dict[str, SSHConnection] = {}

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    def add(
        self,
        host: str,
        user: str,
        port: int,
        conn: Any,
        *,
        label: str | None = None,
    ) -> str:
        """Register a new connection. Returns its UUID."""
        connection_id = str(uuid.uuid4())
        self._connections[connection_id] = SSHConnection(
            id=connection_id,
            conn=conn,
            host=host,
            user=user,
            port=port,
            label=label,
        )
        return connection_id

    def get(self, connection_id: str) -> SSHConnection:
        """Look up a connection by ID. Raises KeyError if not found."""
        try:
            return self._connections[connection_id]
        except KeyError:
            raise KeyError(
                f"Connection '{connection_id}' not found. "
                "It may have been disconnected or expired."
            )

    async def disconnect(self, connection_id: str) -> SSHConnection:
        """Close and remove a connection. Returns metadata."""
        entry = self.get(connection_id)
        try:
            entry.conn.close()
            await entry.conn.wait_closed()
        except Exception:
            pass  # Connection may already be dead
        del self._connections[connection_id]
        return entry

    def list_connections(self) -> list[dict]:
        """Return sanitised metadata for all active connections."""
        now = time.time()
        return [
            {
                "connection_id": c.id,
                "host": c.host,
                "user": c.user,
                "port": c.port,
                "label": c.label,
                "connected_at": c.created_at,
                "last_activity": c.last_activity,
                "idle_seconds": round(now - c.last_activity, 1),
            }
            for c in self._connections.values()
        ]

    def touch(self, connection_id: str) -> None:
        """Update last_activity timestamp for a connection."""
        entry = self.get(connection_id)
        entry.last_activity = time.time()

    async def halt(self) -> None:
        """Emergency: close ALL connections immediately."""
        for entry in list(self._connections.values()):
            try:
                entry.conn.close()
                await entry.conn.wait_closed()
            except Exception:
                pass
        self._connections.clear()

    async def prune(self, idle_timeout: int, max_lifetime: int) -> int:
        """Remove idle or expired connections. Returns count pruned."""
        now = time.time()
        to_remove: list[str] = []
        for cid, entry in self._connections.items():
            idle = now - entry.last_activity
            age = now - entry.created_at
            if idle > idle_timeout or age > max_lifetime:
                to_remove.append(cid)
        for cid in to_remove:
            await self.disconnect(cid)
        return len(to_remove)

    def reset(self) -> None:
        """Wipe all state without closing connections (tests)."""
        self._connections.clear()


# ---- module-level singleton ----

_pool_instance: SSHConnectionPool | None = None
_pool_override: SSHConnectionPool | None = None


def _get_pool() -> SSHConnectionPool:
    """Return (and cache) the pool singleton."""
    global _pool_instance
    if _pool_override is not None:
        return _pool_override
    if _pool_instance is None:
        _pool_instance = SSHConnectionPool()
    return _pool_instance

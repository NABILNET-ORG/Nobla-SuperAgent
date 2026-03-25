"""Tests for SSHConnectionPool."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.config.settings import RemoteControlSettings


def _make_settings(**overrides) -> RemoteControlSettings:
    defaults = {
        "allowed_hosts": ["host1.example.com"],
        "allowed_users": ["deploy"],
        "max_connections": 3,
        "idle_timeout_s": 300,
        "max_lifetime_s": 3600,
    }
    defaults.update(overrides)
    return RemoteControlSettings(**defaults)


@pytest.fixture(autouse=True)
def _reset_pool():
    from nobla.tools.remote import pool as pool_mod
    pool_mod._pool_instance = None
    pool_mod._pool_override = None
    yield
    pool_mod._pool_instance = None
    pool_mod._pool_override = None


def _mock_asyncssh_conn():
    """Create a mock asyncssh.SSHClientConnection."""
    conn = AsyncMock()
    conn.close = MagicMock()
    conn.wait_closed = AsyncMock()
    return conn


class TestPoolSingleton:
    def test_get_pool_returns_same_instance(self):
        from nobla.tools.remote.pool import _get_pool
        p1 = _get_pool()
        p2 = _get_pool()
        assert p1 is p2

    def test_pool_override_takes_precedence(self):
        from nobla.tools.remote import pool as pool_mod
        from nobla.tools.remote.pool import SSHConnectionPool, _get_pool
        override = SSHConnectionPool()
        pool_mod._pool_override = override
        assert _get_pool() is override


class TestPoolLifecycle:
    @pytest.mark.asyncio
    async def test_add_and_get_connection(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        cid = pool.add("host1.example.com", "deploy", 22, conn)
        assert cid is not None
        entry = pool.get(cid)
        assert entry.host == "host1.example.com"
        assert entry.user == "deploy"
        assert entry.conn is conn

    @pytest.mark.asyncio
    async def test_get_invalid_id_raises(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        with pytest.raises(KeyError, match="not found"):
            pool.get("nonexistent-id")

    @pytest.mark.asyncio
    async def test_disconnect_removes(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        cid = pool.add("host1.example.com", "deploy", 22, conn)
        await pool.disconnect(cid)
        with pytest.raises(KeyError):
            pool.get(cid)

    @pytest.mark.asyncio
    async def test_disconnect_calls_close(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        cid = pool.add("host1.example.com", "deploy", 22, conn)
        await pool.disconnect(cid)
        conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_connections_returns_metadata(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn1 = _mock_asyncssh_conn()
        conn2 = _mock_asyncssh_conn()
        pool.add("host1.example.com", "deploy", 22, conn1)
        pool.add("host1.example.com", "admin", 22, conn2, label="staging")
        conns = pool.list_connections()
        assert len(conns) == 2

    @pytest.mark.asyncio
    async def test_list_connections_includes_label(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        pool.add("host1.example.com", "deploy", 22, conn, label="prod")
        conns = pool.list_connections()
        assert conns[0]["label"] == "prod"

    @pytest.mark.asyncio
    async def test_connection_count(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        assert pool.connection_count == 0
        pool.add("host1.example.com", "deploy", 22, conn)
        assert pool.connection_count == 1

    @pytest.mark.asyncio
    async def test_touch_updates_last_activity(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        cid = pool.add("host1.example.com", "deploy", 22, conn)
        entry = pool.get(cid)
        old_activity = entry.last_activity
        time.sleep(0.01)
        pool.touch(cid)
        entry = pool.get(cid)
        assert entry.last_activity > old_activity


class TestPoolHalt:
    @pytest.mark.asyncio
    async def test_halt_closes_all(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        c1 = _mock_asyncssh_conn()
        c2 = _mock_asyncssh_conn()
        pool.add("host1.example.com", "deploy", 22, c1)
        pool.add("host1.example.com", "deploy", 22, c2)
        await pool.halt()
        assert pool.connection_count == 0
        c1.close.assert_called_once()
        c2.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_clears_all(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        pool.add("host1.example.com", "deploy", 22, conn)
        pool.reset()
        assert pool.connection_count == 0


class TestPoolCleanup:
    @pytest.mark.asyncio
    async def test_prune_idle_connections(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        cid = pool.add("host1.example.com", "deploy", 22, conn)
        # Manually age the connection
        entry = pool.get(cid)
        entry.last_activity = time.time() - 400  # older than 300s idle
        pruned = await pool.prune(idle_timeout=300, max_lifetime=3600)
        assert pruned == 1
        assert pool.connection_count == 0

    @pytest.mark.asyncio
    async def test_prune_expired_connections(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        cid = pool.add("host1.example.com", "deploy", 22, conn)
        entry = pool.get(cid)
        entry.created_at = time.time() - 4000  # older than 3600s
        entry.last_activity = time.time()  # still active
        pruned = await pool.prune(idle_timeout=300, max_lifetime=3600)
        assert pruned == 1

    @pytest.mark.asyncio
    async def test_prune_keeps_active_connections(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        pool.add("host1.example.com", "deploy", 22, conn)
        pruned = await pool.prune(idle_timeout=300, max_lifetime=3600)
        assert pruned == 0
        assert pool.connection_count == 1

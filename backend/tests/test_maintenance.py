"""Tests for cold path maintenance — decay, prune, cleanup."""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from nobla.memory.maintenance import MaintenanceEngine


@pytest.fixture
def mock_session():
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 5
    mock_result.scalar.return_value = 10
    # For group_by queries
    mock_result.__iter__ = MagicMock(return_value=iter([
        ("fact", 5),
        ("entity", 3),
    ]))
    session.execute.return_value = mock_result
    return session


@pytest.fixture
def engine(mock_session):
    return MaintenanceEngine(db_session=mock_session, retention_days=90)


@pytest.mark.asyncio
async def test_decay_memories(engine):
    count = await engine.decay_memories()
    assert isinstance(count, int)
    assert count >= 0


@pytest.mark.asyncio
async def test_prune_old_memories(engine):
    count = await engine.prune_old_memories()
    assert isinstance(count, int)


@pytest.mark.asyncio
async def test_cleanup_orphan_links(engine):
    count = await engine.cleanup_orphan_links()
    assert isinstance(count, int)


@pytest.mark.asyncio
async def test_run_all(engine):
    result = await engine.run_all()
    assert "decayed" in result
    assert "pruned" in result
    assert "orphans_removed" in result


@pytest.mark.asyncio
async def test_get_stats(engine):
    stats = await engine.get_stats(uuid.uuid4())
    assert "total_memories" in stats
    assert "by_type" in stats
    assert "total_links" in stats

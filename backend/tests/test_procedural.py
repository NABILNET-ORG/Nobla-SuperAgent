"""Tests for procedural memory — Bayesian workflow scoring."""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from nobla.memory.procedural import ProceduralMemory


@pytest.fixture
def mock_session():
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalars.return_value.first.return_value = None
    mock_result.rowcount = 1
    session.execute.return_value = mock_result
    session.add = MagicMock()
    return session


@pytest.fixture
def procedural(mock_session):
    return ProceduralMemory(db_session=mock_session)


def test_bayesian_score():
    """Beta distribution: score = alpha / (alpha + beta)."""
    from nobla.memory.procedural import bayesian_score
    assert bayesian_score(2.0, 1.0) == pytest.approx(2.0 / 3.0)
    assert bayesian_score(10.0, 1.0) == pytest.approx(10.0 / 11.0)
    assert bayesian_score(1.0, 1.0) == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_create_procedure(procedural):
    proc_id = await procedural.create_procedure(
        user_id=uuid.uuid4(),
        name="Deploy to production",
        description="Steps to deploy the app",
        steps=[
            {"action": "Run tests", "order": 1},
            {"action": "Build docker image", "order": 2},
            {"action": "Push to registry", "order": 3},
        ],
    )
    assert proc_id is not None


@pytest.mark.asyncio
async def test_record_success(procedural):
    await procedural.record_outcome(uuid.uuid4(), success=True)
    # Should not raise


@pytest.mark.asyncio
async def test_record_failure(procedural):
    await procedural.record_outcome(uuid.uuid4(), success=False)
    # Should not raise


@pytest.mark.asyncio
async def test_get_relevant_procedures(procedural):
    results = await procedural.get_relevant(
        user_id=uuid.uuid4(),
        context="deploy production",
    )
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_list_procedures(procedural):
    results = await procedural.list_procedures(
        user_id=uuid.uuid4(),
    )
    assert isinstance(results, list)

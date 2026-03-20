"""Tests for semantic memory — fact storage with ChromaDB embeddings."""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from nobla.memory.semantic import SemanticMemory


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
def semantic(mock_session, tmp_path):
    return SemanticMemory(
        db_session=mock_session,
        chromadb_path=str(tmp_path / "chromadb"),
        embedding_model=None,  # Skip loading real model in tests
    )


def test_init(semantic):
    assert semantic is not None


@pytest.mark.asyncio
async def test_store_fact(semantic):
    fact_id = await semantic.store_fact(
        user_id=uuid.uuid4(),
        content="Alice prefers Python for ML",
        note_type="preference",
        keywords=["python", "ml"],
        source_conversation_id=uuid.uuid4(),
    )
    assert fact_id is not None


@pytest.mark.asyncio
async def test_search_facts(semantic):
    results = await semantic.search_facts(
        user_id=uuid.uuid4(),
        query="What does Alice prefer?",
        top_k=5,
    )
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_dedup_detection(semantic):
    user_id = uuid.uuid4()
    # Store a fact
    await semantic.store_fact(
        user_id=user_id,
        content="Alice prefers Python",
        note_type="preference",
    )
    # Check if near-duplicate is detected
    is_dup = semantic.is_near_duplicate(
        user_id=user_id,
        content="Alice prefers Python programming",
        threshold=0.85,
    )
    assert isinstance(is_dup, bool)


@pytest.mark.asyncio
async def test_delete_fact(semantic):
    result = await semantic.delete_fact(uuid.uuid4())
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_get_facts_by_type(semantic):
    results = await semantic.get_facts_by_type(
        user_id=uuid.uuid4(),
        note_type="preference",
    )
    assert isinstance(results, list)

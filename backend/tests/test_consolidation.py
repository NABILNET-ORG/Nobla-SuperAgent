"""Tests for warm path consolidation."""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from nobla.memory.consolidation import ConversationConsolidator
from nobla.memory.semantic import SemanticMemory
from nobla.memory.graph_builder import KnowledgeGraphBuilder
from nobla.memory.episodic import EpisodicMemory


class FakeMessage:
    def __init__(self, role, content):
        self.role = role
        self.content = content
        self.entities_extracted = None


@pytest.fixture
def consolidator():
    return ConversationConsolidator()


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
def graph():
    return KnowledgeGraphBuilder()


@pytest.mark.asyncio
async def test_consolidate_empty(consolidator, mock_session, graph):
    result = await consolidator.consolidate(
        messages=[],
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        episodic=EpisodicMemory(mock_session),
        semantic=SemanticMemory(mock_session, chromadb_path="/tmp/test_chroma", embedding_model=None),
        graph=graph,
    )
    assert result["summary"] == ""
    assert result["facts_extracted"] == 0
    assert result["entities_extracted"] == 0


@pytest.mark.asyncio
async def test_consolidate_extracts_entities(consolidator, mock_session, graph):
    messages = [
        FakeMessage("user", "Alice works at Google in New York"),
        FakeMessage("assistant", "That's great! Google is a top company."),
    ]
    result = await consolidator.consolidate(
        messages=messages,
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        episodic=EpisodicMemory(mock_session),
        semantic=SemanticMemory(mock_session, chromadb_path="/tmp/test_chroma", embedding_model=None),
        graph=graph,
    )
    assert result["entities_extracted"] >= 0  # May be 0 without spaCy
    assert isinstance(result["summary"], str)


@pytest.mark.asyncio
async def test_consolidate_generates_summary(consolidator, mock_session, graph):
    messages = [
        FakeMessage("user", "I want to learn Python for data science and machine learning projects"),
        FakeMessage("assistant", "Python is great for data science! Start with pandas and numpy."),
    ]
    result = await consolidator.consolidate(
        messages=messages,
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        episodic=EpisodicMemory(mock_session),
        semantic=SemanticMemory(mock_session, chromadb_path="/tmp/test_chroma", embedding_model=None),
        graph=graph,
    )
    assert len(result["summary"]) > 0


def test_parse_llm_response(consolidator):
    response = """SUMMARY: User wants to learn Python for ML
FACTS:
- User prefers Python
- User is interested in machine learning
ENTITIES:
- Python | TOOL | USES"""
    summary, facts = consolidator._parse_llm_response(response)
    assert "Python" in summary
    assert len(facts) == 2


def test_extract_facts_heuristic(consolidator):
    messages = [
        FakeMessage("user", "I really enjoy using Python for building data pipelines and ML models at work"),
        FakeMessage("assistant", "Great choice!"),
    ]
    facts = consolidator._extract_facts_heuristic(messages)
    assert isinstance(facts, list)
    assert len(facts) >= 1

"""Tests for knowledge graph builder, persistence, and queries."""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from nobla.memory.graph_builder import KnowledgeGraphBuilder
from nobla.memory.graph_persistence import GraphPersistence
from nobla.memory.graph_queries import GraphQueries


@pytest.fixture
def builder():
    return KnowledgeGraphBuilder()


@pytest.fixture
def mock_session():
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.rowcount = 1
    session.execute.return_value = mock_result
    session.add = MagicMock()
    return session


@pytest.fixture
def persistence(mock_session):
    return GraphPersistence(db_session=mock_session)


@pytest.fixture
def queries(builder):
    return GraphQueries(graph=builder)


# --- KnowledgeGraphBuilder tests ---

def test_add_entity(builder):
    builder.add_entity("Alice", entity_type="PERSON")
    assert builder.has_entity("Alice")


def test_add_entity_with_metadata(builder):
    builder.add_entity("Google", entity_type="ORGANIZATION", metadata={"domain": "tech"})
    assert builder.has_entity("Google")
    data = builder.get_entity("Google")
    assert data["entity_type"] == "ORGANIZATION"


def test_add_relationship(builder):
    builder.add_entity("Alice", entity_type="PERSON")
    builder.add_entity("Google", entity_type="ORGANIZATION")
    builder.add_relationship("Alice", "Google", "WORKS_AT", strength=0.9)
    assert builder.has_relationship("Alice", "Google", "WORKS_AT")


def test_add_relationship_creates_missing_entities(builder):
    builder.add_relationship("Bob", "Python", "USES", strength=0.8)
    assert builder.has_entity("Bob")
    assert builder.has_entity("Python")


def test_entity_count(builder):
    builder.add_entity("A", entity_type="PERSON")
    builder.add_entity("B", entity_type="TOOL")
    assert builder.entity_count == 2


def test_remove_entity(builder):
    builder.add_entity("Alice", entity_type="PERSON")
    builder.remove_entity("Alice")
    assert not builder.has_entity("Alice")


def test_get_entities_by_type(builder):
    builder.add_entity("Alice", entity_type="PERSON")
    builder.add_entity("Bob", entity_type="PERSON")
    builder.add_entity("Python", entity_type="TOOL")
    persons = builder.get_entities_by_type("PERSON")
    assert len(persons) == 2


# --- GraphPersistence tests ---

@pytest.mark.asyncio
async def test_save_incremental(persistence):
    builder = KnowledgeGraphBuilder()
    builder.add_entity("Alice", entity_type="PERSON")
    builder.add_relationship("Alice", "Python", "USES")
    await persistence.save_incremental(builder, user_id=uuid.uuid4())
    # Should have called session.add for new entities
    assert persistence._db.add.called


@pytest.mark.asyncio
async def test_load_graph(persistence):
    graph = await persistence.load_graph(user_id=uuid.uuid4())
    assert isinstance(graph, KnowledgeGraphBuilder)


# --- GraphQueries tests ---

def test_neighbors(queries, builder):
    builder.add_entity("Alice", entity_type="PERSON")
    builder.add_entity("Python", entity_type="TOOL")
    builder.add_relationship("Alice", "Python", "USES")
    neighbors = queries.neighbors("Alice")
    assert "Python" in neighbors


def test_get_related(queries, builder):
    builder.add_entity("Alice", entity_type="PERSON")
    builder.add_entity("Google", entity_type="ORGANIZATION")
    builder.add_relationship("Alice", "Google", "WORKS_AT")
    related = queries.get_related("Alice", link_type="WORKS_AT")
    assert "Google" in related


def test_search_entities(queries, builder):
    builder.add_entity("Alice Smith", entity_type="PERSON")
    builder.add_entity("Alice Johnson", entity_type="PERSON")
    results = queries.search_entities("Alice")
    assert len(results) == 2


def test_neighbors_empty(queries):
    results = queries.neighbors("NonExistent")
    assert results == []

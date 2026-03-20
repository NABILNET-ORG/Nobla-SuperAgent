"""Retrieval source backends — ChromaDB semantic, PostgreSQL BM25, graph neighbors.

Each source implements the RetrievalSource protocol, returning scored results
that the retrieval pipeline merges and re-ranks.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from nobla.memory.semantic import SemanticMemory
    from nobla.memory.graph_queries import GraphQueries

from nobla.memory.retrieval import RetrievalResult

logger = logging.getLogger(__name__)


class RetrievalSource(ABC):
    """Base class for retrieval backends."""

    @abstractmethod
    async def query(
        self, user_id: str, query_text: str, top_k: int = 5
    ) -> list[RetrievalResult]:
        ...


class SemanticSource(RetrievalSource):
    """Retrieves facts from ChromaDB via semantic similarity."""

    def __init__(self, semantic_memory: SemanticMemory):
        self._semantic = semantic_memory

    async def query(self, user_id, query_text, top_k=5):
        import uuid as uuid_lib
        uid = uuid_lib.UUID(user_id) if isinstance(user_id, str) else user_id
        facts = await self._semantic.search_facts(uid, query_text, top_k)
        return [
            RetrievalResult(
                id=f["id"],
                content=f["content"],
                score=f.get("similarity", 0.5),
                source="semantic",
                confidence=f.get("metadata", {}).get("confidence", 0.5),
                access_count=0,
                recency=0.5,
            )
            for f in facts
        ]


class GraphSource(RetrievalSource):
    """Retrieves entity context from the knowledge graph."""

    def __init__(self, graph_queries: GraphQueries):
        self._queries = graph_queries

    async def query(self, user_id, query_text, top_k=5):
        # Search for entities matching the query
        entities = self._queries.search_entities(query_text, limit=top_k)
        results = []
        for entity in entities:
            context = self._queries.get_entity_context(entity["name"])
            if context:
                results.append(RetrievalResult(
                    id=f"graph:{entity['name']}",
                    content=context,
                    score=0.6,  # Graph results get moderate base score
                    source="graph",
                    confidence=0.9,
                    access_count=entity.get("neighbors", 0),
                    recency=0.5,
                ))
        return results

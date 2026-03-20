"""Knowledge graph queries — traversal and search operations.

Provides query operations over the in-memory NetworkX graph:
1-hop neighbors, relationship queries, and entity search.
"""

from __future__ import annotations

import logging
from typing import Optional

from nobla.memory.graph_builder import KnowledgeGraphBuilder

logger = logging.getLogger(__name__)


class GraphQueries:
    """Query interface for the knowledge graph."""

    def __init__(self, graph: KnowledgeGraphBuilder):
        self._builder = graph

    def neighbors(self, entity: str, max_depth: int = 1) -> list[str]:
        """Get direct neighbors of an entity (1-hop by default)."""
        if not self._builder.has_entity(entity):
            return []

        g = self._builder._graph
        result = set()

        # Outgoing neighbors
        if entity in g:
            result.update(g.successors(entity))
            result.update(g.predecessors(entity))

        return list(result)

    def get_related(
        self,
        entity: str,
        link_type: Optional[str] = None,
    ) -> list[str]:
        """Get entities related to the given entity, optionally filtered by link type."""
        if not self._builder.has_entity(entity):
            return []

        g = self._builder._graph
        related = []

        # Check outgoing edges
        for _, target, data in g.out_edges(entity, data=True):
            if link_type is None or data.get("link_type") == link_type:
                related.append(target)

        # Check incoming edges
        for source, _, data in g.in_edges(entity, data=True):
            if link_type is None or data.get("link_type") == link_type:
                related.append(source)

        return related

    def search_entities(
        self,
        query: str,
        entity_type: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        """Search entities by name substring, optionally filtered by type."""
        query_lower = query.lower()
        results = []

        for name, attrs in self._builder._graph.nodes(data=True):
            if query_lower in name.lower():
                if entity_type and attrs.get("entity_type") != entity_type:
                    continue
                results.append({
                    "name": name,
                    "entity_type": attrs.get("entity_type", "UNKNOWN"),
                    "neighbors": len(list(self._builder._graph.successors(name)))
                               + len(list(self._builder._graph.predecessors(name))),
                })
                if len(results) >= limit:
                    break

        return results

    def get_entity_context(self, entity: str) -> str:
        """Get a natural-language context block for an entity and its neighbors."""
        if not self._builder.has_entity(entity):
            return ""

        attrs = self._builder.get_entity(entity)
        g = self._builder._graph
        parts = [f"{entity} ({attrs.get('entity_type', 'UNKNOWN')})"]

        # Outgoing relationships
        for _, target, data in g.out_edges(entity, data=True):
            link = data.get("link_type", "RELATED_TO")
            parts.append(f"  -> {link} -> {target}")

        # Incoming relationships
        for source, _, data in g.in_edges(entity, data=True):
            link = data.get("link_type", "RELATED_TO")
            parts.append(f"  <- {link} <- {source}")

        return "\n".join(parts)

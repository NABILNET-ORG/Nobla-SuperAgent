"""Knowledge graph builder — entity/relationship CRUD using NetworkX.

Maintains an in-memory directed graph of entities and their relationships.
Entities are nodes with typed metadata; relationships are weighted edges.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import networkx as nx

logger = logging.getLogger(__name__)


class KnowledgeGraphBuilder:
    """Manages an in-memory knowledge graph with NetworkX."""

    def __init__(self):
        self._graph = nx.DiGraph()
        self._dirty_entities: set[str] = set()
        self._dirty_relationships: set[tuple[str, str, str]] = set()

    # --- Entity CRUD ---

    def add_entity(
        self,
        name: str,
        entity_type: str = "UNKNOWN",
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Add or update an entity node."""
        attrs = {"entity_type": entity_type, **(metadata or {})}
        if self._graph.has_node(name):
            self._graph.nodes[name].update(attrs)
        else:
            self._graph.add_node(name, **attrs)
        self._dirty_entities.add(name)

    def has_entity(self, name: str) -> bool:
        return self._graph.has_node(name)

    def get_entity(self, name: str) -> dict[str, Any]:
        """Get entity attributes. Returns empty dict if not found."""
        if not self._graph.has_node(name):
            return {}
        return dict(self._graph.nodes[name])

    def remove_entity(self, name: str) -> None:
        """Remove entity and all its relationships."""
        if self._graph.has_node(name):
            self._graph.remove_node(name)
            self._dirty_entities.discard(name)

    def get_entities_by_type(self, entity_type: str) -> list[str]:
        """Get all entity names of a given type."""
        return [
            name for name, attrs in self._graph.nodes(data=True)
            if attrs.get("entity_type") == entity_type
        ]

    @property
    def entity_count(self) -> int:
        return self._graph.number_of_nodes()

    @property
    def relationship_count(self) -> int:
        return self._graph.number_of_edges()

    # --- Relationship CRUD ---

    def add_relationship(
        self,
        source: str,
        target: str,
        link_type: str,
        strength: float = 1.0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Add or update a directed relationship between entities."""
        # Auto-create entities if they don't exist
        if not self._graph.has_node(source):
            self.add_entity(source)
        if not self._graph.has_node(target):
            self.add_entity(target)

        attrs = {"link_type": link_type, "strength": strength, **(metadata or {})}

        # Check if edge already exists with same link_type
        if self._graph.has_edge(source, target):
            existing = self._graph[source][target]
            if existing.get("link_type") == link_type:
                # Update existing edge
                existing.update(attrs)
            else:
                # Different link type — NetworkX DiGraph allows one edge per pair,
                # so we overwrite. For multi-type edges, use MultiDiGraph later.
                self._graph[source][target].update(attrs)
        else:
            self._graph.add_edge(source, target, **attrs)

        self._dirty_relationships.add((source, target, link_type))

    def has_relationship(self, source: str, target: str, link_type: str) -> bool:
        if not self._graph.has_edge(source, target):
            return False
        return self._graph[source][target].get("link_type") == link_type

    def get_dirty_entities(self) -> set[str]:
        """Get entities modified since last save."""
        return self._dirty_entities.copy()

    def get_dirty_relationships(self) -> set[tuple[str, str, str]]:
        """Get relationships modified since last save."""
        return self._dirty_relationships.copy()

    def clear_dirty(self) -> None:
        """Mark all changes as saved."""
        self._dirty_entities.clear()
        self._dirty_relationships.clear()

    # --- Export ---

    def to_dict(self) -> dict:
        """Export graph as a serializable dictionary."""
        return {
            "entities": [
                {"name": n, **attrs}
                for n, attrs in self._graph.nodes(data=True)
            ],
            "relationships": [
                {"source": u, "target": v, **attrs}
                for u, v, attrs in self._graph.edges(data=True)
            ],
        }

"""Knowledge graph persistence — NetworkX <-> PostgreSQL serialization.

Saves graph entities as MemoryNode rows and relationships as MemoryLink rows.
Supports incremental saves (only dirty nodes/edges) to minimize DB writes.
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from nobla.db.models.memory import MemoryNode, MemoryLink
from nobla.memory.graph_builder import KnowledgeGraphBuilder

logger = logging.getLogger(__name__)


class GraphPersistence:
    """Loads and saves knowledge graphs to/from PostgreSQL."""

    def __init__(self, db_session: AsyncSession):
        self._db = db_session

    async def load_graph(self, user_id: uuid_lib.UUID) -> KnowledgeGraphBuilder:
        """Load a user's knowledge graph from PostgreSQL."""
        builder = KnowledgeGraphBuilder()

        # Load entity nodes
        result = await self._db.execute(
            select(MemoryNode)
            .where(MemoryNode.user_id == str(user_id))
            .where(MemoryNode.note_type == "entity")
        )
        nodes = result.scalars().all()
        node_id_to_name: dict[str, str] = {}

        for node in nodes:
            name = node.content
            node_id_to_name[str(node.id)] = name
            metadata = dict(node.metadata_) if node.metadata_ else {}
            entity_type = metadata.pop("entity_type", "UNKNOWN")
            builder.add_entity(name, entity_type=entity_type, metadata=metadata)

        # Load relationship edges
        if node_id_to_name:
            node_ids = list(node_id_to_name.keys())
            result = await self._db.execute(
                select(MemoryLink)
                .where(MemoryLink.source_id.in_(node_ids))
            )
            links = result.scalars().all()

            for link in links:
                source_name = node_id_to_name.get(str(link.source_id))
                target_name = node_id_to_name.get(str(link.target_id))
                if source_name and target_name:
                    builder.add_relationship(
                        source_name,
                        target_name,
                        link_type=link.link_type,
                        strength=link.strength or 1.0,
                    )

        builder.clear_dirty()
        logger.info(
            "graph_loaded",
            user_id=str(user_id),
            entities=builder.entity_count,
            relationships=builder.relationship_count,
        )
        return builder

    async def save_incremental(
        self,
        builder: KnowledgeGraphBuilder,
        user_id: uuid_lib.UUID,
    ) -> None:
        """Save only dirty (modified) entities and relationships."""
        # Save dirty entities
        for name in builder.get_dirty_entities():
            attrs = builder.get_entity(name)
            if not attrs:
                continue

            entity_type = attrs.pop("entity_type", "UNKNOWN")
            node = MemoryNode(
                user_id=str(user_id),
                content=name,
                note_type="entity",
                keywords=[name.lower()],
                confidence=1.0,
                metadata_={"entity_type": entity_type, **attrs},
            )
            self._db.add(node)

        await self._db.flush()

        # Save dirty relationships
        # First, get all entity node IDs
        result = await self._db.execute(
            select(MemoryNode)
            .where(MemoryNode.user_id == str(user_id))
            .where(MemoryNode.note_type == "entity")
        )
        nodes = result.scalars().all()
        name_to_id: dict[str, str] = {n.content: str(n.id) for n in nodes}

        for source, target, link_type in builder.get_dirty_relationships():
            source_id = name_to_id.get(source)
            target_id = name_to_id.get(target)
            if not source_id or not target_id:
                continue

            # Get strength from graph
            edge_data = {}
            if builder._graph.has_edge(source, target):
                edge_data = dict(builder._graph[source][target])

            link = MemoryLink(
                source_id=source_id,
                target_id=target_id,
                link_type=link_type,
                strength=edge_data.get("strength", 1.0),
            )
            self._db.add(link)

        builder.clear_dirty()
        logger.info("graph_saved", user_id=str(user_id))

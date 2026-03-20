"""Memory JSON-RPC handlers — memory.stats, memory.facts, memory.graph, memory.search.

Split from websocket.py to keep files under the 750-line limit.
"""

from __future__ import annotations

import uuid

from nobla.gateway.websocket import (
    rpc_method,
    ConnectionState,
    get_memory_orchestrator,
)


@rpc_method("memory.stats")
async def handle_memory_stats(params: dict, state: ConnectionState) -> dict:
    """Get memory statistics for the current user."""
    memory = get_memory_orchestrator()
    if not memory:
        raise RuntimeError("Memory orchestrator not initialized")

    async with memory._session_factory() as session:
        from nobla.memory.maintenance import MaintenanceEngine
        engine = MaintenanceEngine(db_session=session)
        stats = await engine.get_stats(uuid.UUID(state.user_id))

    # Add graph stats
    user_uuid = uuid.UUID(state.user_id)
    graph = memory._get_graph(user_uuid)
    stats["graph_entities"] = graph.entity_count
    stats["graph_relationships"] = graph.relationship_count

    return stats


@rpc_method("memory.facts")
async def handle_memory_facts(params: dict, state: ConnectionState) -> dict:
    """Get facts from semantic memory, optionally filtered by type."""
    memory = get_memory_orchestrator()
    if not memory:
        raise RuntimeError("Memory orchestrator not initialized")

    note_type = params.get("type", "fact")
    limit = params.get("limit", 20)

    async with memory._session_factory() as session:
        semantic = memory._semantic(session)
        facts = await semantic.get_facts_by_type(
            user_id=uuid.UUID(state.user_id),
            note_type=note_type,
            limit=limit,
        )

    return {"facts": facts}


@rpc_method("memory.graph")
async def handle_memory_graph(params: dict, state: ConnectionState) -> dict:
    """Get knowledge graph data for the current user."""
    memory = get_memory_orchestrator()
    if not memory:
        raise RuntimeError("Memory orchestrator not initialized")

    user_uuid = uuid.UUID(state.user_id)
    graph = memory._get_graph(user_uuid)
    graph_data = graph.to_dict()

    # Apply optional limit
    limit = params.get("limit", 50)
    graph_data["entities"] = graph_data["entities"][:limit]
    graph_data["relationships"] = graph_data["relationships"][:limit]

    return graph_data


@rpc_method("memory.search")
async def handle_memory_search(params: dict, state: ConnectionState) -> dict:
    """Semantic search across all memory types."""
    memory = get_memory_orchestrator()
    if not memory:
        raise RuntimeError("Memory orchestrator not initialized")

    query = params.get("query", "")
    top_k = params.get("limit", 10)

    async with memory._session_factory() as session:
        semantic = memory._semantic(session)
        facts = await semantic.search_facts(
            user_id=uuid.UUID(state.user_id),
            query=query,
            top_k=top_k,
        )

    return {"results": facts}


@rpc_method("memory.procedures")
async def handle_memory_procedures(params: dict, state: ConnectionState) -> dict:
    """List learned procedures for the current user."""
    memory = get_memory_orchestrator()
    if not memory:
        raise RuntimeError("Memory orchestrator not initialized")

    async with memory._session_factory() as session:
        from nobla.memory.procedural import ProceduralMemory
        proc_mem = ProceduralMemory(db_session=session)
        procedures = await proc_mem.list_procedures(
            user_id=uuid.UUID(state.user_id),
            limit=params.get("limit", 20),
        )

    return {"procedures": procedures}

"""JSON-RPC handlers for AI search."""
from __future__ import annotations

import structlog

from nobla.gateway.websocket import rpc_method, ConnectionState

logger = structlog.get_logger(__name__)

_search_engine = None


def set_search_engine(engine) -> None:
    global _search_engine
    _search_engine = engine


def get_search_engine():
    return _search_engine


@rpc_method("search.query")
async def handle_search_query(params: dict, state: ConnectionState) -> dict:
    from nobla.tools.search.models import SearchMode

    if not _search_engine:
        raise RuntimeError("Search engine not initialized")
    query = params.get("query", "")
    mode = SearchMode(params.get("mode", "quick"))
    use_brave = params.get("use_brave", False)
    response = await _search_engine.search(query, mode=mode, use_brave=use_brave)
    return response.to_dict()


@rpc_method("search.modes")
async def handle_search_modes(params: dict, state: ConnectionState) -> dict:
    if not _search_engine:
        return {"modes": ["quick", "deep", "wide", "deep_wide"]}
    return {"modes": _search_engine.available_modes()}

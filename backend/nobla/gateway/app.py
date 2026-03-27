"""
FastAPI application factory.

Creates the app, attaches middleware, REST routes, and WebSocket endpoint.
Service initialization lives in lifespan.py.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from nobla.gateway.lifespan import lifespan
from nobla.gateway.routes import router as rest_router
from nobla.gateway.websocket import websocket_endpoint, get_kill_switch
import nobla.gateway.memory_handlers  # noqa: F401 — registers memory RPC methods
import nobla.gateway.provider_handlers  # noqa: F401
import nobla.gateway.search_handlers  # noqa: F401
import nobla.gateway.voice_handlers  # noqa: F401 — registers voice RPC methods
import nobla.gateway.tool_handlers  # noqa: F401 — registers tool RPC methods
import nobla.gateway.channel_handlers  # noqa: F401 — registers channel RPC methods


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(title="Nobla Agent", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(rest_router)
    app.add_api_websocket_route("/ws", websocket_endpoint)

    # Emergency kill endpoint (localhost only)
    @app.post("/api/kill")
    async def emergency_kill(request: Request):
        client = request.client.host if request.client else ""
        if client not in ("127.0.0.1", "::1", "localhost"):
            return {"error": "Localhost only"}
        ks = get_kill_switch()
        if ks:
            await ks.soft_kill()
        return {"state": ks.state.value if ks else "unknown"}

    return app

"""
FastAPI application factory with lifespan management.

Creates the app, initializes LLM providers and security services
on startup, and wires REST routes + WebSocket endpoint.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import structlog

from nobla.gateway.routes import router as rest_router
from nobla.gateway.websocket import (
    websocket_endpoint,
    set_router,
    set_auth_service,
    set_kill_switch,
    set_cost_tracker,
    set_permission_checker,
    set_sandbox_manager,
    get_kill_switch,
)
from nobla.config import load_settings
from nobla.brain.router import LLMRouter
from nobla.security import (
    AuthService,
    KillSwitch,
    CostTracker,
    PermissionChecker,
    SandboxConfig,
    SandboxManager,
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize LLM providers and security services on startup."""
    settings = load_settings()

    # --- LLM Providers ---
    providers = {}
    llm_config = settings.llm

    for name in llm_config.fallback_chain:
        prov_settings = llm_config.providers.get(name)
        if not prov_settings or not prov_settings.enabled:
            continue
        try:
            if name == "gemini":
                from nobla.brain.gemini import GeminiProvider

                api_key = prov_settings.api_key or os.environ.get(
                    "GEMINI_API_KEY", ""
                )
                if api_key:
                    providers[name] = GeminiProvider(
                        api_key=api_key, model=prov_settings.model
                    )
            elif name == "ollama":
                from nobla.brain.ollama import OllamaProvider

                providers[name] = OllamaProvider(
                    model=prov_settings.model,
                    base_url=prov_settings.base_url or "http://localhost:11434",
                )
            elif name == "groq":
                from nobla.brain.groq import GroqProvider

                api_key = prov_settings.api_key or os.environ.get(
                    "GROQ_API_KEY", ""
                )
                if api_key:
                    providers[name] = GroqProvider(
                        api_key=api_key, model=prov_settings.model
                    )
        except Exception as e:
            logger.warning("provider_init_failed", provider=name, error=str(e))

    router = LLMRouter(
        providers=providers, fallback_chain=llm_config.fallback_chain
    )
    set_router(router)

    # --- Security Services ---
    auth_service = AuthService(
        secret_key=settings.secret_key,
        access_expire_minutes=settings.auth.access_token_expire_minutes,
        refresh_expire_days=settings.auth.refresh_token_expire_days,
        bcrypt_rounds=settings.auth.bcrypt_rounds,
        min_passphrase_length=settings.auth.min_passphrase_length,
    )
    kill_switch = KillSwitch()
    cost_tracker = CostTracker(
        daily_limit=settings.costs.daily_limit_usd,
        monthly_limit=settings.costs.monthly_limit_usd,
        session_limit=settings.costs.per_session_limit_usd,
        warning_threshold=settings.costs.warning_threshold,
    )
    permission_checker = PermissionChecker(
        escalation_requires_passphrase=settings.security.escalation_requires_passphrase,
    )
    sandbox_mgr = SandboxManager(SandboxConfig(**settings.sandbox.model_dump()))

    set_auth_service(auth_service)
    set_kill_switch(kill_switch)
    set_cost_tracker(cost_tracker)
    set_permission_checker(permission_checker)
    set_sandbox_manager(sandbox_mgr)

    logger.info(
        "nobla_started",
        providers=list(providers.keys()),
        phase="1B",
        security="enabled",
    )

    yield

    # Cleanup
    await sandbox_mgr.cleanup()
    logger.info("nobla_shutdown")


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

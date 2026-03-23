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
    manager as connection_manager,
    set_router,
    set_auth_service,
    set_kill_switch,
    set_cost_tracker,
    set_permission_checker,
    set_sandbox_manager,
    set_memory_orchestrator,
    get_kill_switch,
)
from nobla.memory.orchestrator import MemoryOrchestrator
from nobla.db.engine import Database
import nobla.gateway.memory_handlers  # noqa: F401 — registers memory RPC methods
import nobla.gateway.provider_handlers  # noqa: F401
import nobla.gateway.search_handlers  # noqa: F401
import nobla.gateway.voice_handlers  # noqa: F401 — registers voice RPC methods
import nobla.gateway.tool_handlers  # noqa: F401 — registers tool RPC methods
from nobla.config import load_settings
from nobla.brain.router import LLMRouter
from nobla.brain.circuit_breaker import CircuitBreaker
from nobla.brain.auth.api_key import ApiKeyManager
from nobla.brain.auth.oauth import OAuthManager
from nobla.brain.auth.local import LocalModelManager
from nobla.gateway.provider_handlers import (
    set_api_key_manager, set_oauth_manager,
    set_local_model_manager, set_provider_registry,
)
from nobla.security import (
    AuditEntry,
    AuthService,
    KillSwitch,
    CostTracker,
    PermissionChecker,
    SandboxConfig,
    SandboxManager,
)

logger = structlog.get_logger(__name__)


async def _log_audit(entry: AuditEntry) -> None:
    """Log an audit entry via structlog."""
    logger.info(
        "audit",
        user_id=entry.user_id,
        action=entry.action,
        status=entry.status,
        latency_ms=entry.latency_ms,
        tier=entry.tier,
        **entry.metadata,
    )


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
                from nobla.brain.providers.gemini import GeminiProvider

                api_key = prov_settings.api_key or os.environ.get(
                    "GEMINI_API_KEY", ""
                )
                if api_key:
                    providers[name] = GeminiProvider(
                        api_key=api_key, model=prov_settings.model
                    )
            elif name == "ollama":
                from nobla.brain.providers.ollama import OllamaProvider

                providers[name] = OllamaProvider(
                    model=prov_settings.model,
                    base_url=prov_settings.base_url or "http://localhost:11434",
                )
            elif name == "groq":
                from nobla.brain.providers.groq import GroqProvider

                api_key = prov_settings.api_key or os.environ.get(
                    "GROQ_API_KEY", ""
                )
                if api_key:
                    providers[name] = GroqProvider(
                        api_key=api_key, model=prov_settings.model
                    )
            elif name == "openai":
                from nobla.brain.providers.openai import OpenAIProvider

                api_key = prov_settings.api_key or os.environ.get(
                    "OPENAI_API_KEY", ""
                )
                if api_key:
                    providers[name] = OpenAIProvider(
                        api_key=api_key, model=prov_settings.model
                    )
            elif name == "anthropic":
                from nobla.brain.providers.anthropic import AnthropicProvider

                api_key = prov_settings.api_key or os.environ.get(
                    "ANTHROPIC_API_KEY", ""
                )
                if api_key:
                    providers[name] = AnthropicProvider(
                        api_key=api_key, model=prov_settings.model
                    )
            elif name == "deepseek":
                from nobla.brain.providers.deepseek import DeepSeekProvider

                api_key = prov_settings.api_key or os.environ.get(
                    "DEEPSEEK_API_KEY", ""
                )
                if api_key:
                    providers[name] = DeepSeekProvider(
                        api_key=api_key, model=prov_settings.model
                    )
        except Exception as e:
            logger.warning("provider_init_failed", provider=name, error=str(e))

    circuit_breakers = {name: CircuitBreaker(name) for name in providers}
    router = LLMRouter(providers=providers, fallback_chain=llm_config.fallback_chain, circuit_breakers=circuit_breakers)
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

    # --- Tool Platform (Phase 4) ---
    from nobla.tools import tool_registry
    from nobla.tools.approval import ApprovalManager
    from nobla.tools.executor import ToolExecutor
    from nobla.gateway.tool_handlers import (
        set_tool_executor,
        set_tool_registry,
        set_approval_manager,
    )

    approval_manager = ApprovalManager(connection_manager=connection_manager)
    tool_executor = ToolExecutor(
        registry=tool_registry,
        permission_checker=permission_checker,
        audit_logger=_log_audit,
        approval_manager=approval_manager,
        connection_manager=connection_manager,
        max_concurrent=settings.tools.max_concurrent_tools,
    )

    ks = get_kill_switch()
    if ks:
        ks.on_soft_kill(tool_executor.handle_kill)

    set_tool_executor(tool_executor)
    set_tool_registry(tool_registry)
    set_approval_manager(approval_manager)

    # --- Database & Memory System ---
    db = Database(settings)
    memory_orchestrator = MemoryOrchestrator(
        session_factory=db.session_factory,
        settings=settings,
    )
    set_memory_orchestrator(memory_orchestrator)

    # --- Search Engine (Phase 2B-2) ---
    from nobla.tools.search.searxng import SearxNGClient
    from nobla.tools.search.brave import BraveSearchClient
    from nobla.tools.search.academic import AcademicSearchClient
    from nobla.tools.search.synthesizer import SearchSynthesizer
    from nobla.tools.search.engine import SearchEngine
    from nobla.gateway.search_handlers import set_search_engine

    searxng = SearxNGClient(base_url=settings.search.searxng_url)
    brave_client = BraveSearchClient(api_key=settings.search.brave_api_key) if settings.search.brave_api_key else None
    academic = AcademicSearchClient(searxng_url=settings.search.searxng_url)
    synthesizer = SearchSynthesizer(router=router)
    search_engine = SearchEngine(
        searxng=searxng, brave=brave_client, academic=academic,
        synthesizer=synthesizer, memory=memory_orchestrator,
    )
    set_search_engine(search_engine)

    # --- Voice Pipeline (Phase 3A) ---
    from nobla.voice.stt.whisper import WhisperSTT
    from nobla.voice.stt.levantine import LevantineSTT
    from nobla.voice.stt.detector import LanguageDetector
    from nobla.voice.tts.fish_speech import FishSpeechTTS
    from nobla.voice.tts.cosyvoice import CosyVoiceTTS
    from nobla.voice.pipeline import VoicePipeline
    from nobla.gateway.voice_handlers import set_voice_pipeline

    try:
        whisper_stt = WhisperSTT(model_size=settings.voice.stt_model)
    except Exception:
        logger.warning("whisper_stt_load_failed voice_disabled=true")
        whisper_stt = None

    levantine_stt = None
    if whisper_stt:
        try:
            levantine_stt = LevantineSTT(model_path=settings.voice.levantine_model_path)
        except Exception:
            logger.warning("levantine_model_not_found arabic_stt=disabled")

    if whisper_stt:
        stt_engine = LanguageDetector(
            whisper_engine=whisper_stt,
            levantine_engine=levantine_stt,
        ) if levantine_stt else whisper_stt

        tts_engines = {}
        try:
            tts_engines["cosyvoice"] = CosyVoiceTTS(model_path="models/cosyvoice2")
        except Exception:
            logger.warning("cosyvoice_load_failed")
        try:
            tts_engines["fish_speech"] = FishSpeechTTS(model_path="models/fish_speech")
        except Exception:
            logger.warning("fish_speech_load_failed")

        if tts_engines:
            voice_pipeline = VoicePipeline(
                stt_engine=stt_engine,
                tts_engines=tts_engines,
                llm_router=router,
            )
            set_voice_pipeline(voice_pipeline)
            logger.info("voice_pipeline_ready engines=%s", list(tts_engines.keys()))
        else:
            logger.warning("no_tts_engines_available voice_disabled=true")
    else:
        logger.warning("voice_pipeline_disabled stt=unavailable")

    # --- Phase 3B: Persona System ---
    from nobla.persona.repository import PersonaRepository
    from nobla.persona.manager import PersonaManager
    from nobla.persona.prompt import PromptBuilder
    from nobla.persona.service import set_persona_manager, set_prompt_builder, set_emotion_detector
    from nobla.voice.emotion.hume import HumeEmotionEngine
    from nobla.voice.emotion.local import LocalEmotionEngine
    from nobla.voice.emotion.detector import EmotionDetector
    from nobla.gateway.persona_routes import create_persona_router

    persona_repo = PersonaRepository(db.session_factory)
    persona_manager = PersonaManager(repo=persona_repo)
    prompt_builder = PromptBuilder()
    set_persona_manager(persona_manager)
    set_prompt_builder(prompt_builder)

    # Emotion detection
    hume_engine = HumeEmotionEngine(api_key=settings.persona.hume_api_key)
    local_emotion_engine = LocalEmotionEngine(
        model_name=settings.persona.local_emotion_model,
    )
    emotion_detector = EmotionDetector(
        hume=hume_engine,
        local=local_emotion_engine,
        cache_ttl=settings.persona.emotion_cache_ttl,
    )
    set_emotion_detector(emotion_detector)

    # Pass emotion detector to voice pipeline (if it was initialized)
    from nobla.gateway.voice_handlers import get_voice_pipeline
    _vp = get_voice_pipeline()
    if _vp is not None:
        _vp._emotion_detector = emotion_detector

    # Register persona REST API routes
    persona_router = create_persona_router(persona_manager, persona_repo)
    app.include_router(persona_router)

    logger.info("persona_system_ready default=%s", settings.persona.default_persona)

    # --- Phase 3B-2: PersonaPlex premium TTS ---
    if settings.personaplex.enabled:
        from nobla.voice.tts.personaplex import PersonaPlexTTS

        personaplex_engine = PersonaPlexTTS(
            server_url=settings.personaplex.server_url,
            timeout=settings.personaplex.timeout,
            voice_prompts_dir=settings.personaplex.voice_prompts_dir,
            cpu_offload=settings.personaplex.cpu_offload,
        )
        tts_engines["personaplex"] = personaplex_engine
        logger.info("personaplex_registered url=%s", settings.personaplex.server_url)

    # --- Provider Auth (Phase 2B) ---
    api_key_mgr = ApiKeyManager(encryption_key=settings.secret_key or "dev-key-change-me")
    oauth_mgr = OAuthManager(configs={}, encryption_key=settings.secret_key or "dev-key-change-me")
    local_mgr = LocalModelManager()
    set_api_key_manager(api_key_mgr)
    set_oauth_manager(oauth_mgr)
    set_local_model_manager(local_mgr)
    set_provider_registry({
        "gemini": {"display_name": "Google Gemini", "auth_methods": ["oauth", "api_key"], "model": "gemini-2.0-flash"},
        "openai": {"display_name": "OpenAI GPT", "auth_methods": ["api_key"], "model": "gpt-4o"},
        "anthropic": {"display_name": "Anthropic Claude", "auth_methods": ["api_key"], "model": "claude-sonnet-4-20250514"},
        "groq": {"display_name": "Groq", "auth_methods": ["api_key"], "model": "llama-3.1-70b-versatile"},
        "deepseek": {"display_name": "DeepSeek", "auth_methods": ["api_key"], "model": "deepseek-chat"},
        "ollama": {"display_name": "Ollama (Local)", "auth_methods": ["local"], "model": "llama3.1"},
    })

    logger.info(
        "nobla_started",
        providers=list(providers.keys()),
        phase="3B",
        security="enabled",
        memory="enabled",
        voice="enabled" if whisper_stt else "disabled",
        persona="enabled",
    )

    yield

    # Cleanup
    await db.close()
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

"""
Gateway lifespan management.

Initializes all services on startup (event bus, LLM providers, security,
tools, channels, skills, memory, search, voice, persona, scheduler)
and tears them down on shutdown.

Extracted from app.py to keep files under the 750-line limit as
new services (agents, MCP) are added in Phase 6+.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
import structlog

from nobla.gateway.websocket import (
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


def _init_providers(llm_config) -> dict:
    """Instantiate LLM providers from settings."""
    providers = {}

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

    return providers


async def _init_channels(settings, linking_service, channel_manager, event_bus):
    """Initialize channel adapters (Telegram, Discord)."""
    # --- Telegram Adapter (Phase 5A) ---
    if settings.telegram.enabled and settings.telegram.bot_token:
        from nobla.channels.telegram.handlers import TelegramHandlers
        from nobla.channels.telegram.adapter import TelegramAdapter

        tg_handlers = TelegramHandlers(
            linking=linking_service,
            event_bus=event_bus,
            max_file_size_mb=settings.telegram.max_file_size_mb,
        )
        tg_adapter = TelegramAdapter(
            settings=settings.telegram,
            handlers=tg_handlers,
        )
        channel_manager.register(tg_adapter)
        await tg_adapter.start()
        logger.info(
            "telegram_adapter_started",
            mode=settings.telegram.mode,
        )
    else:
        logger.info("telegram_adapter_disabled")

    # --- Discord Adapter (Phase 5A) ---
    if settings.discord.enabled and settings.discord.bot_token:
        from nobla.channels.discord.handlers import DiscordHandlers
        from nobla.channels.discord.adapter import DiscordAdapter

        dc_handlers = DiscordHandlers(
            linking=linking_service,
            event_bus=event_bus,
            command_prefix=settings.discord.command_prefix,
            max_file_size_mb=settings.discord.max_file_size_mb,
        )
        dc_adapter = DiscordAdapter(
            settings=settings.discord,
            handlers=dc_handlers,
        )
        channel_manager.register(dc_adapter)
        await dc_adapter.start()
        logger.info("discord_adapter_started")
    else:
        logger.info("discord_adapter_disabled")


def _init_voice(settings, router):
    """Initialize voice pipeline (STT/TTS). Returns (voice_pipeline, whisper_stt, tts_engines)."""
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
        return None, {}

    levantine_stt = None
    try:
        levantine_stt = LevantineSTT(model_path=settings.voice.levantine_model_path)
    except Exception:
        logger.warning("levantine_model_not_found arabic_stt=disabled")

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
        return voice_pipeline, tts_engines
    else:
        logger.warning("no_tts_engines_available voice_disabled=true")
        return None, tts_engines


def _init_persona(settings, app, db, tts_engines):
    """Initialize persona system (Phase 3B)."""
    from nobla.persona.repository import PersonaRepository
    from nobla.persona.manager import PersonaManager
    from nobla.persona.prompt import PromptBuilder
    from nobla.persona.service import (
        set_persona_manager, set_prompt_builder, set_emotion_detector,
    )
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize all services on startup, tear down on shutdown."""
    settings = load_settings()

    # --- Event Bus (Phase 5-Foundation) — must init BEFORE all services ---
    from nobla.events.bus import NoblaEventBus

    event_bus = NoblaEventBus(
        max_queue_depth=settings.event_bus.max_queue_depth,
    )
    await event_bus.start()
    logger.info("event_bus_started")

    # --- LLM Providers ---
    providers = _init_providers(settings.llm)
    circuit_breakers = {name: CircuitBreaker(name) for name in providers}
    router = LLMRouter(
        providers=providers,
        fallback_chain=settings.llm.fallback_chain,
        circuit_breakers=circuit_breakers,
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
        event_bus=event_bus,
    )

    ks = get_kill_switch()
    if ks:
        ks.on_soft_kill(tool_executor.handle_kill)

    set_tool_executor(tool_executor)
    set_tool_registry(tool_registry)
    set_approval_manager(approval_manager)

    # --- Channel Abstraction (Phase 5-Foundation) ---
    from nobla.channels.manager import ChannelManager
    from nobla.channels.linking import UserLinkingService
    from nobla.gateway.channel_handlers import (
        set_channel_manager,
        set_linking_service,
        set_event_bus,
    )

    linking_service = UserLinkingService()
    channel_manager = ChannelManager(linking_service=linking_service)
    set_channel_manager(channel_manager)
    set_linking_service(linking_service)
    set_event_bus(event_bus)
    logger.info("channel_abstraction_ready")

    await _init_channels(settings, linking_service, channel_manager, event_bus)

    # --- Skill Runtime (Phase 5-Foundation) ---
    from nobla.skills.adapter import UniversalSkillAdapter
    from nobla.skills.adapters.nobla import NoblaAdapter
    from nobla.skills.runtime import SkillRuntime
    from nobla.skills.security import SkillSecurityScanner

    skill_adapter = UniversalSkillAdapter([NoblaAdapter()])
    skill_scanner = SkillSecurityScanner()
    skill_runtime = SkillRuntime(
        tool_registry=tool_registry,
        adapter=skill_adapter,
        event_bus=event_bus,
        security_scanner=skill_scanner,
    )
    logger.info("skill_runtime_ready")

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
    voice_pipeline, tts_engines = _init_voice(settings, router)

    # --- Phase 3B: Persona System ---
    _init_persona(settings, app, db, tts_engines)

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

    # --- NL Scheduled Tasks (Phase 6) ---
    from nobla.automation.scheduler import NoblaScheduler
    from nobla.automation.confirmation import ConfirmationManager
    from nobla.automation.service import SchedulerService

    nl_scheduler = NoblaScheduler(
        event_bus=event_bus,
        timezone=settings.scheduler.default_timezone,
        misfire_grace_seconds=settings.scheduler.misfire_grace_seconds,
    )
    confirmation_mgr = ConfirmationManager(
        event_bus=event_bus,
        timeout_seconds=settings.scheduler.confirmation_timeout_seconds,
    )
    scheduler_service = SchedulerService(
        scheduler=nl_scheduler,
        confirmation=confirmation_mgr,
        router=router,
        tool_registry=tool_registry,
        event_bus=event_bus,
        default_timezone=settings.scheduler.default_timezone,
        max_tasks_per_user=settings.scheduler.max_tasks_per_user,
    )

    if settings.scheduler.enabled:
        await scheduler_service.start()
        logger.info("scheduler_service_started")
    else:
        logger.info("scheduler_service_disabled")

    logger.info(
        "nobla_started",
        providers=list(providers.keys()),
        phase="6",
        security="enabled",
        memory="enabled",
        voice="enabled" if voice_pipeline else "disabled",
        persona="enabled",
    )

    yield

    # Cleanup
    await scheduler_service.stop()
    await channel_manager.stop_all()
    await event_bus.stop()
    await db.close()
    await sandbox_mgr.cleanup()
    logger.info("nobla_shutdown")

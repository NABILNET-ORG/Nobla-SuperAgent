from __future__ import annotations
from pathlib import Path

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings


class ServerSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    cors_origins: list[str] = ["*"]


class ProviderSettings(BaseModel):
    enabled: bool = True
    model: str = ""
    base_url: str | None = None
    api_key: str | None = None
    auth_type: str = "api_key"


class LLMSettings(BaseModel):
    default_provider: str = "gemini"
    fallback_chain: list[str] = ["gemini", "groq", "ollama", "openai", "anthropic", "deepseek"]
    providers: dict[str, ProviderSettings] = Field(default_factory=lambda: {
        "gemini": ProviderSettings(model="gemini-2.0-flash"),
        "ollama": ProviderSettings(model="llama3.1", base_url="http://localhost:11434"),
        "groq": ProviderSettings(model="llama-3.1-70b-versatile"),
        "openai": ProviderSettings(model="gpt-4o", enabled=False),
        "anthropic": ProviderSettings(model="claude-sonnet-4-20250514", enabled=False),
        "deepseek": ProviderSettings(model="deepseek-chat", enabled=False),
    })


class DatabaseSettings(BaseModel):
    postgres_url: str = "postgresql+asyncpg://nobla:nobla@localhost:5432/nobla"
    redis_url: str = "redis://localhost:6379/0"


class MemorySettings(BaseModel):
    context_window_messages: int = 20
    max_context_tokens: int = 8000
    store_embeddings: bool = True
    chromadb_path: str = "./data/chromadb"
    embedding_model: str = "all-MiniLM-L6-v2"
    spacy_model: str = "en_core_web_sm"
    warm_path_idle_timeout_minutes: int = 5
    cold_path_schedule_hour: int = 3
    memory_retention_days: int = 90
    retrieval_top_k: int = 5
    semantic_weight: float = 0.7
    keyword_weight: float = 0.3


class AuthSettings(BaseModel):
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    bcrypt_rounds: int = 12
    min_passphrase_length: int = 8


class SecuritySettings(BaseModel):
    default_tier: int = 1
    escalation_requires_passphrase: list[int] = [3, 4]


class SandboxSettings(BaseModel):
    enabled: bool = True
    runtime: str = "docker"
    memory_limit: str = "256m"
    cpu_limit: float = 1.0
    timeout_seconds: int = 30
    network_enabled: bool = False
    allowed_images: list[str] = ["python:3.12-slim", "node:20-slim", "bash:5", "alpine/git:latest"]


class CostSettings(BaseModel):
    daily_limit_usd: float = 5.0
    monthly_limit_usd: float = 50.0
    per_session_limit_usd: float = 1.0
    warning_threshold: float = 0.8


class SearchSettings(BaseModel):
    searxng_url: str = "http://localhost:8888"
    brave_api_key: str = ""
    default_mode: str = "quick"
    enabled: bool = True


class CompressionSettings(BaseModel):
    enabled: bool = True
    target_ratio: float = 0.5


class VoiceSettings(BaseModel):
    """Voice pipeline configuration."""

    stt_model: str = "large-v3"
    levantine_model_path: str = "backend/nobla/voice/models/ggml-levantine-large-v3.bin"
    default_tts_engine: str = "cosyvoice"
    default_vad_mode: str = "push_to_talk"
    opus_bitrate: int = 32000
    vad_silence_threshold_ms: int = 800
    vad_min_speech_ms: int = 250


class PersonaSettings(BaseModel):
    """Persona system configuration."""

    hume_api_key: str | None = None
    emotion_enabled: bool = True
    emotion_cache_ttl: int = 30
    emotion_confidence_threshold: float = 0.5
    default_persona: str = "professional"
    local_emotion_model: str = (
        "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition"
    )


class PersonaPlexSettings(BaseModel):
    """PersonaPlex premium TTS server configuration."""

    enabled: bool = False
    server_url: str = "http://localhost:8880"
    timeout: float = 30.0
    voice_prompts_dir: str = "backend/nobla/voice/models/voice_prompts"
    cpu_offload: bool = False


class ToolPlatformSettings(BaseModel):
    """Settings for the tool execution platform."""

    enabled: bool = True
    default_approval_timeout: int = 30
    activity_feed_enabled: bool = True
    max_concurrent_tools: int = 5


class VisionSettings(BaseModel):
    """Screen vision tools configuration."""

    enabled: bool = True
    screenshot_format: str = "png"
    screenshot_quality: int = 85
    screenshot_max_dimension: int = 1920
    screenshot_include_cursor: bool = False
    ocr_engine: str = "tesseract"
    ocr_languages: list[str] = ["en"]
    ocr_confidence_threshold: float = 0.5
    ui_tars_enabled: bool = False
    ui_tars_model_path: str = ""
    detection_confidence_threshold: float = 0.4
    element_cache_ttl: int = 5


class CodeExecutionSettings(BaseModel):
    """Code execution tools configuration."""

    enabled: bool = True
    default_language: str = "python"
    supported_languages: list[str] = ["python", "javascript", "bash"]
    package_volume_prefix: str = "nobla-pkg"
    persist_packages: bool = False
    max_output_length: int = 50000
    codegen_max_tokens: int = 4096
    debug_max_error_length: int = 5000
    git_allowed_hosts: list[str] = ["github.com", "gitlab.com"]
    git_timeout: int = 120
    git_workspace_volume_prefix: str = "nobla-git"
    git_image: str = "alpine/git:latest"


class ComputerControlSettings(BaseModel):
    """Configuration for Phase 4B computer control tools."""

    enabled: bool = True
    allowed_read_dirs: list[str] = Field(default_factory=list)
    allowed_write_dirs: list[str] = Field(default_factory=list)
    max_file_size_bytes: int = 10_485_760
    max_backups_per_file: int = 3
    allowed_apps: list[str] = Field(default_factory=list)
    failsafe_enabled: bool = True
    min_action_delay_ms: int = 100
    max_actions_per_minute: int = 120
    type_chunk_size: int = 50
    blocked_shortcuts: list[str] = Field(default_factory=lambda: [
        "ctrl+alt+delete", "alt+f4", "ctrl+shift+delete",
        "win+r", "win+l", "ctrl+w",
    ])
    max_clipboard_size: int = 1_048_576
    audit_clipboard_preview_length: int = 50

    @model_validator(mode="after")
    def validate_write_dirs_subset(self):
        """Every write directory must be within an allowed read directory."""
        for wd in self.allowed_write_dirs:
            wd_resolved = Path(wd).resolve()
            if not any(
                wd_resolved.is_relative_to(Path(rd).resolve())
                for rd in self.allowed_read_dirs
            ):
                raise ValueError(
                    f"Write directory '{wd}' is not within any allowed read directory"
                )
        return self


class RemoteControlSettings(BaseModel):
    """Configuration for Phase 4D remote control tools (SSH, SFTP)."""

    enabled: bool = True

    # --- Allow-lists (default deny) ---
    allowed_hosts: list[str] = Field(default_factory=list)
    allowed_users: list[str] = Field(default_factory=list)
    allowed_remote_dirs: list[str] = Field(default_factory=list)

    # --- Command safety ---
    safe_commands: list[str] = Field(
        default_factory=lambda: [
            "ls", "cat", "head", "tail", "grep", "find", "wc",
            "df", "du", "whoami", "hostname", "date", "uptime",
            "ps", "top", "free", "uname", "env", "echo", "pwd",
        ]
    )
    blocked_binaries: list[str] = Field(
        default_factory=lambda: [
            "mkfs", "dd", "shutdown", "reboot", "halt", "poweroff",
        ]
    )
    blocked_patterns: list[str] = Field(
        default_factory=lambda: [
            r"rm\s+.*-[^\s]*r[^\s]*f|rm\s+.*-[^\s]*f[^\s]*r",
            r"dd\s+.*of=/dev/",
            r">\s*/dev/sd",
            r"init\s+[06]",
            r"systemctl\s+(poweroff|halt)",
        ]
    )

    # --- SSH settings ---
    ssh_key_path: str | None = None
    allow_password_auth: bool = False
    known_hosts_policy: str = "strict"
    known_hosts_path: str | None = None

    # --- Timeouts ---
    ssh_connect_timeout_s: int = 30
    default_command_timeout_s: int = 60
    max_command_timeout_s: int = 600

    # --- Connection pool ---
    max_connections: int = 5
    idle_timeout_s: int = 300
    max_lifetime_s: int = 3600

    # --- SFTP limits ---
    sftp_max_file_size: int = 104_857_600
    sftp_approval_threshold: int = 10_485_760

    # --- Output ---
    max_output_bytes: int = 1_048_576
    max_output_lines: int = 10_000

    # --- Safety ---
    failsafe_enabled: bool = True

    @model_validator(mode="after")
    def validate_known_hosts_policy(self):
        valid = {"strict", "ask_first_time"}
        if self.known_hosts_policy not in valid:
            raise ValueError(
                f"known_hosts_policy must be one of {valid}, "
                f"got '{self.known_hosts_policy}'"
            )
        return self


class EventBusSettings(BaseModel):
    """Event bus configuration (Phase 5-Foundation)."""

    max_queue_depth: int = 10_000
    urgent_priority_threshold: int = 5


class ChannelSettings(BaseModel):
    """Channel abstraction configuration (Phase 5-Foundation)."""

    enabled: bool = True
    pairing_code_ttl_seconds: int = 300
    pairing_code_length: int = 6


class TelegramSettings(BaseModel):
    """Telegram bot adapter configuration (Phase 5A)."""

    enabled: bool = False
    bot_token: str = ""
    mode: str = "polling"  # "polling" or "webhook"
    webhook_url: str | None = None
    webhook_secret: str | None = None
    webhook_path: str = "/webhook/telegram"
    allowed_updates: list[str] = Field(
        default_factory=lambda: ["message", "callback_query", "edited_message"]
    )
    group_activation: str = "mention"  # "mention" only for now
    max_file_size_mb: int = 50
    download_timeout: int = 30
    rate_limit_per_second: int = 30

    @model_validator(mode="after")
    def validate_webhook_config(self):
        if self.mode == "webhook" and not self.webhook_url:
            raise ValueError("webhook_url is required when mode is 'webhook'")
        if self.mode not in ("polling", "webhook"):
            raise ValueError(f"mode must be 'polling' or 'webhook', got '{self.mode}'")
        return self


class DiscordSettings(BaseModel):
    """Discord bot adapter configuration (Phase 5A)."""

    enabled: bool = False
    bot_token: str = ""
    command_prefix: str = "!"
    group_activation: str = "mention"  # "mention" only for now
    max_file_size_mb: int = 25  # 100 with Nitro boost
    sync_commands_on_start: bool = True

    @model_validator(mode="after")
    def validate_prefix(self):
        if not self.command_prefix:
            raise ValueError("command_prefix must not be empty")
        return self


class WhatsAppSettings(BaseModel):
    """WhatsApp Business Cloud API adapter configuration (Phase 5-Channels)."""

    enabled: bool = False
    access_token: str = ""
    phone_number_id: str = ""
    business_account_id: str = ""
    app_secret: str = ""  # For webhook signature verification (HMAC-SHA256)
    verify_token: str = ""  # Webhook subscription verification token
    webhook_path: str = "/webhook/whatsapp"
    api_version: str = "v21.0"
    group_activation: str = "mention"
    max_file_size_mb: int = 100
    download_timeout: int = 30
    message_ttl_days: int = 30

    @model_validator(mode="after")
    def validate_secrets(self):
        if self.enabled and not self.access_token:
            raise ValueError("access_token is required when WhatsApp is enabled")
        if self.enabled and not self.phone_number_id:
            raise ValueError("phone_number_id is required when WhatsApp is enabled")
        return self


class SlackSettings(BaseModel):
    """Slack adapter configuration (Phase 5-Channels)."""

    enabled: bool = False
    bot_token: str = ""  # xoxb-*
    app_token: str = ""  # xapp-* (Socket Mode)
    signing_secret: str = ""  # Events API HMAC key
    mode: str = "socket"  # "socket" or "events"
    command_name: str = "/nobla"
    webhook_path: str = "/webhook/slack"
    group_activation: str = "mention"
    max_file_size_mb: int = 100

    @model_validator(mode="after")
    def validate_tokens(self):
        if self.enabled and not self.bot_token:
            raise ValueError("bot_token is required when Slack is enabled")
        if self.enabled and self.mode == "socket" and not self.app_token:
            raise ValueError("app_token is required for Socket Mode")
        if self.enabled and self.mode == "events" and not self.signing_secret:
            raise ValueError("signing_secret is required for Events API mode")
        return self


class SignalSettings(BaseModel):
    """Signal adapter configuration (Phase 5-Channels)."""

    enabled: bool = False
    phone_number: str = ""
    signal_cli_path: str = "signal-cli"
    mode: str = "json-rpc"
    rpc_host: str = "localhost"
    rpc_port: int = 7583
    data_dir: str = ""
    group_activation: str = "mention"
    max_file_size_mb: int = 100

    @model_validator(mode="after")
    def validate_phone(self):
        if self.enabled and not self.phone_number:
            raise ValueError("phone_number is required when Signal is enabled")
        return self


class TeamsSettings(BaseModel):
    """Microsoft Teams adapter configuration (Phase 5-Channels)."""

    enabled: bool = False
    app_id: str = ""
    app_password: str = ""
    tenant_id: str = ""  # Empty = multi-tenant
    webhook_path: str = "/webhook/teams"
    group_activation: str = "mention"
    max_file_size_mb: int = 100
    token_refresh_margin_seconds: int = 300

    @model_validator(mode="after")
    def validate_credentials(self):
        if self.enabled and not self.app_id:
            raise ValueError("app_id is required when Teams is enabled")
        if self.enabled and not self.app_password:
            raise ValueError("app_password is required when Teams is enabled")
        return self


class SchedulerSettings(BaseModel):
    """NL Scheduled Tasks configuration (Phase 6)."""

    enabled: bool = True
    max_tasks_per_user: int = 50
    default_timezone: str = "UTC"
    confirmation_timeout_seconds: int = 60
    max_concurrent_jobs: int = 10
    job_history_retention_days: int = 30
    misfire_grace_seconds: int = 300


class WebhookSettings(BaseModel):
    """Webhook system configuration (Phase 6)."""

    enabled: bool = True
    max_webhooks_per_user: int = 50
    default_signature_scheme: str = "hmac-sha256"
    inbound_path_prefix: str = "/webhooks/inbound"
    max_payload_bytes: int = 1_048_576  # 1 MB
    max_retries: int = 3
    retry_backoff_base: float = 2.0  # Exponential: 2s, 8s, 32s
    retry_backoff_multiplier: float = 4.0
    dead_letter_retention_days: int = 30
    event_log_retention_days: int = 7
    health_window_hours: int = 24  # Health computed over last N hours
    outbound_timeout_seconds: float = 10.0


class WorkflowSettings(BaseModel):
    """Workflow engine configuration (Phase 6)."""

    enabled: bool = True
    max_workflows_per_user: int = 100
    max_steps_per_workflow: int = 50
    max_triggers_per_workflow: int = 10
    max_concurrent_executions: int = 5
    default_step_timeout_seconds: int = 300
    max_step_retries: int = 5
    deduplication_window_seconds: float = 5.0
    execution_history_retention_days: int = 30


class AgentSettings(BaseModel):
    enabled: bool = True
    max_concurrent_agents: int = 10
    max_workflow_depth: int = 5
    max_tasks_per_workflow: int = 20
    default_isolation: str = "full_isolated"


class LearningSettings(BaseModel):
    enabled: bool = True
    feedback_enabled: bool = True
    pattern_detection_enabled: bool = True
    ab_testing_enabled: bool = True
    proactive_level: str = "conservative"


class MCPClientSettings(BaseModel):
    enabled: bool = False
    max_connections: int = 20
    default_timeout: float = 30.0
    allowed_servers: list[str] = Field(default_factory=list)


class MCPServerSettings(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8100
    transport: str = "sse"
    require_auth: bool = True
    default_tier: int = 2  # Tier.STANDARD value; use int for Pydantic serialization
    exposed_tools: list[str] = Field(default_factory=list)
    exposed_agents: list[str] = Field(default_factory=list)


class MarketplaceSettings(BaseModel):
    """Skills Marketplace configuration (Phase 5B.2)."""

    enabled: bool = True
    max_skills_per_author: int = 50
    max_archive_size_mb: int = 10
    storage_dir: str = "data/marketplace"


class SkillRuntimeSettings(BaseModel):
    """Skill runtime configuration (Phase 5-Foundation)."""

    enabled: bool = True
    default_dry_run_timeout_seconds: int = 10
    mcp_dry_run_timeout_seconds: int = 20
    max_installed_skills: int = 100


class Settings(BaseSettings):
    server: ServerSettings = ServerSettings()
    llm: LLMSettings = LLMSettings()
    database: DatabaseSettings = DatabaseSettings()
    memory: MemorySettings = MemorySettings()
    auth: AuthSettings = AuthSettings()
    security: SecuritySettings = SecuritySettings()
    sandbox: SandboxSettings = SandboxSettings()
    costs: CostSettings = CostSettings()
    search: SearchSettings = SearchSettings()
    compression: CompressionSettings = CompressionSettings()
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    persona: PersonaSettings = Field(default_factory=PersonaSettings)
    personaplex: PersonaPlexSettings = Field(default_factory=PersonaPlexSettings)
    tools: ToolPlatformSettings = Field(default_factory=ToolPlatformSettings)
    vision: VisionSettings = Field(default_factory=VisionSettings)
    code: CodeExecutionSettings = Field(default_factory=CodeExecutionSettings)
    computer_control: ComputerControlSettings = Field(default_factory=ComputerControlSettings)
    remote_control: RemoteControlSettings = Field(default_factory=RemoteControlSettings)
    event_bus: EventBusSettings = Field(default_factory=EventBusSettings)
    channels: ChannelSettings = Field(default_factory=ChannelSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    discord: DiscordSettings = Field(default_factory=DiscordSettings)
    whatsapp: WhatsAppSettings = Field(default_factory=WhatsAppSettings)
    slack: SlackSettings = Field(default_factory=SlackSettings)
    signal: SignalSettings = Field(default_factory=SignalSettings)
    teams: TeamsSettings = Field(default_factory=TeamsSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    webhooks: WebhookSettings = Field(default_factory=WebhookSettings)
    workflows: WorkflowSettings = Field(default_factory=WorkflowSettings)
    skill_runtime: SkillRuntimeSettings = Field(default_factory=SkillRuntimeSettings)
    agents: AgentSettings = Field(default_factory=AgentSettings)
    mcp_client: MCPClientSettings = Field(default_factory=MCPClientSettings)
    mcp_server: MCPServerSettings = Field(default_factory=MCPServerSettings)
    learning: LearningSettings = Field(default_factory=LearningSettings)
    marketplace: MarketplaceSettings = Field(default_factory=MarketplaceSettings)
    secret_key: str = ""  # REQUIRED: set via SECRET_KEY env var

    model_config = {"env_prefix": "", "env_nested_delimiter": "__"}

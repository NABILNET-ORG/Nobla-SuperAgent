from __future__ import annotations
from pydantic import BaseModel, Field
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


class LLMSettings(BaseModel):
    default_provider: str = "gemini"
    fallback_chain: list[str] = ["gemini", "groq", "ollama"]
    providers: dict[str, ProviderSettings] = Field(default_factory=lambda: {
        "gemini": ProviderSettings(model="gemini-2.0-flash"),
        "ollama": ProviderSettings(model="llama3.1", base_url="http://localhost:11434"),
        "groq": ProviderSettings(model="llama-3.1-70b-versatile"),
    })


class DatabaseSettings(BaseModel):
    postgres_url: str = "postgresql+asyncpg://nobla:nobla@localhost:5432/nobla"
    redis_url: str = "redis://localhost:6379/0"


class MemorySettings(BaseModel):
    context_window_messages: int = 20
    max_context_tokens: int = 8000
    store_embeddings: bool = False


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
    allowed_images: list[str] = ["python:3.12-slim"]


class CostSettings(BaseModel):
    daily_limit_usd: float = 5.0
    monthly_limit_usd: float = 50.0
    per_session_limit_usd: float = 1.0
    warning_threshold: float = 0.8


class Settings(BaseSettings):
    server: ServerSettings = ServerSettings()
    llm: LLMSettings = LLMSettings()
    database: DatabaseSettings = DatabaseSettings()
    memory: MemorySettings = MemorySettings()
    auth: AuthSettings = AuthSettings()
    security: SecuritySettings = SecuritySettings()
    sandbox: SandboxSettings = SandboxSettings()
    costs: CostSettings = CostSettings()
    secret_key: str = ""  # REQUIRED: set via SECRET_KEY env var

    model_config = {"env_prefix": "", "env_nested_delimiter": "__"}

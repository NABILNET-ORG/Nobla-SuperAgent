import pytest
from nobla.config.settings import Settings


def test_settings_defaults():
    settings = Settings()
    assert settings.server.host == "0.0.0.0"
    assert settings.server.port == 8000
    assert settings.llm.default_provider == "gemini"
    assert settings.database.redis_url == "redis://localhost:6379/0"
    assert settings.memory.context_window_messages == 20
    assert settings.memory.max_context_tokens == 8000


def test_settings_provider_config():
    settings = Settings()
    assert settings.llm.providers["gemini"].enabled is True
    assert settings.llm.providers["gemini"].model == "gemini-2.0-flash"
    assert settings.llm.fallback_chain == ["gemini", "groq", "ollama"]


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("DATABASE__POSTGRES_URL", "postgresql+asyncpg://test:test@db:5432/test")
    monkeypatch.setenv("DATABASE__REDIS_URL", "redis://redis:6379/1")
    settings = Settings()
    assert "test" in settings.database.postgres_url
    assert settings.database.redis_url == "redis://redis:6379/1"


def test_load_settings_from_yaml(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("server:\n  port: 9000\n  debug: true\n")
    from nobla.config.loader import load_settings
    settings = load_settings(str(config))
    assert settings.server.port == 9000
    assert settings.server.debug is True

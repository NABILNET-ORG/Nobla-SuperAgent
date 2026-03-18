from __future__ import annotations
import os
from pathlib import Path
import yaml
from dotenv import load_dotenv
from nobla.config.settings import Settings


def load_settings(config_path: str | None = None) -> Settings:
    """Load settings from YAML config + .env + environment variables.
    Priority: env vars > .env file > config.yaml > defaults
    """
    env_path = Path("backend/.env") if Path("backend/.env").exists() else Path(".env")
    load_dotenv(env_path)

    yaml_config = {}
    if config_path is None:
        for candidate in ["config.yaml", "backend/config.yaml"]:
            if Path(candidate).exists():
                config_path = candidate
                break

    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            yaml_config = yaml.safe_load(f) or {}

    _flatten_to_env(yaml_config)
    return Settings()


def _flatten_to_env(d: dict, prefix: str = "") -> None:
    """Flatten nested dict to env vars (only if not already set)."""
    for key, value in d.items():
        env_key = f"{prefix}{key}".upper() if not prefix else f"{prefix}__{key}".upper()
        if isinstance(value, dict):
            _flatten_to_env(value, env_key if prefix else key.upper())
        elif not os.environ.get(env_key):
            os.environ[env_key] = str(value)

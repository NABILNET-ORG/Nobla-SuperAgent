from __future__ import annotations

from nobla.config.settings import Settings


class TestToolPlatformSettings:
    def test_defaults(self):
        settings = Settings()
        assert settings.tools.enabled is True
        assert settings.tools.default_approval_timeout == 30
        assert settings.tools.activity_feed_enabled is True
        assert settings.tools.max_concurrent_tools == 5

    def test_override(self):
        settings = Settings(tools={"enabled": False, "max_concurrent_tools": 10})
        assert settings.tools.enabled is False
        assert settings.tools.max_concurrent_tools == 10

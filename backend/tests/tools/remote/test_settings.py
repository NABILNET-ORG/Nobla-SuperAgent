"""Tests for RemoteControlSettings."""

import pytest
from pydantic import ValidationError


class TestRemoteControlSettingsDefaults:
    def test_enabled_default_true(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.enabled is True

    def test_allowed_hosts_default_empty(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.allowed_hosts == []

    def test_allowed_users_default_empty(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.allowed_users == []

    def test_allowed_remote_dirs_default_empty(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.allowed_remote_dirs == []

    def test_safe_commands_has_defaults(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert "ls" in s.safe_commands
        assert "cat" in s.safe_commands
        assert "whoami" in s.safe_commands

    def test_blocked_binaries_has_defaults(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert "mkfs" in s.blocked_binaries
        assert "shutdown" in s.blocked_binaries

    def test_blocked_patterns_has_defaults(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert len(s.blocked_patterns) > 0

    def test_allow_password_auth_default_false(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.allow_password_auth is False

    def test_known_hosts_policy_default_strict(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.known_hosts_policy == "strict"

    def test_max_connections_default_5(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.max_connections == 5

    def test_idle_timeout_default_300(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.idle_timeout_s == 300

    def test_max_lifetime_default_3600(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.max_lifetime_s == 3600

    def test_sftp_max_file_size_default_100mb(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.sftp_max_file_size == 104_857_600

    def test_max_output_bytes_default_1mb(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.max_output_bytes == 1_048_576

    def test_max_output_lines_default_10000(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.max_output_lines == 10_000


class TestRemoteControlSettingsValidation:
    def test_invalid_known_hosts_policy_raises(self):
        from nobla.config.settings import RemoteControlSettings
        with pytest.raises(ValidationError, match="known_hosts_policy"):
            RemoteControlSettings(known_hosts_policy="yolo")

    def test_valid_known_hosts_policy_strict(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings(known_hosts_policy="strict")
        assert s.known_hosts_policy == "strict"

    def test_valid_known_hosts_policy_ask_first_time(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings(known_hosts_policy="ask_first_time")
        assert s.known_hosts_policy == "ask_first_time"

    def test_custom_allowed_hosts(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings(allowed_hosts=["prod.example.com"])
        assert s.allowed_hosts == ["prod.example.com"]

    def test_custom_timeouts(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings(
            ssh_connect_timeout_s=10,
            default_command_timeout_s=30,
            max_command_timeout_s=120,
        )
        assert s.ssh_connect_timeout_s == 10
        assert s.default_command_timeout_s == 30
        assert s.max_command_timeout_s == 120


class TestSettingsNesting:
    def test_settings_has_remote_control(self):
        from nobla.config.settings import Settings
        s = Settings()
        assert hasattr(s, "remote_control")

    def test_settings_remote_control_is_remote_control_settings(self):
        from nobla.config.settings import RemoteControlSettings, Settings
        s = Settings()
        assert isinstance(s.remote_control, RemoteControlSettings)

"""Tests for ComputerControlSettings validation and defaults."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from nobla.config.settings import ComputerControlSettings


class TestComputerControlSettingsDefaults:
    """Verify default values are sane."""

    def test_defaults(self):
        s = ComputerControlSettings()
        assert s.enabled is True
        assert s.allowed_read_dirs == []
        assert s.allowed_write_dirs == []
        assert s.max_file_size_bytes == 10_485_760
        assert s.max_backups_per_file == 3
        assert s.allowed_apps == []
        assert s.failsafe_enabled is True
        assert s.min_action_delay_ms == 100
        assert s.max_actions_per_minute == 120
        assert s.type_chunk_size == 50
        assert s.max_clipboard_size == 1_048_576
        assert s.audit_clipboard_preview_length == 50

    def test_blocked_shortcuts_defaults(self):
        s = ComputerControlSettings()
        expected = [
            "ctrl+alt+delete", "alt+f4", "ctrl+shift+delete",
            "win+r", "win+l", "ctrl+w",
        ]
        assert s.blocked_shortcuts == expected


class TestWriteDirValidation:
    """Write dirs must be subsets of read dirs."""

    def test_write_dir_within_read_dir(self, tmp_path):
        read_dir = str(tmp_path)
        write_dir = str(tmp_path / "subdir")
        write_dir_path = tmp_path / "subdir"
        write_dir_path.mkdir()
        s = ComputerControlSettings(
            allowed_read_dirs=[read_dir],
            allowed_write_dirs=[write_dir],
        )
        assert s.allowed_write_dirs == [write_dir]

    def test_write_dir_not_in_read_dir_raises(self, tmp_path):
        read_dir = str(tmp_path / "read")
        write_dir = str(tmp_path / "other")
        (tmp_path / "read").mkdir()
        (tmp_path / "other").mkdir()
        with pytest.raises(ValidationError, match="not within any allowed read directory"):
            ComputerControlSettings(
                allowed_read_dirs=[read_dir],
                allowed_write_dirs=[write_dir],
            )

    def test_write_dir_equals_read_dir(self, tmp_path):
        d = str(tmp_path)
        s = ComputerControlSettings(
            allowed_read_dirs=[d],
            allowed_write_dirs=[d],
        )
        assert s.allowed_write_dirs == [d]

    def test_empty_write_dirs_always_valid(self):
        s = ComputerControlSettings(allowed_read_dirs=["/some/path"])
        assert s.allowed_write_dirs == []


class TestCustomValues:
    """Custom values are accepted when valid."""

    def test_custom_values(self, tmp_path):
        d = str(tmp_path)
        s = ComputerControlSettings(
            enabled=False,
            allowed_read_dirs=[d],
            allowed_write_dirs=[d],
            max_file_size_bytes=5_000_000,
            max_backups_per_file=10,
            allowed_apps=["notepad.exe", "code.exe"],
            failsafe_enabled=False,
            min_action_delay_ms=200,
            max_actions_per_minute=60,
            type_chunk_size=25,
            blocked_shortcuts=[],
            max_clipboard_size=500_000,
            audit_clipboard_preview_length=100,
        )
        assert s.enabled is False
        assert s.max_file_size_bytes == 5_000_000
        assert s.allowed_apps == ["notepad.exe", "code.exe"]
        assert s.blocked_shortcuts == []
        assert s.min_action_delay_ms == 200

    def test_empty_blocked_shortcuts(self):
        s = ComputerControlSettings(blocked_shortcuts=[])
        assert s.blocked_shortcuts == []

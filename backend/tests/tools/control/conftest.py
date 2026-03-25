"""Shared fixtures for Phase 4B computer-control tests."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from nobla.config.settings import ComputerControlSettings


@pytest.fixture()
def control_settings(tmp_path) -> ComputerControlSettings:
    """Return a ComputerControlSettings with tmp_path-based directories."""
    read_dir = tmp_path / "read"
    read_dir.mkdir()
    write_dir = tmp_path / "read" / "write"
    write_dir.mkdir()
    return ComputerControlSettings(
        allowed_read_dirs=[str(read_dir)],
        allowed_write_dirs=[str(write_dir)],
        min_action_delay_ms=100,
        max_actions_per_minute=120,
    )


@pytest.fixture()
def mock_pyautogui() -> MagicMock:
    """Mock pyautogui with size and FAILSAFE attributes."""
    mock = MagicMock()
    mock.size.return_value = (1920, 1080)
    mock.FAILSAFE = True

    # Create a FailSafeException class on the mock
    class FailSafeException(Exception):
        pass

    mock.FailSafeException = FailSafeException
    return mock


@pytest.fixture()
def mock_pyperclip() -> MagicMock:
    """Mock pyperclip copy/paste."""
    mock = MagicMock()
    mock.copy = MagicMock()
    mock.paste = MagicMock(return_value="test clipboard content")
    return mock


@pytest.fixture()
def mock_psutil() -> MagicMock:
    """Mock psutil process iteration."""
    proc = SimpleNamespace(info={"name": "notepad.exe", "pid": 1234})
    mock = MagicMock()
    mock.process_iter.return_value = [proc]
    return mock

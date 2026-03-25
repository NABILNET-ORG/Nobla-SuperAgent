"""Tests for FileManageTool — path security, backups, CRUD operations."""
from __future__ import annotations

import asyncio
import os
import time

import pytest

from nobla.config.settings import ComputerControlSettings
from nobla.gateway.websocket import ConnectionState
from nobla.tools.models import ToolCategory, ToolParams, ToolResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _params(args: dict) -> ToolParams:
    return ToolParams(args=args, connection_state=ConnectionState())


def _make_tool(settings: ComputerControlSettings):
    """Create a fresh FileManageTool with injected settings."""
    from nobla.tools.control.file_manager import FileManageTool

    tool = FileManageTool()
    tool._settings_override = settings
    return tool


# ===================================================================
# Path security tests
# ===================================================================


class TestPathSecurity:
    """Validate path allow-list enforcement."""

    def test_read_within_allowed_dir(self, control_settings, tmp_path):
        """Reading a file inside allowed_read_dirs should pass validation."""
        tool = _make_tool(control_settings)
        read_dir = tmp_path / "read"
        target = read_dir / "hello.txt"
        target.write_text("data")
        params = _params({"action": "read", "path": str(target)})
        asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_read_outside_allowed_dir(self, control_settings, tmp_path):
        """Reading outside allowed_read_dirs must raise ValueError."""
        tool = _make_tool(control_settings)
        outside = tmp_path / "outside.txt"
        outside.write_text("secret")
        params = _params({"action": "read", "path": str(outside)})
        with pytest.raises(ValueError, match="not within any allowed"):
            asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_traversal_attack(self, control_settings, tmp_path):
        """Path with ../../ must be blocked after resolution."""
        tool = _make_tool(control_settings)
        read_dir = tmp_path / "read"
        evil_path = str(read_dir / "subdir" / ".." / ".." / "outside.txt")
        params = _params({"action": "read", "path": evil_path})
        with pytest.raises(ValueError, match="not within any allowed"):
            asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_symlink_escape(self, control_settings, tmp_path):
        """Symlink pointing outside allowed dir must be blocked."""
        tool = _make_tool(control_settings)
        read_dir = tmp_path / "read"
        outside = tmp_path / "outside.txt"
        outside.write_text("escape")
        link = read_dir / "sneaky_link.txt"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("Symlink creation not supported (requires privileges)")
        params = _params({"action": "read", "path": str(link)})
        with pytest.raises(ValueError, match="not within any allowed"):
            asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_write_outside_write_dir(self, control_settings, tmp_path):
        """Writing to a path inside read_dir but outside write_dir must fail."""
        tool = _make_tool(control_settings)
        # read_dir is allowed for reads, but NOT for writes
        read_dir = tmp_path / "read"
        target = read_dir / "no_write_here.txt"
        params = _params({
            "action": "write", "path": str(target), "content": "x",
        })
        with pytest.raises(ValueError, match="not within any allowed"):
            asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_write_within_write_dir(self, control_settings, tmp_path):
        """Writing inside allowed_write_dirs should pass validation."""
        tool = _make_tool(control_settings)
        write_dir = tmp_path / "read" / "write"
        target = write_dir / "ok.txt"
        params = _params({
            "action": "write", "path": str(target), "content": "ok",
        })
        asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_empty_read_dirs_raises(self, tmp_path):
        """Empty allowed_read_dirs should raise ValueError with hint."""
        settings = ComputerControlSettings(
            allowed_read_dirs=[],
            allowed_write_dirs=[],
        )
        tool = _make_tool(settings)
        params = _params({"action": "read", "path": "/anything"})
        with pytest.raises(ValueError, match="allowed_read_dirs"):
            asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_empty_write_dirs_raises(self, tmp_path):
        """Empty allowed_write_dirs should raise ValueError with hint."""
        read_dir = tmp_path / "read"
        read_dir.mkdir(exist_ok=True)
        settings = ComputerControlSettings(
            allowed_read_dirs=[str(read_dir)],
            allowed_write_dirs=[],
        )
        tool = _make_tool(settings)
        params = _params({
            "action": "write", "path": str(read_dir / "file.txt"),
            "content": "x",
        })
        with pytest.raises(ValueError, match="allowed_write_dirs"):
            asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_file_too_large(self, control_settings, tmp_path):
        """Reading a file exceeding max_file_size_bytes must fail validation."""
        tool = _make_tool(control_settings)
        read_dir = tmp_path / "read"
        big_file = read_dir / "big.bin"
        # Create a file larger than the default 10 MB limit
        big_file.write_bytes(b"x" * (control_settings.max_file_size_bytes + 1))
        params = _params({"action": "read", "path": str(big_file)})
        with pytest.raises(ValueError, match="exceeds maximum"):
            asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_move_validates_src_read_dst_write(self, control_settings, tmp_path):
        """Move must validate source in read_dirs AND dest in write_dirs."""
        tool = _make_tool(control_settings)
        write_dir = tmp_path / "read" / "write"
        src = write_dir / "src.txt"
        src.write_text("data")
        # Dest outside write_dirs
        dst = tmp_path / "read" / "not_writable.txt"
        params = _params({
            "action": "move", "path": str(src), "destination": str(dst),
        })
        with pytest.raises(ValueError, match="not within any allowed"):
            asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_copy_validates_src_read_dst_write(self, control_settings, tmp_path):
        """Copy must validate source in read_dirs AND dest in write_dirs."""
        tool = _make_tool(control_settings)
        write_dir = tmp_path / "read" / "write"
        src = write_dir / "src.txt"
        src.write_text("data")
        dst = tmp_path / "read" / "not_writable.txt"
        params = _params({
            "action": "copy", "path": str(src), "destination": str(dst),
        })
        with pytest.raises(ValueError, match="not within any allowed"):
            asyncio.get_event_loop().run_until_complete(tool.validate(params))


# ===================================================================
# Execution tests
# ===================================================================


class TestExecution:
    """Test each file action end-to-end."""

    @pytest.mark.asyncio
    async def test_read_file(self, control_settings, tmp_path):
        tool = _make_tool(control_settings)
        target = tmp_path / "read" / "greet.txt"
        target.write_text("Hello, Nobla!")
        params = _params({"action": "read", "path": str(target)})
        result = await tool.execute(params)
        assert result.success is True
        assert result.data["content"] == "Hello, Nobla!"

    @pytest.mark.asyncio
    async def test_write_file(self, control_settings, tmp_path):
        tool = _make_tool(control_settings)
        target = tmp_path / "read" / "write" / "new.txt"
        params = _params({
            "action": "write",
            "path": str(target),
            "content": "created!",
        })
        result = await tool.execute(params)
        assert result.success is True
        assert target.read_text() == "created!"

    @pytest.mark.asyncio
    async def test_write_creates_backup(self, control_settings, tmp_path):
        """Writing to an existing file should create a backup first."""
        tool = _make_tool(control_settings)
        target = tmp_path / "read" / "write" / "existing.txt"
        target.write_text("original")
        params = _params({
            "action": "write",
            "path": str(target),
            "content": "updated",
        })
        result = await tool.execute(params)
        assert result.success is True
        assert target.read_text() == "updated"
        # Backup should exist
        backup_dir = target.parent / ".nobla-backup"
        assert backup_dir.exists()
        backups = list(backup_dir.glob("existing.txt.*"))
        assert len(backups) >= 1

    @pytest.mark.asyncio
    async def test_list_directory(self, control_settings, tmp_path):
        tool = _make_tool(control_settings)
        read_dir = tmp_path / "read"
        (read_dir / "a.txt").write_text("aaa")
        (read_dir / "b.txt").write_text("bbb")
        params = _params({"action": "list", "path": str(read_dir)})
        result = await tool.execute(params)
        assert result.success is True
        names = [e["name"] for e in result.data["entries"]]
        assert "a.txt" in names
        assert "b.txt" in names

    @pytest.mark.asyncio
    async def test_delete_creates_backup(self, control_settings, tmp_path):
        """Deleting a file should back it up first."""
        tool = _make_tool(control_settings)
        target = tmp_path / "read" / "write" / "doomed.txt"
        target.write_text("goodbye")
        params = _params({"action": "delete", "path": str(target)})
        result = await tool.execute(params)
        assert result.success is True
        assert not target.exists()
        backup_dir = target.parent / ".nobla-backup"
        backups = list(backup_dir.glob("doomed.txt.*"))
        assert len(backups) == 1

    @pytest.mark.asyncio
    async def test_move_file(self, control_settings, tmp_path):
        tool = _make_tool(control_settings)
        write_dir = tmp_path / "read" / "write"
        src = write_dir / "source.txt"
        src.write_text("moveme")
        dst = write_dir / "dest.txt"
        params = _params({
            "action": "move",
            "path": str(src),
            "destination": str(dst),
        })
        result = await tool.execute(params)
        assert result.success is True
        assert not src.exists()
        assert dst.read_text() == "moveme"

    @pytest.mark.asyncio
    async def test_copy_file(self, control_settings, tmp_path):
        tool = _make_tool(control_settings)
        write_dir = tmp_path / "read" / "write"
        src = write_dir / "original.txt"
        src.write_text("copyme")
        dst = write_dir / "copied.txt"
        params = _params({
            "action": "copy",
            "path": str(src),
            "destination": str(dst),
        })
        result = await tool.execute(params)
        assert result.success is True
        assert src.exists()  # original still there
        assert dst.read_text() == "copyme"

    @pytest.mark.asyncio
    async def test_info(self, control_settings, tmp_path):
        tool = _make_tool(control_settings)
        target = tmp_path / "read" / "info_target.txt"
        target.write_text("some content")
        params = _params({"action": "info", "path": str(target)})
        result = await tool.execute(params)
        assert result.success is True
        data = result.data
        assert data["size"] == len("some content")
        assert data["is_dir"] is False
        assert "modified" in data
        assert "permissions" in data

    @pytest.mark.asyncio
    async def test_max_backups_pruned(self, control_settings, tmp_path):
        """Only max_backups_per_file backups should be kept; oldest pruned."""
        tool = _make_tool(control_settings)
        target = tmp_path / "read" / "write" / "pruned.txt"
        max_b = control_settings.max_backups_per_file  # default 3

        for i in range(max_b + 2):
            target.write_text(f"version-{i}")
            params = _params({
                "action": "write",
                "path": str(target),
                "content": f"version-{i + 1}",
            })
            await tool.execute(params)
            # tiny sleep to ensure distinct timestamps
            await asyncio.sleep(0.05)

        backup_dir = target.parent / ".nobla-backup"
        backups = sorted(backup_dir.glob("pruned.txt.*"))
        assert len(backups) <= max_b

    @pytest.mark.asyncio
    async def test_read_file_not_found(self, control_settings, tmp_path):
        tool = _make_tool(control_settings)
        target = tmp_path / "read" / "nonexistent.txt"
        params = _params({"action": "read", "path": str(target)})
        result = await tool.execute(params)
        assert result.success is False
        assert "not found" in result.error.lower() or "No such file" in result.error

    @pytest.mark.asyncio
    async def test_delete_file_not_found(self, control_settings, tmp_path):
        tool = _make_tool(control_settings)
        target = tmp_path / "read" / "write" / "ghost.txt"
        params = _params({"action": "delete", "path": str(target)})
        result = await tool.execute(params)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_list_nonexistent_dir(self, control_settings, tmp_path):
        tool = _make_tool(control_settings)
        target = tmp_path / "read" / "no_such_dir"
        params = _params({"action": "list", "path": str(target)})
        result = await tool.execute(params)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, control_settings, tmp_path):
        """Write should create intermediate directories if needed."""
        tool = _make_tool(control_settings)
        target = tmp_path / "read" / "write" / "sub" / "deep" / "file.txt"
        params = _params({
            "action": "write",
            "path": str(target),
            "content": "deep write",
        })
        result = await tool.execute(params)
        assert result.success is True
        assert target.read_text() == "deep write"


# ===================================================================
# Approval tests
# ===================================================================


class TestApproval:
    """Verify conditional approval based on action type."""

    @pytest.mark.parametrize("action", ["read", "list", "info"])
    def test_safe_actions_no_approval(self, control_settings, action):
        tool = _make_tool(control_settings)
        params = _params({"action": action, "path": "/any"})
        assert tool.needs_approval(params) is False

    @pytest.mark.parametrize("action", ["write", "delete", "move", "copy"])
    def test_destructive_actions_need_approval(self, control_settings, action):
        tool = _make_tool(control_settings)
        params = _params({"action": action, "path": "/any"})
        assert tool.needs_approval(params) is True


# ===================================================================
# Metadata tests
# ===================================================================


class TestMetadata:
    """Tool metadata and describe_action."""

    def test_tool_name(self, control_settings):
        tool = _make_tool(control_settings)
        assert tool.name == "file.manage"

    def test_tool_category(self, control_settings):
        tool = _make_tool(control_settings)
        assert tool.category == ToolCategory.FILE_SYSTEM

    def test_invalid_action(self, control_settings):
        tool = _make_tool(control_settings)
        params = _params({"action": "format_disk", "path": "/any"})
        with pytest.raises(ValueError, match="Invalid action"):
            asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_describe_action_read(self, control_settings, tmp_path):
        tool = _make_tool(control_settings)
        params = _params({"action": "read", "path": "/home/user/file.txt"})
        desc = tool.describe_action(params)
        assert "read" in desc.lower() or "Read" in desc

    def test_describe_action_delete(self, control_settings, tmp_path):
        tool = _make_tool(control_settings)
        params = _params({"action": "delete", "path": "/home/user/file.txt"})
        desc = tool.describe_action(params)
        assert "delete" in desc.lower() or "Delete" in desc

    def test_describe_action_move(self, control_settings, tmp_path):
        tool = _make_tool(control_settings)
        params = _params({
            "action": "move", "path": "/a.txt", "destination": "/b.txt",
        })
        desc = tool.describe_action(params)
        assert "move" in desc.lower() or "Move" in desc

    def test_get_params_summary(self, control_settings):
        tool = _make_tool(control_settings)
        params = _params({
            "action": "write", "path": "/home/user/test.txt",
            "content": "secret data",
        })
        summary = tool.get_params_summary(params)
        assert summary["action"] == "write"
        assert "path" in summary

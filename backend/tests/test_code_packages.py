"""Tests for PackageInstallTool."""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest

from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.security.sandbox import SandboxResult
from nobla.tools.models import ToolCategory, ToolParams


class TestPackageNameRegex:
    def test_valid_python_packages(self):
        from nobla.tools.code.packages import PACKAGE_NAME_RE
        valid = ["numpy", "pandas", "scikit-learn", "Flask", "requests"]
        for pkg in valid:
            assert PACKAGE_NAME_RE.match(pkg), f"{pkg} should be valid"

    def test_valid_versioned_packages(self):
        from nobla.tools.code.packages import PACKAGE_NAME_RE
        valid = ["numpy>=1.24", "pandas<2.0", "Flask>=2.0,<3.0"]
        for pkg in valid:
            assert PACKAGE_NAME_RE.match(pkg), f"{pkg} should be valid"

    def test_valid_npm_scoped_packages(self):
        from nobla.tools.code.packages import PACKAGE_NAME_RE
        valid = ["@types/node", "@vue/cli", "@angular/core"]
        for pkg in valid:
            assert PACKAGE_NAME_RE.match(pkg), f"{pkg} should be valid"

    def test_rejects_path_traversal(self):
        from nobla.tools.code.packages import PACKAGE_NAME_RE
        invalid = ["../../../etc/passwd", "./local-pkg", "/absolute/path"]
        for pkg in invalid:
            assert not PACKAGE_NAME_RE.match(pkg), f"{pkg} should be rejected"

    def test_rejects_command_injection(self):
        from nobla.tools.code.packages import PACKAGE_NAME_RE
        invalid = ["numpy; rm -rf /", "pkg && whoami", "pkg | cat /etc/passwd"]
        for pkg in invalid:
            assert not PACKAGE_NAME_RE.match(pkg), f"{pkg} should be rejected"


class TestPackageInstallTool:
    @pytest.fixture()
    def state(self):
        return ConnectionState(
            connection_id="conn12345678", user_id="u1", tier=Tier.ELEVATED.value,
        )

    def test_tool_metadata(self):
        from nobla.tools.code.packages import PackageInstallTool
        tool = PackageInstallTool()
        assert tool.name == "code.install_package"
        assert tool.category == ToolCategory.CODE
        assert tool.tier == Tier.ELEVATED
        assert tool.requires_approval is False

    @pytest.mark.asyncio
    async def test_validate_rejects_bash(self, state):
        from nobla.tools.code.packages import PackageInstallTool
        tool = PackageInstallTool()
        with pytest.raises(ValueError, match="[Bb]ash|[Pp]ackageable"):
            await tool.validate(ToolParams(
                args={"packages": ["pkg"], "language": "bash"},
                connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_validate_rejects_empty_packages(self, state):
        from nobla.tools.code.packages import PackageInstallTool
        tool = PackageInstallTool()
        with pytest.raises(ValueError, match="[Pp]ackage|[Ee]mpty"):
            await tool.validate(ToolParams(
                args={"packages": []}, connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_validate_rejects_bad_package_name(self, state):
        from nobla.tools.code.packages import PackageInstallTool
        tool = PackageInstallTool()
        with pytest.raises(ValueError, match="[Ii]nvalid|name"):
            await tool.validate(ToolParams(
                args={"packages": ["numpy; rm -rf /"]},
                connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_execute_builds_pip_command(self, state):
        from nobla.tools.code.packages import PackageInstallTool
        tool = PackageInstallTool()
        with patch("nobla.tools.code.packages.get_sandbox") as mock_gs:
            sandbox = AsyncMock()
            sandbox.execute_command = AsyncMock(return_value=SandboxResult(
                stdout="Successfully installed numpy", stderr="",
                exit_code=0, execution_time_ms=5000, timed_out=False,
            ))
            mock_gs.return_value = sandbox

            params = ToolParams(
                args={"packages": ["numpy", "pandas"], "language": "python"},
                connection_state=state,
            )
            result = await tool.execute(params)
            assert result.success is True
            assert result.data["packages"] == ["numpy", "pandas"]

            cmd = sandbox.execute_command.call_args.kwargs.get("cmd")
            if cmd is None:
                cmd = sandbox.execute_command.call_args[0][0]
            assert isinstance(cmd, list)
            assert "pip" in cmd
            assert "numpy" in cmd
            assert "pandas" in cmd

    @pytest.mark.asyncio
    async def test_execute_uses_network_true(self, state):
        from nobla.tools.code.packages import PackageInstallTool
        tool = PackageInstallTool()
        with patch("nobla.tools.code.packages.get_sandbox") as mock_gs:
            sandbox = AsyncMock()
            sandbox.execute_command = AsyncMock(return_value=SandboxResult(
                stdout="ok", stderr="", exit_code=0,
                execution_time_ms=100, timed_out=False,
            ))
            mock_gs.return_value = sandbox

            params = ToolParams(
                args={"packages": ["requests"]},
                connection_state=state,
            )
            await tool.execute(params)
            call_kwargs = sandbox.execute_command.call_args.kwargs
            assert call_kwargs.get("network") is True

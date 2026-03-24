# Phase 4C: Code Execution — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build 5 code execution tools (code.run, code.install_package, code.generate, code.debug, git.ops) that plug into the existing tool platform, enabling sandboxed code execution, package management, LLM-powered code generation, error debugging, and git operations.

**Architecture:** Each tool inherits `BaseTool`, registers via `@register_tool`. `code.run` wraps `SandboxManager` with Docker volume mounting for packages. `code.generate` and `code.debug` route through `LLMRouter`. `git.ops` is a single tool with 7 subcommands and conditional approval for push/PR. Shared `run_code()` free function in `runner.py` is used by both `CodeRunnerTool` and `CodeGenerationTool`.

**Tech Stack:** Docker (via docker-py), shlex (stdlib), re (stdlib), existing SandboxManager, existing LLMRouter

**Spec:** `docs/superpowers/specs/2026-03-24-phase4c-code-execution-design.md`

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Modify | `backend/nobla/config/settings.py` | Add `CodeExecutionSettings`, wire as `Settings.code`, update `SandboxSettings.allowed_images` |
| Modify | `backend/nobla/tools/base.py` | Add `needs_approval(params)` method |
| Modify | `backend/nobla/tools/executor.py` | Change `tool.requires_approval` → `tool.needs_approval(params)` |
| Modify | `backend/nobla/security/sandbox.py` | Add `volumes`/`network`/`environment` to `execute()`, add `execute_command()`, add `cleanup_volumes()`, extend `kill_all()` |
| Modify | `backend/nobla/tools/__init__.py` | Add `from nobla.tools import code` for auto-discovery |
| Create | `backend/nobla/tools/code/__init__.py` | Shared helpers: `get_volume_name`, `PACKAGE_ENV`, `PACKAGEABLE_LANGUAGES` |
| Create | `backend/nobla/tools/code/runner.py` | `run_code()` free function + `CodeRunnerTool` |
| Create | `backend/nobla/tools/code/packages.py` | `PackageInstallTool` |
| Create | `backend/nobla/tools/code/codegen.py` | `CodeGenerationTool` + `_extract_code()` |
| Create | `backend/nobla/tools/code/debug.py` | `DebugAssistantTool` + `_parse_error()` |
| Create | `backend/nobla/tools/code/git.py` | `GitTool` (7 subcommands, conditional approval) |
| Create | `backend/tests/test_code_settings.py` | Tests for CodeExecutionSettings + platform changes |
| Create | `backend/tests/test_code_runner.py` | Tests for CodeRunnerTool + run_code() |
| Create | `backend/tests/test_code_packages.py` | Tests for PackageInstallTool |
| Create | `backend/tests/test_code_codegen.py` | Tests for CodeGenerationTool |
| Create | `backend/tests/test_code_debug.py` | Tests for DebugAssistantTool |
| Create | `backend/tests/test_code_git.py` | Tests for GitTool |
| Create | `backend/tests/integration/test_code_flow.py` | E2E integration tests |

---

## Task 0: Settings & Platform Changes

**Files:**
- Modify: `backend/nobla/config/settings.py`
- Modify: `backend/nobla/tools/base.py`
- Modify: `backend/nobla/tools/executor.py:69`
- Create: `backend/tests/test_code_settings.py`

### Step-by-step

- [ ] **Step 1: Write failing tests for CodeExecutionSettings and platform changes**

```python
# backend/tests/test_code_settings.py
"""Tests for CodeExecutionSettings and Phase 4C platform changes."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from nobla.config.settings import CodeExecutionSettings, Settings, SandboxSettings
from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import PermissionChecker, Tier
from nobla.tools.approval import ApprovalManager
from nobla.tools.base import BaseTool
from nobla.tools.executor import ToolExecutor
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import ToolRegistry, _TOOL_REGISTRY


# --- CodeExecutionSettings ---


class TestCodeExecutionSettings:
    def test_defaults(self):
        s = CodeExecutionSettings()
        assert s.enabled is True
        assert s.default_language == "python"
        assert s.supported_languages == ["python", "javascript", "bash"]
        assert s.package_volume_prefix == "nobla-pkg"
        assert s.persist_packages is False
        assert s.max_output_length == 50000
        assert s.codegen_max_tokens == 4096
        assert s.debug_max_error_length == 5000
        assert s.git_allowed_hosts == ["github.com", "gitlab.com"]
        assert s.git_timeout == 120
        assert s.git_workspace_volume_prefix == "nobla-git"
        assert s.git_image == "alpine/git:latest"

    def test_custom_values(self):
        s = CodeExecutionSettings(
            default_language="javascript",
            persist_packages=True,
            git_allowed_hosts=["github.com", "gitlab.com", "bitbucket.org"],
        )
        assert s.default_language == "javascript"
        assert s.persist_packages is True
        assert len(s.git_allowed_hosts) == 3

    def test_wired_into_settings(self):
        s = Settings()
        assert hasattr(s, "code")
        assert isinstance(s.code, CodeExecutionSettings)
        assert s.code.enabled is True


class TestSandboxAllowedImages:
    def test_includes_code_images(self):
        s = SandboxSettings()
        assert "python:3.12-slim" in s.allowed_images
        assert "node:20-slim" in s.allowed_images
        assert "alpine/git:latest" in s.allowed_images


# --- BaseTool.needs_approval ---


class _ConditionalApprovalTool(BaseTool):
    name = "test.conditional"
    description = "Tool with conditional approval"
    category = ToolCategory.CODE
    tier = Tier.ELEVATED
    requires_approval = False

    def needs_approval(self, params: ToolParams) -> bool:
        return params.args.get("dangerous", False)

    async def execute(self, params: ToolParams) -> ToolResult:
        return ToolResult(success=True, data="done")


class _StaticApprovalTool(BaseTool):
    name = "test.static_approval"
    description = "Tool with static approval"
    category = ToolCategory.CODE
    tier = Tier.STANDARD
    requires_approval = True

    async def execute(self, params: ToolParams) -> ToolResult:
        return ToolResult(success=True, data="done")


class TestNeedsApproval:
    def test_default_returns_class_variable_false(self):
        tool = _ConditionalApprovalTool()
        # When not overridden, would return self.requires_approval
        base_tool = _StaticApprovalTool()
        state = ConnectionState(
            connection_id="c1", user_id="u1", tier=Tier.ADMIN.value
        )
        params = ToolParams(args={}, connection_state=state)
        # Static tool uses default needs_approval -> returns self.requires_approval
        assert base_tool.needs_approval(params) is True

    def test_override_returns_false_for_safe_params(self):
        tool = _ConditionalApprovalTool()
        state = ConnectionState(
            connection_id="c1", user_id="u1", tier=Tier.ELEVATED.value
        )
        params = ToolParams(args={"dangerous": False}, connection_state=state)
        assert tool.needs_approval(params) is False

    def test_override_returns_true_for_dangerous_params(self):
        tool = _ConditionalApprovalTool()
        state = ConnectionState(
            connection_id="c1", user_id="u1", tier=Tier.ELEVATED.value
        )
        params = ToolParams(args={"dangerous": True}, connection_state=state)
        assert tool.needs_approval(params) is True


# --- ToolExecutor uses needs_approval ---


class TestExecutorUsesNeedsApproval:
    @pytest.fixture()
    def state(self):
        return ConnectionState(
            connection_id="conn1", user_id="user1", tier=Tier.ELEVATED.value
        )

    @pytest.fixture()
    def executor(self):
        _TOOL_REGISTRY.clear()
        registry = ToolRegistry()
        cond_tool = _ConditionalApprovalTool()
        _TOOL_REGISTRY[cond_tool.name] = cond_tool
        checker = PermissionChecker()
        audit = AsyncMock()
        approvals = ApprovalManager()
        return ToolExecutor(registry, checker, audit, approvals)

    @pytest.mark.asyncio
    async def test_no_approval_when_needs_approval_false(self, executor, state):
        params = ToolParams(
            args={"dangerous": False}, connection_state=state
        )
        result = await executor.execute("test.conditional", params)
        assert result.success is True
        assert result.approval_was_required is False

    @pytest.mark.asyncio
    async def test_approval_triggered_when_needs_approval_true(self, executor, state):
        params = ToolParams(
            args={"dangerous": True}, connection_state=state
        )
        # No one resolves the approval, so it should time out
        # Use a tool with short timeout for test speed
        tool = _TOOL_REGISTRY["test.conditional"]
        tool.approval_timeout = 1
        result = await executor.execute("test.conditional", params)
        assert result.success is False
        assert result.approval_was_required is True
        assert "timed_out" in result.error
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_code_settings.py -v`
Expected: FAIL — `CodeExecutionSettings` not defined, `needs_approval` not found

- [ ] **Step 3: Add CodeExecutionSettings to settings.py**

Add after `VisionSettings` in `backend/nobla/config/settings.py`:

```python
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
```

Wire into `Settings` class — add after the `vision` field:

```python
    code: CodeExecutionSettings = Field(default_factory=CodeExecutionSettings)
```

Update `SandboxSettings.allowed_images` default:

```python
    allowed_images: list[str] = ["python:3.12-slim", "node:20-slim", "bash:5", "alpine/git:latest"]
```

- [ ] **Step 4: Add needs_approval() to BaseTool**

Add after `get_params_summary()` in `backend/nobla/tools/base.py`:

```python
    def needs_approval(self, params: ToolParams) -> bool:
        """Whether this action needs user approval. Override for conditional logic."""
        return self.requires_approval
```

- [ ] **Step 5: Change executor approval check**

In `backend/nobla/tools/executor.py`, line 69, change:

```python
        if tool.requires_approval:
```

to:

```python
        if tool.needs_approval(params):
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_code_settings.py -v`
Expected: ALL PASS

- [ ] **Step 7: Run existing tests to verify no regressions**

Run: `cd backend && python -m pytest tests/test_tool_executor.py tests/test_tool_base.py tests/test_tool_settings.py -v`
Expected: ALL PASS (needs_approval default is backward-compatible)

- [ ] **Step 8: Commit**

```bash
git add backend/nobla/config/settings.py backend/nobla/tools/base.py backend/nobla/tools/executor.py backend/tests/test_code_settings.py
git commit -m "feat(tools): add CodeExecutionSettings and needs_approval() support"
```

---

## Task 1: SandboxManager Changes

**Files:**
- Modify: `backend/nobla/security/sandbox.py`
- Modify: `backend/tests/test_sandbox.py`

### Step-by-step

- [ ] **Step 1: Write failing tests for SandboxManager changes**

Append to `backend/tests/test_sandbox.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch


class TestSandboxExecuteExtended:
    """Tests for new volumes/network/environment params on execute()."""

    def test_execute_signature_accepts_new_params(self):
        """Verify the extended signature doesn't raise TypeError."""
        import inspect
        sig = inspect.signature(SandboxManager.execute)
        params = list(sig.parameters.keys())
        assert "network" in params
        assert "volumes" in params
        assert "environment" in params

    @pytest.mark.asyncio
    async def test_execute_defaults_preserve_behavior(self):
        """None defaults should not change existing Docker call."""
        cfg = SandboxConfig()
        mgr = SandboxManager(cfg)
        # Without Docker, should return Docker SDK not available
        result = await mgr.execute("print('hi')", "python")
        assert result.exit_code == 1 or "Docker" in result.stderr or result.stdout == "hi\n"


class TestSandboxExecuteCommand:
    """Tests for new execute_command() method."""

    def test_execute_command_exists(self):
        cfg = SandboxConfig()
        mgr = SandboxManager(cfg)
        assert hasattr(mgr, "execute_command")
        assert asyncio.iscoroutinefunction(mgr.execute_command)

    @pytest.mark.asyncio
    async def test_execute_command_rejects_unallowed_image(self):
        cfg = SandboxConfig(allowed_images=["python:3.12-slim"])
        mgr = SandboxManager(cfg)
        result = await mgr.execute_command(
            cmd=["echo", "test"],
            image="evil:latest",
        )
        assert result.exit_code == 1
        assert "not allowed" in result.stderr.lower() or "not in" in result.stderr.lower()


class TestSandboxCleanupVolumes:
    """Tests for cleanup_volumes() method."""

    def test_cleanup_volumes_exists(self):
        cfg = SandboxConfig()
        mgr = SandboxManager(cfg)
        assert hasattr(mgr, "cleanup_volumes")
        assert asyncio.iscoroutinefunction(mgr.cleanup_volumes)

    @pytest.mark.asyncio
    async def test_cleanup_volumes_no_docker_no_crash(self):
        """cleanup_volumes should not raise if Docker is unavailable."""
        cfg = SandboxConfig()
        mgr = SandboxManager(cfg)
        await mgr.cleanup_volumes("nobla-test")  # Should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_sandbox.py -v`
Expected: FAIL — missing `network`/`volumes`/`environment` params, no `execute_command`, no `cleanup_volumes`

- [ ] **Step 3: Extend SandboxManager.execute() with new params**

In `backend/nobla/security/sandbox.py`, modify the `execute()` method signature and body:

```python
    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout: int | None = None,
        network: bool | None = None,
        volumes: dict[str, str] | None = None,
        environment: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Execute code in a Docker container. Requires Docker daemon running."""
        import time
        image = self.get_image(language)
        if not image:
            return SandboxResult(
                stdout="", stderr=f"Unsupported language: {language}",
                exit_code=1, execution_time_ms=0, timed_out=False,
            )

        timeout = timeout or self.config.timeout_seconds
        net_enabled = network if network is not None else self.config.network_enabled

        # Build Docker volume mounts
        docker_volumes = None
        if volumes:
            docker_volumes = {
                name: {"bind": path, "mode": "rw"}
                for name, path in volumes.items()
            }

        # Build tmpfs mounts — extend when volumes present
        tmpfs = {"/tmp": "size=64m"}
        if volumes:
            tmpfs.update({"/root": "size=32m", "/home": "size=32m"})

        try:
            import docker
            if not self._client:
                self._client = docker.from_env()

            start = time.monotonic()
            container = self._client.containers.run(
                image=image,
                command=self._build_command(code, language),
                detach=True,
                mem_limit=self.config.memory_limit,
                nano_cpus=int(self.config.cpu_limit * 1e9),
                network_mode="none" if not net_enabled else "bridge",
                runtime="runsc" if self.config.runtime == "gvisor" else None,
                read_only=True,
                tmpfs=tmpfs,
                volumes=docker_volumes,
                environment=environment,
            )

            try:
                result = container.wait(timeout=timeout)
                elapsed = int((time.monotonic() - start) * 1000)
                stdout = container.logs(stdout=True, stderr=False).decode()
                stderr = container.logs(stdout=False, stderr=True).decode()
                return SandboxResult(
                    stdout=stdout, stderr=stderr,
                    exit_code=result.get("StatusCode", -1),
                    execution_time_ms=elapsed, timed_out=False,
                )
            except Exception:
                elapsed = int((time.monotonic() - start) * 1000)
                container.kill()
                return SandboxResult(
                    stdout="", stderr="Execution timed out",
                    exit_code=-1, execution_time_ms=elapsed, timed_out=True,
                )
            finally:
                container.remove(force=True)

        except ImportError:
            return SandboxResult(
                stdout="", stderr="Docker SDK not available",
                exit_code=1, execution_time_ms=0, timed_out=False,
            )
        except Exception as e:
            logger.error("sandbox_error", error=str(e))
            return SandboxResult(
                stdout="", stderr=str(e),
                exit_code=1, execution_time_ms=0, timed_out=False,
            )
```

- [ ] **Step 4: Add execute_command() method**

Add after `execute()` in `backend/nobla/security/sandbox.py`:

```python
    async def execute_command(
        self,
        cmd: list[str],
        image: str,
        timeout: int | None = None,
        network: bool | None = None,
        volumes: dict[str, str] | None = None,
        environment: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Execute a pre-built command list in a container.

        Used by PackageInstallTool and GitTool where the command is
        a safe list rather than a code snippet + language.
        """
        import time

        if image not in self.config.allowed_images:
            return SandboxResult(
                stdout="",
                stderr=f"Image '{image}' not in allowed_images",
                exit_code=1, execution_time_ms=0, timed_out=False,
            )

        timeout = timeout or self.config.timeout_seconds
        net_enabled = network if network is not None else self.config.network_enabled
        docker_volumes = (
            {n: {"bind": p, "mode": "rw"} for n, p in volumes.items()}
            if volumes else None
        )
        tmpfs = {"/tmp": "size=64m"}
        if volumes:
            tmpfs.update({"/root": "size=32m", "/home": "size=32m"})

        try:
            import docker
            if not self._client:
                self._client = docker.from_env()

            start = time.monotonic()
            container = self._client.containers.run(
                image=image,
                command=cmd,
                detach=True,
                mem_limit=self.config.memory_limit,
                nano_cpus=int(self.config.cpu_limit * 1e9),
                network_mode="none" if not net_enabled else "bridge",
                runtime="runsc" if self.config.runtime == "gvisor" else None,
                read_only=True,
                tmpfs=tmpfs,
                volumes=docker_volumes,
                environment=environment,
            )

            try:
                result = container.wait(timeout=timeout)
                elapsed = int((time.monotonic() - start) * 1000)
                stdout = container.logs(stdout=True, stderr=False).decode()
                stderr = container.logs(stdout=False, stderr=True).decode()
                return SandboxResult(
                    stdout=stdout, stderr=stderr,
                    exit_code=result.get("StatusCode", -1),
                    execution_time_ms=elapsed, timed_out=False,
                )
            except Exception:
                elapsed = int((time.monotonic() - start) * 1000)
                container.kill()
                return SandboxResult(
                    stdout="", stderr="Execution timed out",
                    exit_code=-1, execution_time_ms=elapsed, timed_out=True,
                )
            finally:
                container.remove(force=True)

        except ImportError:
            return SandboxResult(
                stdout="", stderr="Docker SDK not available",
                exit_code=1, execution_time_ms=0, timed_out=False,
            )
        except Exception as e:
            logger.error("sandbox_execute_command_error", error=str(e))
            return SandboxResult(
                stdout="", stderr=str(e),
                exit_code=1, execution_time_ms=0, timed_out=False,
            )
```

- [ ] **Step 5: Add cleanup_volumes() and extend kill_all()**

Add after `execute_command()` in `backend/nobla/security/sandbox.py`:

```python
    async def cleanup_volumes(self, prefix: str) -> None:
        """Remove all Docker volumes whose name starts with prefix."""
        try:
            import docker
            if not self._client:
                self._client = docker.from_env()
            volumes = self._client.volumes.list()
            for vol in volumes:
                if vol.name.startswith(prefix):
                    try:
                        vol.remove(force=True)
                    except Exception:
                        pass
        except Exception as e:
            logger.error("cleanup_volumes_error", prefix=prefix, error=str(e))
```

Extend the existing `kill_all()` — add volume cleanup at the end:

```python
    async def kill_all(self) -> None:
        """Kill all running sandbox containers. Used by kill switch."""
        try:
            import docker
            if not self._client:
                self._client = docker.from_env()
            containers = self._client.containers.list(
                filters={"ancestor": list(LANGUAGE_IMAGES.values())}
            )
            for c in containers:
                try:
                    c.kill()
                    c.remove(force=True)
                except Exception:
                    pass
        except Exception as e:
            logger.error("kill_all_error", error=str(e))

        # Clean up code execution volumes (use lazy singleton, not bare constructor)
        from nobla.tools.code.runner import get_settings as _get_settings
        try:
            s = _get_settings()
            await self.cleanup_volumes(s.code.package_volume_prefix)
            await self.cleanup_volumes(s.code.git_workspace_volume_prefix)
        except Exception as e:
            logger.error("kill_all_volume_cleanup_error", error=str(e))
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_sandbox.py -v`
Expected: ALL PASS

- [ ] **Step 7: Run existing sandbox tests for regression**

Run: `cd backend && python -m pytest tests/test_sandbox.py tests/test_killswitch.py -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add backend/nobla/security/sandbox.py backend/tests/test_sandbox.py
git commit -m "feat(sandbox): add volumes, network, environment params and execute_command()"
```

---

## Task 2: Shared Helpers & CodeRunnerTool

**Files:**
- Create: `backend/nobla/tools/code/__init__.py`
- Create: `backend/nobla/tools/code/runner.py`
- Create: `backend/tests/test_code_runner.py`

### Step-by-step

- [ ] **Step 1: Write failing tests for shared helpers and CodeRunnerTool**

```python
# backend/tests/test_code_runner.py
"""Tests for code execution shared helpers and CodeRunnerTool."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.security.sandbox import SandboxResult
from nobla.tools.models import ToolCategory, ToolParams, ToolResult


# --- Shared helpers ---


class TestSharedHelpers:
    def test_packageable_languages(self):
        from nobla.tools.code import PACKAGEABLE_LANGUAGES
        assert "python" in PACKAGEABLE_LANGUAGES
        assert "javascript" in PACKAGEABLE_LANGUAGES
        assert "bash" not in PACKAGEABLE_LANGUAGES

    def test_package_env(self):
        from nobla.tools.code import PACKAGE_ENV
        assert "PYTHONPATH" in PACKAGE_ENV["python"]
        assert "NODE_PATH" in PACKAGE_ENV["javascript"]
        assert "/packages/node/node_modules" in PACKAGE_ENV["javascript"]["NODE_PATH"]

    def test_get_volume_name(self):
        from nobla.tools.code import get_volume_name
        name = get_volume_name("nobla-pkg", "python", "abcdef1234567890")
        assert name == "nobla-pkg-python-abcdef12"

    def test_get_volume_name_truncates_connection_id(self):
        from nobla.tools.code import get_volume_name
        name = get_volume_name("prefix", "js", "short")
        assert name == "prefix-js-short"


# --- run_code free function ---


class TestRunCode:
    @pytest.fixture()
    def mock_sandbox(self):
        with patch("nobla.tools.code.runner.get_sandbox") as mock:
            sandbox = AsyncMock()
            sandbox.execute = AsyncMock(return_value=SandboxResult(
                stdout="hello\n", stderr="", exit_code=0,
                execution_time_ms=100, timed_out=False,
            ))
            mock.return_value = sandbox
            yield sandbox

    @pytest.mark.asyncio
    async def test_run_code_python_with_volume(self, mock_sandbox):
        from nobla.tools.code.runner import run_code
        result = await run_code("print('hi')", "python", "conn12345678")
        mock_sandbox.execute.assert_awaited_once()
        call_kwargs = mock_sandbox.execute.call_args
        assert call_kwargs.kwargs.get("volumes") is not None
        assert "python" in list(call_kwargs.kwargs["volumes"].keys())[0]
        assert result.stdout == "hello\n"

    @pytest.mark.asyncio
    async def test_run_code_bash_no_volume(self, mock_sandbox):
        from nobla.tools.code.runner import run_code
        await run_code("echo hi", "bash", "conn12345678")
        call_kwargs = mock_sandbox.execute.call_args
        assert call_kwargs.kwargs.get("volumes") is None

    @pytest.mark.asyncio
    async def test_run_code_sets_environment(self, mock_sandbox):
        from nobla.tools.code.runner import run_code
        await run_code("print('hi')", "python", "conn12345678")
        call_kwargs = mock_sandbox.execute.call_args
        env = call_kwargs.kwargs.get("environment")
        assert env is not None
        assert "PYTHONPATH" in env


# --- CodeRunnerTool ---


class TestCodeRunnerTool:
    @pytest.fixture()
    def state(self):
        return ConnectionState(
            connection_id="conn12345678", user_id="u1", tier=Tier.STANDARD.value
        )

    @pytest.fixture()
    def mock_sandbox(self):
        with patch("nobla.tools.code.runner.get_sandbox") as mock:
            sandbox = AsyncMock()
            sandbox.execute = AsyncMock(return_value=SandboxResult(
                stdout="result\n", stderr="", exit_code=0,
                execution_time_ms=50, timed_out=False,
            ))
            mock.return_value = sandbox
            yield sandbox

    def test_tool_metadata(self):
        from nobla.tools.code.runner import CodeRunnerTool
        tool = CodeRunnerTool()
        assert tool.name == "code.run"
        assert tool.category == ToolCategory.CODE
        assert tool.tier == Tier.STANDARD
        assert tool.requires_approval is False

    @pytest.mark.asyncio
    async def test_validate_rejects_empty_code(self, state):
        from nobla.tools.code.runner import CodeRunnerTool
        tool = CodeRunnerTool()
        with pytest.raises(ValueError, match="[Cc]ode.*required|empty"):
            await tool.validate(ToolParams(args={"code": ""}, connection_state=state))

    @pytest.mark.asyncio
    async def test_validate_rejects_unsupported_language(self, state):
        from nobla.tools.code.runner import CodeRunnerTool
        tool = CodeRunnerTool()
        with pytest.raises(ValueError, match="[Uu]nsupported|language"):
            await tool.validate(ToolParams(
                args={"code": "x", "language": "ruby"}, connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_execute_returns_structured_result(self, state, mock_sandbox):
        from nobla.tools.code.runner import CodeRunnerTool
        tool = CodeRunnerTool()
        params = ToolParams(
            args={"code": "print('hi')", "language": "python"},
            connection_state=state,
        )
        result = await tool.execute(params)
        assert result.success is True
        assert result.data["stdout"] == "result\n"
        assert result.data["exit_code"] == 0
        assert result.data["language"] == "python"
        assert "truncated" in result.data

    @pytest.mark.asyncio
    async def test_execute_truncates_long_output(self, state):
        long_output = "x" * 100000
        with patch("nobla.tools.code.runner.get_sandbox") as mock:
            sandbox = AsyncMock()
            sandbox.execute = AsyncMock(return_value=SandboxResult(
                stdout=long_output, stderr="", exit_code=0,
                execution_time_ms=50, timed_out=False,
            ))
            mock.return_value = sandbox

            from nobla.tools.code.runner import CodeRunnerTool
            tool = CodeRunnerTool()
            params = ToolParams(
                args={"code": "x", "language": "python"},
                connection_state=state,
            )
            result = await tool.execute(params)
            assert result.data["truncated"] is True
            assert len(result.data["stdout"]) <= 50001  # max_output_length + margin
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_code_runner.py -v`
Expected: FAIL — modules don't exist yet

- [ ] **Step 3: Create shared helpers in tools/code/__init__.py**

```python
# backend/nobla/tools/code/__init__.py
"""Code execution tools — auto-discovery and shared helpers."""
from __future__ import annotations

PACKAGEABLE_LANGUAGES = {"python", "javascript"}

PACKAGE_MOUNT = "/packages"

PACKAGE_ENV: dict[str, dict[str, str]] = {
    "python": {"PYTHONPATH": "/packages/python"},
    "javascript": {"NODE_PATH": "/packages/node/node_modules"},
}


def get_volume_name(prefix: str, language: str, connection_id: str) -> str:
    """Build a Docker volume name. Shared by runner and packages tools."""
    return f"{prefix}-{language}-{connection_id[:8]}"


# Auto-discovery: importing submodules triggers @register_tool decorators.
from nobla.tools.code import runner  # noqa: E402, F401
from nobla.tools.code import packages  # noqa: E402, F401
from nobla.tools.code import codegen  # noqa: E402, F401
from nobla.tools.code import debug  # noqa: E402, F401
from nobla.tools.code import git  # noqa: E402, F401
```

**Note:** The submodule imports at the bottom will fail until those files are created. During Task 2 implementation, temporarily comment out imports for `packages`, `codegen`, `debug`, and `git`. Uncomment each as the corresponding task completes. Final wiring happens in Task 7.

Temporary version for Task 2:

```python
from nobla.tools.code import runner  # noqa: E402, F401
# from nobla.tools.code import packages  # noqa: E402, F401  -- Task 3
# from nobla.tools.code import codegen  # noqa: E402, F401  -- Task 4
# from nobla.tools.code import debug  # noqa: E402, F401  -- Task 5
# from nobla.tools.code import git  # noqa: E402, F401  -- Task 6
```

- [ ] **Step 4: Create CodeRunnerTool in runner.py**

```python
# backend/nobla/tools/code/runner.py
"""CodeRunnerTool — sandboxed code execution with package volume support."""
from __future__ import annotations

from nobla.config.settings import Settings
from nobla.security.permissions import Tier
from nobla.security.sandbox import SandboxConfig, SandboxManager, SandboxResult
from nobla.tools.base import BaseTool
from nobla.tools.code import PACKAGE_ENV, PACKAGEABLE_LANGUAGES, get_volume_name
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool

_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


_sandbox: SandboxManager | None = None


def get_sandbox() -> SandboxManager:
    global _sandbox
    if _sandbox is None:
        s = get_settings().sandbox
        _sandbox = SandboxManager(SandboxConfig(
            runtime=s.runtime,
            memory_limit=s.memory_limit,
            cpu_limit=s.cpu_limit,
            timeout_seconds=s.timeout_seconds,
            network_enabled=s.network_enabled,
            allowed_images=s.allowed_images,
        ))
    return _sandbox


async def run_code(
    code: str, language: str, connection_id: str, timeout: int | None = None,
) -> SandboxResult:
    """Run code in sandbox with package volume. Shared by runner and codegen."""
    settings = get_settings()
    sandbox = get_sandbox()

    volumes = None
    env = None
    if language in PACKAGEABLE_LANGUAGES:
        vol_name = get_volume_name(
            settings.code.package_volume_prefix, language, connection_id,
        )
        mount_path = f"/packages/{language}"
        volumes = {vol_name: mount_path}
        env = PACKAGE_ENV.get(language)

    return await sandbox.execute(
        code, language, timeout=timeout, volumes=volumes, environment=env,
    )


@register_tool
class CodeRunnerTool(BaseTool):
    name = "code.run"
    description = "Execute code in a sandboxed container"
    category = ToolCategory.CODE
    tier = Tier.STANDARD
    requires_approval = False

    async def validate(self, params: ToolParams) -> None:
        settings = get_settings()
        if not settings.code.enabled:
            raise ValueError("Code tools disabled in settings")
        code = params.args.get("code", "")
        if not code or not code.strip():
            raise ValueError("Code is required and cannot be empty")
        lang = params.args.get("language", settings.code.default_language)
        if lang not in settings.code.supported_languages:
            raise ValueError(
                f"Unsupported language '{lang}'. "
                f"Supported: {settings.code.supported_languages}"
            )

    def describe_action(self, params: ToolParams) -> str:
        lang = params.args.get("language", get_settings().code.default_language)
        code_preview = params.args.get("code", "")[:60]
        return f"Run {lang} code: {code_preview!r}"

    async def execute(self, params: ToolParams) -> ToolResult:
        settings = get_settings()
        code = params.args["code"]
        language = params.args.get("language", settings.code.default_language)
        timeout = params.args.get("timeout")
        connection_id = params.connection_state.connection_id

        try:
            result = await run_code(code, language, connection_id, timeout)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

        max_len = settings.code.max_output_length
        stdout = result.stdout
        stderr = result.stderr
        truncated = False
        if len(stdout) > max_len:
            stdout = stdout[:max_len]
            truncated = True
        if len(stderr) > max_len:
            stderr = stderr[:max_len]
            truncated = True

        return ToolResult(
            success=result.exit_code == 0,
            data={
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": result.exit_code,
                "language": language,
                "timed_out": result.timed_out,
                "truncated": truncated,
                "execution_time_ms": result.execution_time_ms,
            },
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_code_runner.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/tools/code/__init__.py backend/nobla/tools/code/runner.py backend/tests/test_code_runner.py
git commit -m "feat(tools): add CodeRunnerTool with run_code() shared function"
```

---

## Task 3: PackageInstallTool

**Files:**
- Create: `backend/nobla/tools/code/packages.py`
- Create: `backend/tests/test_code_packages.py`
- Modify: `backend/nobla/tools/code/__init__.py` (uncomment packages import)

### Step-by-step

- [ ] **Step 1: Write failing tests for PackageInstallTool**

```python
# backend/tests/test_code_packages.py
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

    def test_rejects_shell_injection(self):
        from nobla.tools.code.packages import PACKAGE_NAME_RE
        invalid = ["numpy; rm -rf /", "pkg && curl evil.com", "$(whoami)"]
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

            # Verify command was built as a list (not string)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_code_packages.py -v`
Expected: FAIL — `PackageInstallTool` doesn't exist

- [ ] **Step 3: Create PackageInstallTool**

```python
# backend/nobla/tools/code/packages.py
"""PackageInstallTool — install pip/npm packages into shared Docker volume."""
from __future__ import annotations

import re

from nobla.config.settings import Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.code import PACKAGEABLE_LANGUAGES, get_volume_name
from nobla.tools.code.runner import get_sandbox, get_settings
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool

PACKAGE_NAME_RE = re.compile(
    r"^[@a-zA-Z0-9][a-zA-Z0-9_\-\.]*"
    r"(/[a-zA-Z0-9][a-zA-Z0-9_\-\.]*)*"
    r"(\[[\w,]+\])?"
    r"([>=<!][^\s,]+)?(,[^\s,]+)*$"
)

_INSTALL_CMD = {
    "python": lambda pkgs: [
        "pip", "install", "--no-cache-dir", "--target", "/packages/python", *pkgs,
    ],
    "javascript": lambda pkgs: [
        "npm", "install", "--prefix", "/packages/node", *pkgs,
    ],
}

_INSTALL_IMAGE = {
    "python": "python:3.12-slim",
    "javascript": "node:20-slim",
}


@register_tool
class PackageInstallTool(BaseTool):
    name = "code.install_package"
    description = "Install packages (pip/npm) into the sandbox environment"
    category = ToolCategory.CODE
    tier = Tier.ELEVATED
    requires_approval = False

    async def validate(self, params: ToolParams) -> None:
        settings = get_settings()
        if not settings.code.enabled:
            raise ValueError("Code tools disabled in settings")
        packages = params.args.get("packages", [])
        if not packages:
            raise ValueError("Packages list is required and cannot be empty")
        lang = params.args.get("language", settings.code.default_language)
        if lang not in PACKAGEABLE_LANGUAGES:
            raise ValueError(
                f"Language '{lang}' does not support package installation. "
                f"Supported: {sorted(PACKAGEABLE_LANGUAGES)}"
            )
        for pkg in packages:
            if not PACKAGE_NAME_RE.match(pkg):
                raise ValueError(
                    f"Invalid package name: {pkg!r}. "
                    "Names must be alphanumeric with optional scope/version."
                )

    def describe_action(self, params: ToolParams) -> str:
        pkgs = params.args.get("packages", [])
        lang = params.args.get("language", get_settings().code.default_language)
        return f"Install {lang} packages: {', '.join(pkgs[:5])}"

    async def execute(self, params: ToolParams) -> ToolResult:
        settings = get_settings()
        packages = params.args["packages"]
        language = params.args.get("language", settings.code.default_language)
        connection_id = params.connection_state.connection_id

        cmd = _INSTALL_CMD[language](packages)
        image = _INSTALL_IMAGE[language]
        vol_name = get_volume_name(
            settings.code.package_volume_prefix, language, connection_id,
        )
        volumes = {vol_name: f"/packages/{language}"}

        try:
            result = await get_sandbox().execute_command(
                cmd=cmd, image=image, network=True, volumes=volumes,
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

        max_len = settings.code.max_output_length
        output = (result.stdout + result.stderr)[:max_len]

        return ToolResult(
            success=result.exit_code == 0,
            data={
                "success": result.exit_code == 0,
                "packages": packages,
                "output": output,
                "language": language,
            },
        )
```

- [ ] **Step 4: Uncomment packages import in tools/code/__init__.py**

In `backend/nobla/tools/code/__init__.py`, uncomment:

```python
from nobla.tools.code import packages  # noqa: E402, F401
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_code_packages.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/tools/code/packages.py backend/nobla/tools/code/__init__.py backend/tests/test_code_packages.py
git commit -m "feat(tools): add PackageInstallTool with safety regex and volume support"
```

---

## Task 4: CodeGenerationTool

**Files:**
- Create: `backend/nobla/tools/code/codegen.py`
- Create: `backend/tests/test_code_codegen.py`
- Modify: `backend/nobla/tools/code/__init__.py` (uncomment codegen import)

### Step-by-step

- [ ] **Step 1: Write failing tests for CodeGenerationTool**

```python
# backend/tests/test_code_codegen.py
"""Tests for CodeGenerationTool and _extract_code helper."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.security.sandbox import SandboxResult
from nobla.tools.models import ToolCategory, ToolParams


class TestExtractCode:
    def test_strips_python_fences(self):
        from nobla.tools.code.codegen import _extract_code
        raw = "```python\nprint('hi')\n```"
        assert _extract_code(raw) == "print('hi')"

    def test_strips_bare_fences(self):
        from nobla.tools.code.codegen import _extract_code
        raw = "```\nprint('hi')\n```"
        assert _extract_code(raw) == "print('hi')"

    def test_no_fences_returns_stripped(self):
        from nobla.tools.code.codegen import _extract_code
        raw = "  print('hi')  "
        assert _extract_code(raw) == "print('hi')"

    def test_multiple_fences_takes_first(self):
        from nobla.tools.code.codegen import _extract_code
        raw = "```python\nfirst()\n```\ntext\n```python\nsecond()\n```"
        assert _extract_code(raw) == "first()"


class TestCodeGenerationTool:
    @pytest.fixture()
    def state(self):
        return ConnectionState(
            connection_id="conn12345678", user_id="u1", tier=Tier.STANDARD.value,
        )

    def test_tool_metadata(self):
        from nobla.tools.code.codegen import CodeGenerationTool
        tool = CodeGenerationTool()
        assert tool.name == "code.generate"
        assert tool.category == ToolCategory.CODE
        assert tool.tier == Tier.STANDARD
        assert tool.requires_approval is False

    @pytest.mark.asyncio
    async def test_validate_rejects_empty_description(self, state):
        from nobla.tools.code.codegen import CodeGenerationTool
        tool = CodeGenerationTool()
        with pytest.raises(ValueError, match="[Dd]escription|empty"):
            await tool.validate(ToolParams(
                args={"description": ""}, connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_execute_generate_only(self, state):
        from nobla.tools.code.codegen import CodeGenerationTool
        tool = CodeGenerationTool()

        mock_response = MagicMock()
        mock_response.content = "```python\nprint('hello')\n```"

        with patch("nobla.tools.code.codegen.get_router") as mock_router:
            router = AsyncMock()
            router.route = AsyncMock(return_value=mock_response)
            mock_router.return_value = router

            params = ToolParams(
                args={"description": "print hello", "language": "python"},
                connection_state=state,
            )
            result = await tool.execute(params)

            assert result.success is True
            assert result.data["code"] == "print('hello')"
            assert result.data["language"] == "python"
            assert result.data["execution"] is None

    @pytest.mark.asyncio
    async def test_execute_generate_and_run(self, state):
        from nobla.tools.code.codegen import CodeGenerationTool
        tool = CodeGenerationTool()

        mock_response = MagicMock()
        mock_response.content = "print('hello')"

        with patch("nobla.tools.code.codegen.get_router") as mock_router, \
             patch("nobla.tools.code.codegen.run_code") as mock_run:
            router = AsyncMock()
            router.route = AsyncMock(return_value=mock_response)
            mock_router.return_value = router
            mock_run.return_value = SandboxResult(
                stdout="hello\n", stderr="", exit_code=0,
                execution_time_ms=100, timed_out=False,
            )

            params = ToolParams(
                args={
                    "description": "print hello",
                    "language": "python",
                    "run": True,
                },
                connection_state=state,
            )
            result = await tool.execute(params)

            assert result.success is True
            assert result.data["execution"] is not None
            assert result.data["execution"]["stdout"] == "hello\n"
            assert result.data["execution"]["exit_code"] == 0
            assert "execution_time_ms" in result.data["execution"]
            mock_run.assert_awaited_once_with(
                "print('hello')", "python", "conn12345678",
            )

    @pytest.mark.asyncio
    async def test_execute_passes_max_tokens(self, state):
        from nobla.tools.code.codegen import CodeGenerationTool
        tool = CodeGenerationTool()

        mock_response = MagicMock()
        mock_response.content = "x = 1"

        with patch("nobla.tools.code.codegen.get_router") as mock_router:
            router = AsyncMock()
            router.route = AsyncMock(return_value=mock_response)
            mock_router.return_value = router

            params = ToolParams(
                args={"description": "assign x"},
                connection_state=state,
            )
            await tool.execute(params)
            call_kwargs = router.route.call_args.kwargs
            assert "max_tokens" in call_kwargs
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_code_codegen.py -v`
Expected: FAIL

- [ ] **Step 3: Create CodeGenerationTool**

```python
# backend/nobla/tools/code/codegen.py
"""CodeGenerationTool — LLM-powered code generation with optional execution."""
from __future__ import annotations

import re

from nobla.brain.base_provider import LLMMessage
from nobla.brain.router import LLMRouter
from nobla.config.settings import Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.code.runner import get_settings, run_code
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool

_router: LLMRouter | None = None


def get_router() -> LLMRouter:
    """Lazy singleton for LLM router. Wired during app startup or first call."""
    global _router
    if _router is None:
        # Import here to avoid circular deps at module level.
        # In production, the router is injected via set_router().
        raise RuntimeError(
            "LLM router not initialized. Call set_router() during app startup."
        )
    return _router


def set_router(router: LLMRouter) -> None:
    """Inject the LLM router instance. Called during app startup."""
    global _router
    _router = router


_CODEGEN_SYSTEM_PROMPT = (
    "You are a code generator. Output ONLY executable {language} code. "
    "No explanations, no markdown fences, no comments unless critical. "
    "The code must be self-contained and runnable."
)


def _extract_code(response: str) -> str:
    """Strip markdown code fences from LLM response."""
    match = re.search(r"```(?:\w*)\n(.*?)```", response, re.DOTALL)
    return match.group(1).strip() if match else response.strip()


@register_tool
class CodeGenerationTool(BaseTool):
    name = "code.generate"
    description = "Generate code from a natural language description"
    category = ToolCategory.CODE
    tier = Tier.STANDARD
    requires_approval = False

    async def validate(self, params: ToolParams) -> None:
        settings = get_settings()
        if not settings.code.enabled:
            raise ValueError("Code tools disabled in settings")
        desc = params.args.get("description", "")
        if not desc or not desc.strip():
            raise ValueError("Description is required and cannot be empty")
        lang = params.args.get("language", settings.code.default_language)
        if lang not in settings.code.supported_languages:
            raise ValueError(
                f"Unsupported language '{lang}'. "
                f"Supported: {settings.code.supported_languages}"
            )

    def describe_action(self, params: ToolParams) -> str:
        desc = params.args.get("description", "")[:80]
        lang = params.args.get("language", get_settings().code.default_language)
        return f"Generate {lang} code: {desc!r}"

    async def execute(self, params: ToolParams) -> ToolResult:
        settings = get_settings()
        description = params.args["description"]
        language = params.args.get("language", settings.code.default_language)
        should_run = params.args.get("run", False)
        context = params.args.get("context", "")

        # Build LLM messages
        system = _CODEGEN_SYSTEM_PROMPT.format(language=language)
        user_content = description
        if context:
            user_content = f"{description}\n\nContext:\n{context}"

        messages = [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=user_content),
        ]

        try:
            response = await get_router().route(
                messages, max_tokens=settings.code.codegen_max_tokens,
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Code generation failed: {e}")

        code = _extract_code(response.content)

        execution = None
        if should_run:
            try:
                result = await run_code(
                    code, language, params.connection_state.connection_id,
                )
                execution = {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code,
                    "timed_out": result.timed_out,
                    "execution_time_ms": result.execution_time_ms,
                }
            except Exception as e:
                execution = {
                    "stdout": "",
                    "stderr": str(e),
                    "exit_code": -1,
                    "timed_out": False,
                    "execution_time_ms": 0,
                }

        return ToolResult(
            success=True,
            data={
                "code": code,
                "language": language,
                "execution": execution,
            },
        )
```

- [ ] **Step 4: Uncomment codegen import in tools/code/__init__.py**

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_code_codegen.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/tools/code/codegen.py backend/nobla/tools/code/__init__.py backend/tests/test_code_codegen.py
git commit -m "feat(tools): add CodeGenerationTool with LLM routing and optional execution"
```

---

## Task 5: DebugAssistantTool

**Files:**
- Create: `backend/nobla/tools/code/debug.py`
- Create: `backend/tests/test_code_debug.py`
- Modify: `backend/nobla/tools/code/__init__.py` (uncomment debug import)

### Step-by-step

- [ ] **Step 1: Write failing tests for DebugAssistantTool**

```python
# backend/tests/test_code_debug.py
"""Tests for DebugAssistantTool and _parse_error helper."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.tools.models import ToolCategory, ToolParams


class TestParseError:
    def test_python_traceback(self):
        from nobla.tools.code.debug import _parse_error
        error = 'File "main.py", line 42, in <module>\nValueError: invalid literal'
        result = _parse_error(error, "python")
        assert result["type"] == "ValueError"
        assert "invalid literal" in result["message"]
        assert result["file"] == "main.py"
        assert result["line"] == 42

    def test_javascript_error(self):
        from nobla.tools.code.debug import _parse_error
        error = "TypeError: Cannot read properties of undefined\n    at main.js:15"
        result = _parse_error(error, "javascript")
        assert result["type"] == "TypeError"
        assert "undefined" in result["message"]

    def test_bash_error(self):
        from nobla.tools.code.debug import _parse_error
        error = "script.sh: line 10: syntax error near unexpected token"
        result = _parse_error(error, "bash")
        assert result["line"] == 10

    def test_unknown_format_fallback(self):
        from nobla.tools.code.debug import _parse_error
        error = "something went wrong with no pattern"
        result = _parse_error(error, "python")
        assert result["type"] is None
        assert result["message"] is not None
        assert result["file"] is None
        assert result["line"] is None

    def test_never_raises(self):
        from nobla.tools.code.debug import _parse_error
        # Even garbage input should not raise
        result = _parse_error("", "unknown_lang")
        assert result is not None
        result = _parse_error(None, "python")  # type: ignore
        assert result is not None


class TestDebugAssistantTool:
    @pytest.fixture()
    def state(self):
        return ConnectionState(
            connection_id="conn123", user_id="u1", tier=Tier.STANDARD.value,
        )

    def test_tool_metadata(self):
        from nobla.tools.code.debug import DebugAssistantTool
        tool = DebugAssistantTool()
        assert tool.name == "code.debug"
        assert tool.category == ToolCategory.CODE
        assert tool.tier == Tier.STANDARD
        assert tool.requires_approval is False

    @pytest.mark.asyncio
    async def test_validate_rejects_empty_error(self, state):
        from nobla.tools.code.debug import DebugAssistantTool
        tool = DebugAssistantTool()
        with pytest.raises(ValueError, match="[Ee]rror.*required|empty"):
            await tool.validate(ToolParams(
                args={"error": ""}, connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_execute_returns_parsed_error_and_suggestion(self, state):
        from nobla.tools.code.debug import DebugAssistantTool
        tool = DebugAssistantTool()

        mock_response = MagicMock()
        mock_response.content = "The error is caused by X. Fix: change Y to Z."

        with patch("nobla.tools.code.debug.get_router") as mock_router:
            router = AsyncMock()
            router.route = AsyncMock(return_value=mock_response)
            mock_router.return_value = router

            params = ToolParams(
                args={
                    "error": 'File "app.py", line 10\nValueError: bad value',
                    "code": "x = int('abc')",
                    "language": "python",
                },
                connection_state=state,
            )
            result = await tool.execute(params)

            assert result.success is True
            assert result.data["parsed_error"]["type"] == "ValueError"
            assert result.data["suggestion"] is not None
            assert len(result.data["suggestion"]) > 0

    @pytest.mark.asyncio
    async def test_execute_truncates_long_error(self, state):
        from nobla.tools.code.debug import DebugAssistantTool
        tool = DebugAssistantTool()

        mock_response = MagicMock()
        mock_response.content = "Fix it."

        with patch("nobla.tools.code.debug.get_router") as mock_router:
            router = AsyncMock()
            router.route = AsyncMock(return_value=mock_response)
            mock_router.return_value = router

            long_error = "E" * 100000
            params = ToolParams(
                args={"error": long_error},
                connection_state=state,
            )
            result = await tool.execute(params)
            # Should not pass the full 100k to the LLM
            call_args = router.route.call_args[0][0]  # messages list
            user_msg = [m for m in call_args if m.role == "user"][0]
            assert len(user_msg.content) < 100000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_code_debug.py -v`
Expected: FAIL

- [ ] **Step 3: Create DebugAssistantTool**

```python
# backend/nobla/tools/code/debug.py
"""DebugAssistantTool — error parsing and LLM-powered fix suggestions."""
from __future__ import annotations

import re

from nobla.brain.base_provider import LLMMessage
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.code.codegen import get_router
from nobla.tools.code.runner import get_settings
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool

_ERROR_PATTERNS = {
    "python": re.compile(
        r'(?:File "(?P<file>.+?)", line (?P<line>\d+).*?\n)?'
        r"(?P<type>\w+Error): (?P<message>.+)",
        re.DOTALL,
    ),
    "javascript": re.compile(
        r"(?P<type>\w*Error): (?P<message>.+?)"
        r"(?:\n\s+at .+?[:\(](?P<file>.+?):(?P<line>\d+))?",
        re.DOTALL,
    ),
    "bash": re.compile(r".*line (?P<line>\d+): (?P<message>.+)"),
}

_DEBUG_SYSTEM_PROMPT = (
    "You are a debugging assistant. Analyze the error and suggest a fix. "
    "Be concise: state the cause in 1-2 sentences, then provide the corrected code. "
    "If the original code is provided, show the fix as a minimal diff."
)


def _parse_error(error: str, language: str) -> dict:
    """Best-effort error parsing. Never raises."""
    try:
        if not error:
            return {"type": None, "message": "", "file": None, "line": None}
        pattern = _ERROR_PATTERNS.get(language)
        if pattern:
            match = pattern.search(error)
            if match:
                groups = match.groupdict()
                line_val = groups.get("line")
                return {
                    "type": groups.get("type"),
                    "message": groups.get("message", error[:200]),
                    "file": groups.get("file"),
                    "line": int(line_val) if line_val else None,
                }
    except Exception:
        pass
    return {"type": None, "message": str(error)[:200], "file": None, "line": None}


@register_tool
class DebugAssistantTool(BaseTool):
    name = "code.debug"
    description = "Analyze error messages and suggest fixes"
    category = ToolCategory.CODE
    tier = Tier.STANDARD
    requires_approval = False

    async def validate(self, params: ToolParams) -> None:
        settings = get_settings()
        if not settings.code.enabled:
            raise ValueError("Code tools disabled in settings")
        error = params.args.get("error", "")
        if not error or not error.strip():
            raise ValueError("Error message is required and cannot be empty")

    def describe_action(self, params: ToolParams) -> str:
        error_preview = params.args.get("error", "")[:60]
        return f"Debug error: {error_preview!r}"

    async def execute(self, params: ToolParams) -> ToolResult:
        settings = get_settings()
        error = params.args["error"]
        code = params.args.get("code", "")
        language = params.args.get("language", settings.code.default_language)

        # Truncate in execute, not validate
        max_err = settings.code.debug_max_error_length
        error = error[:max_err]

        parsed = _parse_error(error, language)

        # Build LLM prompt with raw error (not parsed)
        user_parts = [f"## Error\n{error}"]
        if code:
            user_parts.append(f"## Code\n```{language}\n{code}\n```")
        user_parts.append(f"## Language\n{language}")
        user_content = "\n\n".join(user_parts)

        messages = [
            LLMMessage(role="system", content=_DEBUG_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_content),
        ]

        try:
            response = await get_router().route(messages)
        except Exception as e:
            return ToolResult(success=False, error=f"Debug analysis failed: {e}")

        return ToolResult(
            success=True,
            data={
                "parsed_error": parsed,
                "suggestion": response.content,
                "language": language,
            },
        )
```

- [ ] **Step 4: Uncomment debug import in tools/code/__init__.py**

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_code_debug.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/tools/code/debug.py backend/nobla/tools/code/__init__.py backend/tests/test_code_debug.py
git commit -m "feat(tools): add DebugAssistantTool with error parsing and LLM fix suggestions"
```

---

## Task 6: GitTool

**Files:**
- Create: `backend/nobla/tools/code/git.py`
- Create: `backend/tests/test_code_git.py`
- Modify: `backend/nobla/tools/code/__init__.py` (uncomment git import)

### Step-by-step

- [ ] **Step 1: Write failing tests for GitTool**

```python
# backend/tests/test_code_git.py
"""Tests for GitTool — subcommands, conditional approval, URL validation."""
from __future__ import annotations

import shlex
from unittest.mock import AsyncMock, patch

import pytest

from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.security.sandbox import SandboxResult
from nobla.tools.models import ToolCategory, ToolParams


class TestGitToolMetadata:
    def test_metadata(self):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        assert tool.name == "git.ops"
        assert tool.category == ToolCategory.GIT
        assert tool.tier == Tier.ELEVATED
        assert tool.requires_approval is False


class TestGitNeedsApproval:
    @pytest.fixture()
    def state(self):
        return ConnectionState(
            connection_id="conn123", user_id="u1", tier=Tier.ELEVATED.value,
        )

    def test_clone_no_approval(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        params = ToolParams(args={"operation": "clone"}, connection_state=state)
        assert tool.needs_approval(params) is False

    def test_status_no_approval(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        params = ToolParams(args={"operation": "status"}, connection_state=state)
        assert tool.needs_approval(params) is False

    def test_commit_no_approval(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        params = ToolParams(args={"operation": "commit"}, connection_state=state)
        assert tool.needs_approval(params) is False

    def test_push_requires_approval(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        params = ToolParams(args={"operation": "push"}, connection_state=state)
        assert tool.needs_approval(params) is True

    def test_create_pr_requires_approval(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        params = ToolParams(args={"operation": "create_pr"}, connection_state=state)
        assert tool.needs_approval(params) is True


class TestGitValidation:
    @pytest.fixture()
    def state(self):
        return ConnectionState(
            connection_id="conn123", user_id="u1", tier=Tier.ELEVATED.value,
        )

    @pytest.mark.asyncio
    async def test_rejects_invalid_operation(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with pytest.raises(ValueError, match="[Ii]nvalid|operation"):
            await tool.validate(ToolParams(
                args={"operation": "rebase"}, connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_clone_requires_repo_url(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with pytest.raises(ValueError, match="repo_url"):
            await tool.validate(ToolParams(
                args={"operation": "clone"}, connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_clone_rejects_local_path(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with pytest.raises(ValueError, match="[Ll]ocal"):
            await tool.validate(ToolParams(
                args={"operation": "clone", "repo_url": "/etc/passwd"},
                connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_clone_rejects_file_protocol(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with pytest.raises(ValueError, match="[Ll]ocal"):
            await tool.validate(ToolParams(
                args={"operation": "clone", "repo_url": "file:///etc/passwd"},
                connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_clone_rejects_non_whitelisted_host(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with pytest.raises(ValueError, match="[Aa]llowed|host"):
            await tool.validate(ToolParams(
                args={
                    "operation": "clone",
                    "repo_url": "https://evil.com/repo.git",
                },
                connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_clone_accepts_github(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        # Should not raise
        await tool.validate(ToolParams(
            args={
                "operation": "clone",
                "repo_url": "https://github.com/user/repo.git",
            },
            connection_state=state,
        ))

    @pytest.mark.asyncio
    async def test_commit_requires_message(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with pytest.raises(ValueError, match="message"):
            await tool.validate(ToolParams(
                args={"operation": "commit"}, connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_create_pr_requires_title(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with pytest.raises(ValueError, match="title"):
            await tool.validate(ToolParams(
                args={"operation": "create_pr"}, connection_state=state,
            ))


class TestGitCommandBuilding:
    @pytest.fixture()
    def state(self):
        return ConnectionState(
            connection_id="conn12345678", user_id="u1", tier=Tier.ELEVATED.value,
        )

    @pytest.mark.asyncio
    async def test_clone_uses_list_command(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with patch("nobla.tools.code.git.get_sandbox") as mock_gs:
            sandbox = AsyncMock()
            sandbox.execute_command = AsyncMock(return_value=SandboxResult(
                stdout="Cloning...", stderr="", exit_code=0,
                execution_time_ms=3000, timed_out=False,
            ))
            mock_gs.return_value = sandbox

            params = ToolParams(
                args={
                    "operation": "clone",
                    "repo_url": "https://github.com/user/repo.git",
                },
                connection_state=state,
            )
            result = await tool.execute(params)
            assert result.success is True

            cmd = sandbox.execute_command.call_args.kwargs.get("cmd")
            if cmd is None:
                cmd = sandbox.execute_command.call_args[0][0]
            assert isinstance(cmd, list)
            assert cmd[0] == "git"
            assert "clone" in cmd

    @pytest.mark.asyncio
    async def test_status_uses_list_command(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with patch("nobla.tools.code.git.get_sandbox") as mock_gs:
            sandbox = AsyncMock()
            sandbox.execute_command = AsyncMock(return_value=SandboxResult(
                stdout="On branch main", stderr="", exit_code=0,
                execution_time_ms=100, timed_out=False,
            ))
            mock_gs.return_value = sandbox

            params = ToolParams(
                args={"operation": "status"},
                connection_state=state,
            )
            result = await tool.execute(params)
            cmd = sandbox.execute_command.call_args.kwargs.get("cmd")
            if cmd is None:
                cmd = sandbox.execute_command.call_args[0][0]
            assert cmd[0] == "git"
            assert "-C" in cmd

    @pytest.mark.asyncio
    async def test_commit_uses_sh(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with patch("nobla.tools.code.git.get_sandbox") as mock_gs:
            sandbox = AsyncMock()
            sandbox.execute_command = AsyncMock(return_value=SandboxResult(
                stdout="[main abc1234] test commit", stderr="",
                exit_code=0, execution_time_ms=200, timed_out=False,
            ))
            mock_gs.return_value = sandbox

            params = ToolParams(
                args={"operation": "commit", "message": "test commit"},
                connection_state=state,
            )
            await tool.execute(params)
            cmd = sandbox.execute_command.call_args.kwargs.get("cmd")
            if cmd is None:
                cmd = sandbox.execute_command.call_args[0][0]
            assert cmd[0] == "sh"
            assert cmd[1] == "-c"


class TestGitDescribeAction:
    @pytest.fixture()
    def state(self):
        return ConnectionState(
            connection_id="conn123", user_id="u1", tier=Tier.ELEVATED.value,
        )

    def test_push_description(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        params = ToolParams(
            args={"operation": "push", "branch": "feature-x"},
            connection_state=state,
        )
        desc = tool.describe_action(params)
        assert "Push" in desc
        assert "feature-x" in desc

    def test_create_pr_description(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        params = ToolParams(
            args={"operation": "create_pr", "title": "Add feature"},
            connection_state=state,
        )
        desc = tool.describe_action(params)
        assert "PR" in desc
        assert "Add feature" in desc
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_code_git.py -v`
Expected: FAIL

- [ ] **Step 3: Create GitTool**

```python
# backend/nobla/tools/code/git.py
"""GitTool — single tool with subcommands for git operations."""
from __future__ import annotations

import re
import shlex
from urllib.parse import urlparse

from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.code.runner import get_sandbox, get_settings
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool

_VALID_OPERATIONS = {
    "clone", "status", "diff", "log", "commit", "push", "create_pr",
}

_APPROVAL_OPERATIONS = {"push", "create_pr"}

_NETWORK_OPERATIONS = {"clone", "push", "create_pr"}

_SSH_URL_RE = re.compile(r"^[\w.-]+@([\w.-]+):.*$")


def _extract_host(url: str) -> str | None:
    """Extract hostname from HTTPS or SSH git URL."""
    parsed = urlparse(url)
    if parsed.hostname:
        return parsed.hostname
    match = _SSH_URL_RE.match(url)
    if match:
        return match.group(1)
    return None


def _validate_repo_url(url: str, allowed_hosts: list[str]) -> None:
    """Validate a git clone URL for security."""
    if url.startswith("/") or url.startswith("file://"):
        raise ValueError("Local paths not allowed — use HTTPS or SSH URLs")
    host = _extract_host(url)
    if not host or host not in allowed_hosts:
        raise ValueError(
            f"Host '{host}' not in allowed hosts: {allowed_hosts}"
        )


@register_tool
class GitTool(BaseTool):
    name = "git.ops"
    description = "Git operations: clone, status, diff, log, commit, push, create PR"
    category = ToolCategory.GIT
    tier = Tier.ELEVATED
    requires_approval = False

    def needs_approval(self, params: ToolParams) -> bool:
        op = params.args.get("operation", "")
        return op in _APPROVAL_OPERATIONS

    async def validate(self, params: ToolParams) -> None:
        settings = get_settings()
        if not settings.code.enabled:
            raise ValueError("Code tools disabled in settings")
        op = params.args.get("operation", "")
        if op not in _VALID_OPERATIONS:
            raise ValueError(
                f"Invalid operation '{op}'. Valid: {sorted(_VALID_OPERATIONS)}"
            )
        if op == "clone":
            url = params.args.get("repo_url")
            if not url:
                raise ValueError("repo_url is required for clone")
            _validate_repo_url(url, settings.code.git_allowed_hosts)
        if op == "commit":
            if not params.args.get("message"):
                raise ValueError("message is required for commit")
        if op == "create_pr":
            if not params.args.get("title"):
                raise ValueError("title is required for create_pr")

    def describe_action(self, params: ToolParams) -> str:
        op = params.args.get("operation", "")
        if op == "push":
            branch = params.args.get("branch", "current branch")
            return f"Push to {branch}"
        if op == "create_pr":
            title = params.args.get("title", "untitled")
            return f"Create PR: {title}"
        return f"Git {op}"

    def _build_command(self, operation: str, args: dict) -> list[str]:
        path = args.get("path", "/workspace")

        if operation == "clone":
            cmd = ["git", "clone", "--depth", "1", args["repo_url"]]
            if path:
                cmd.append(path)
            return cmd

        if operation == "status":
            return ["git", "-C", path, "status"]

        if operation == "diff":
            return ["git", "-C", path, "diff"]

        if operation == "log":
            return ["git", "-C", path, "log", "--oneline", "-20"]

        if operation == "commit":
            msg = shlex.quote(args["message"])
            return [
                "sh", "-c",
                f"cd {shlex.quote(path)} && git add -A && git commit -m {msg}",
            ]

        if operation == "push":
            branch = args.get("branch", "HEAD")
            return ["git", "-C", path, "push", "origin", branch]

        if operation == "create_pr":
            title = shlex.quote(args["title"])
            body = shlex.quote(args.get("body", ""))
            base = shlex.quote(args.get("base_branch", "main"))
            return [
                "sh", "-c",
                f"cd {shlex.quote(path)} && "
                f"gh pr create --title {title} --body {body} --base {base}",
            ]

        return ["echo", f"Unknown operation: {operation}"]

    async def execute(self, params: ToolParams) -> ToolResult:
        settings = get_settings()
        operation = params.args["operation"]
        connection_id = params.connection_state.connection_id

        cmd = self._build_command(operation, params.args)
        image = settings.code.git_image
        needs_net = operation in _NETWORK_OPERATIONS

        # Git volume name: {prefix}-{conn_id[:8]} — no language segment
        vol_name = f"{settings.code.git_workspace_volume_prefix}-{connection_id[:8]}"
        volumes = {vol_name: "/workspace"}

        timeout = settings.code.git_timeout

        try:
            result = await get_sandbox().execute_command(
                cmd=cmd, image=image, timeout=timeout,
                network=needs_net, volumes=volumes,
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

        # Handle create_pr gh CLI fallback
        if operation == "create_pr" and result.exit_code != 0:
            if "gh" in result.stderr.lower() or "not found" in result.stderr.lower():
                return ToolResult(
                    success=False,
                    data={
                        "operation": operation,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "exit_code": result.exit_code,
                        "success": False,
                    },
                    error=(
                        "GitHub CLI (gh) not available — "
                        "use the fallback URL to create the PR manually"
                    ),
                )

        return ToolResult(
            success=result.exit_code == 0,
            data={
                "operation": operation,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "success": result.exit_code == 0,
            },
        )
```

- [ ] **Step 4: Uncomment git import in tools/code/__init__.py**

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_code_git.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/tools/code/git.py backend/nobla/tools/code/__init__.py backend/tests/test_code_git.py
git commit -m "feat(tools): add GitTool with subcommands and conditional approval"
```

---

## Task 7: Auto-Discovery Wiring & Integration Tests

**Files:**
- Modify: `backend/nobla/tools/__init__.py`
- Modify: `backend/nobla/tools/code/__init__.py` (ensure all imports uncommented)
- Create: `backend/tests/integration/test_code_flow.py`

### Step-by-step

- [ ] **Step 1: Wire auto-discovery in tools/__init__.py**

In `backend/nobla/tools/__init__.py`, add the code import:

```python
"""Nobla tool platform — registry, executor, and auto-discovered tools."""
from nobla.tools.registry import ToolRegistry

from nobla.tools import vision  # noqa: F401 — triggers @register_tool
from nobla.tools import code    # noqa: F401 — triggers @register_tool

tool_registry = ToolRegistry()

__all__ = ["tool_registry"]
```

- [ ] **Step 2: Ensure all imports in tools/code/__init__.py are uncommented**

Verify `backend/nobla/tools/code/__init__.py` imports all 5 modules:

```python
from nobla.tools.code import runner    # noqa: E402, F401
from nobla.tools.code import packages  # noqa: E402, F401
from nobla.tools.code import codegen   # noqa: E402, F401
from nobla.tools.code import debug     # noqa: E402, F401
from nobla.tools.code import git       # noqa: E402, F401
```

- [ ] **Step 3: Write integration tests**

```python
# backend/tests/integration/test_code_flow.py
"""Integration tests for Phase 4C code execution tools."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import PermissionChecker, Tier
from nobla.security.sandbox import SandboxResult
from nobla.tools.approval import ApprovalManager
from nobla.tools.executor import ToolExecutor
from nobla.tools.models import ApprovalStatus, ToolParams
from nobla.tools.registry import ToolRegistry, _TOOL_REGISTRY


@pytest.fixture(autouse=True)
def clean_registry():
    """Reset registry between tests to avoid cross-contamination."""
    _TOOL_REGISTRY.clear()
    yield
    _TOOL_REGISTRY.clear()


@pytest.fixture()
def executor():
    # Force re-import to register tools
    import importlib
    import nobla.tools.code.runner
    import nobla.tools.code.packages
    import nobla.tools.code.git
    importlib.reload(nobla.tools.code.runner)
    importlib.reload(nobla.tools.code.packages)
    importlib.reload(nobla.tools.code.git)

    registry = ToolRegistry()
    checker = PermissionChecker()
    audit = AsyncMock()
    approvals = ApprovalManager()
    return ToolExecutor(registry, checker, audit, approvals)


@pytest.fixture()
def standard_state():
    return ConnectionState(
        connection_id="conn12345678", user_id="u1", tier=Tier.STANDARD.value,
    )


@pytest.fixture()
def elevated_state():
    return ConnectionState(
        connection_id="conn12345678", user_id="u1", tier=Tier.ELEVATED.value,
    )


class TestCodeToolRegistration:
    def test_all_code_tools_registered(self):
        import importlib
        import nobla.tools.code.runner
        import nobla.tools.code.packages
        import nobla.tools.code.codegen
        import nobla.tools.code.debug
        import nobla.tools.code.git
        importlib.reload(nobla.tools.code.runner)
        importlib.reload(nobla.tools.code.packages)
        importlib.reload(nobla.tools.code.codegen)
        importlib.reload(nobla.tools.code.debug)
        importlib.reload(nobla.tools.code.git)

        registry = ToolRegistry()
        assert registry.get("code.run") is not None
        assert registry.get("code.install_package") is not None
        assert registry.get("code.generate") is not None
        assert registry.get("code.debug") is not None
        assert registry.get("git.ops") is not None


class TestPermissionEnforcement:
    @pytest.mark.asyncio
    async def test_standard_can_run_code(self, executor, standard_state):
        with patch("nobla.tools.code.runner.get_sandbox") as mock:
            sandbox = AsyncMock()
            sandbox.execute = AsyncMock(return_value=SandboxResult(
                stdout="ok", stderr="", exit_code=0,
                execution_time_ms=50, timed_out=False,
            ))
            mock.return_value = sandbox

            params = ToolParams(
                args={"code": "print('hi')", "language": "python"},
                connection_state=standard_state,
            )
            result = await executor.execute("code.run", params)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_standard_cannot_install_packages(self, executor, standard_state):
        params = ToolParams(
            args={"packages": ["numpy"]},
            connection_state=standard_state,
        )
        result = await executor.execute("code.install_package", params)
        assert result.success is False
        assert "permission" in result.error.lower() or "insufficient" in result.error.lower()

    @pytest.mark.asyncio
    async def test_standard_cannot_use_git(self, executor, standard_state):
        params = ToolParams(
            args={"operation": "status"},
            connection_state=standard_state,
        )
        result = await executor.execute("git.ops", params)
        assert result.success is False


class TestGitApprovalFlow:
    @pytest.mark.asyncio
    async def test_git_push_triggers_approval(self, executor, elevated_state):
        params = ToolParams(
            args={"operation": "push"},
            connection_state=elevated_state,
        )
        # Push needs approval, no one resolves it -> times out
        tool = _TOOL_REGISTRY.get("git.ops")
        if tool:
            tool.approval_timeout = 1
        result = await executor.execute("git.ops", params)
        assert result.success is False
        assert result.approval_was_required is True

    @pytest.mark.asyncio
    async def test_git_status_no_approval(self, executor, elevated_state):
        with patch("nobla.tools.code.git.get_sandbox") as mock:
            sandbox = AsyncMock()
            sandbox.execute_command = AsyncMock(return_value=SandboxResult(
                stdout="On branch main", stderr="", exit_code=0,
                execution_time_ms=50, timed_out=False,
            ))
            mock.return_value = sandbox

            params = ToolParams(
                args={"operation": "status"},
                connection_state=elevated_state,
            )
            result = await executor.execute("git.ops", params)
            assert result.success is True
            assert result.approval_was_required is False
```

- [ ] **Step 3b: Add integration tests for code.generate and code.debug**

Add to `backend/tests/integration/test_code_flow.py`:

```python
class TestCodeGenerateIntegration:
    @pytest.mark.asyncio
    async def test_generate_and_run(self, elevated_state):
        """Integration: code.generate with run=True through executor."""
        import importlib
        import nobla.tools.code.codegen
        importlib.reload(nobla.tools.code.codegen)

        # Wire up the router for codegen/debug
        from nobla.tools.code.codegen import set_router
        mock_router = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "print('hello')"
        mock_router.route = AsyncMock(return_value=mock_response)
        set_router(mock_router)

        registry = ToolRegistry()
        checker = PermissionChecker()
        audit = AsyncMock()
        approvals = ApprovalManager()
        executor = ToolExecutor(registry, checker, audit, approvals)

        with patch("nobla.tools.code.runner.get_sandbox") as mock_gs:
            sandbox = AsyncMock()
            sandbox.execute = AsyncMock(return_value=SandboxResult(
                stdout="hello\n", stderr="", exit_code=0,
                execution_time_ms=80, timed_out=False,
            ))
            mock_gs.return_value = sandbox

            params = ToolParams(
                args={
                    "description": "print hello",
                    "language": "python",
                    "run": True,
                },
                connection_state=elevated_state,
            )
            result = await executor.execute("code.generate", params)
            assert result.success is True
            assert result.data["code"] == "print('hello')"
            assert result.data["execution"] is not None
            assert result.data["execution"]["stdout"] == "hello\n"


class TestCodeDebugIntegration:
    @pytest.mark.asyncio
    async def test_debug_through_executor(self, elevated_state):
        """Integration: code.debug returns parsed error + suggestion."""
        import importlib
        import nobla.tools.code.debug
        importlib.reload(nobla.tools.code.debug)

        from nobla.tools.code.codegen import set_router
        mock_router = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "Change int('abc') to int('123')."
        mock_router.route = AsyncMock(return_value=mock_response)
        set_router(mock_router)

        registry = ToolRegistry()
        checker = PermissionChecker()
        audit = AsyncMock()
        approvals = ApprovalManager()
        executor = ToolExecutor(registry, checker, audit, approvals)

        params = ToolParams(
            args={
                "error": 'File "app.py", line 5\nValueError: invalid literal',
                "code": "x = int('abc')",
                "language": "python",
            },
            connection_state=elevated_state,
        )
        result = await executor.execute("code.debug", params)
        assert result.success is True
        assert result.data["parsed_error"]["type"] == "ValueError"
        assert len(result.data["suggestion"]) > 0
```

- [ ] **Step 4: Run all tests**

Run: `cd backend && python -m pytest tests/test_code_settings.py tests/test_code_runner.py tests/test_code_packages.py tests/test_code_codegen.py tests/test_code_debug.py tests/test_code_git.py tests/integration/test_code_flow.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite for regressions**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: ALL PASS (no regressions in existing tests)

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/tools/__init__.py backend/nobla/tools/code/__init__.py backend/tests/integration/test_code_flow.py
git commit -m "feat(tools): wire Phase 4C auto-discovery and add integration tests"
```

---

## Task Summary

| Task | Component | New Lines | Tests |
|------|-----------|-----------|-------|
| 0 | Settings + platform changes | ~25 | ~100 |
| 1 | SandboxManager extensions | ~100 | ~40 |
| 2 | Shared helpers + CodeRunnerTool | ~140 | ~120 |
| 3 | PackageInstallTool | ~100 | ~100 |
| 4 | CodeGenerationTool | ~130 | ~100 |
| 5 | DebugAssistantTool | ~120 | ~80 |
| 6 | GitTool | ~150 | ~150 |
| 7 | Auto-discovery + integration | ~10 | ~80 |
| **Total** | | **~775** | **~770** |

All files stay well under the 750-line limit. Total: ~775 lines of implementation code across 8 files + ~770 lines of tests across 8 test files.

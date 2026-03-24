"""CodeRunnerTool — execute code in sandboxed Docker containers."""
from __future__ import annotations

from nobla.config.settings import Settings
from nobla.security.permissions import Tier
from nobla.security.sandbox import SandboxManager, SandboxResult
from nobla.tools.base import BaseTool
from nobla.tools.code import PACKAGE_ENV, PACKAGE_MOUNT, PACKAGEABLE_LANGUAGES, get_volume_name
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool

# --- Lazy singletons --------------------------------------------------------

_settings: Settings | None = None
_sandbox: SandboxManager | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def get_sandbox() -> SandboxManager:
    global _sandbox
    if _sandbox is None:
        _sandbox = SandboxManager(get_settings().sandbox)
    return _sandbox


# --- Shared free function ----------------------------------------------------


async def run_code(
    code: str,
    language: str,
    connection_id: str,
) -> SandboxResult:
    """Run code in a sandbox, mounting a package volume for packageable languages.

    Shared by CodeRunnerTool and CodeGenerationTool (when run=True).
    """
    settings = get_settings()
    sandbox = get_sandbox()

    volumes: dict[str, str] | None = None
    environment: dict[str, str] | None = None

    if language in PACKAGEABLE_LANGUAGES:
        vol_name = get_volume_name(
            settings.code.package_volume_prefix, language, connection_id,
        )
        mount_path = f"{PACKAGE_MOUNT}/{language}"
        volumes = {vol_name: mount_path}
        environment = PACKAGE_ENV.get(language)

    return await sandbox.execute(
        code=code,
        language=language,
        volumes=volumes,
        environment=environment,
    )


# --- CodeRunnerTool ----------------------------------------------------------


@register_tool
class CodeRunnerTool(BaseTool):
    name = "code.run"
    description = "Execute code in a sandboxed Docker container"
    category = ToolCategory.CODE
    tier = Tier.STANDARD
    requires_approval = False

    async def validate(self, params: ToolParams) -> None:
        settings = get_settings()
        code = params.args.get("code", "")
        if not code or not code.strip():
            raise ValueError("Code is required and cannot be empty")

        language = params.args.get("language", settings.code.default_language)
        if language not in settings.code.supported_languages:
            raise ValueError(
                f"Unsupported language '{language}'. "
                f"Supported: {settings.code.supported_languages}"
            )

    async def execute(self, params: ToolParams) -> ToolResult:
        settings = get_settings()
        code = params.args["code"]
        language = params.args.get("language", settings.code.default_language)
        max_len = settings.code.max_output_length

        result = await run_code(code, language, params.connection_state.connection_id)

        stdout = result.stdout
        truncated = False
        if len(stdout) > max_len:
            stdout = stdout[:max_len]
            truncated = True

        return ToolResult(
            success=result.exit_code == 0,
            data={
                "stdout": stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "language": language,
                "execution_time_ms": result.execution_time_ms,
                "timed_out": result.timed_out,
                "truncated": truncated,
            },
            error=result.stderr if result.exit_code != 0 else None,
        )

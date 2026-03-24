"""PackageInstallTool — install pip/npm packages into shared Docker volume."""
from __future__ import annotations

import re

from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.code import PACKAGEABLE_LANGUAGES, get_volume_name
from nobla.tools.code.runner import get_sandbox, get_settings
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool

PACKAGE_NAME_RE = re.compile(
    r"^(@[a-zA-Z0-9\-_]+/)?"          # optional npm scope
    r"[a-zA-Z0-9][a-zA-Z0-9\-_.]*"    # package name (no leading dot/dash)
    r"([><=!~]{1,2}[a-zA-Z0-9.*]+)?"  # optional version specifier
    r"(,[><=!~]{1,2}[a-zA-Z0-9.*]+)*" # optional additional constraints
    r"$"
)

_INSTALL_CMD = {
    "python": lambda pkgs: [
        "pip", "install", "--no-cache-dir", "--target", "/packages/python", *pkgs,
    ],
    "javascript": lambda pkgs: [
        "npm", "install", "--prefix", "/packages/node", *pkgs,
    ],
}

_INSTALL_MOUNT = {
    "python": "/packages/python",
    "javascript": "/packages/node",
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
            raise ValueError("Code execution is disabled")

        packages = params.args.get("packages", [])
        if not packages:
            raise ValueError("Package list is empty — provide at least one package")

        language = params.args.get("language", settings.code.default_language)
        if language not in PACKAGEABLE_LANGUAGES:
            raise ValueError(
                f"Language '{language}' does not support package installation. "
                f"Packageable: {sorted(PACKAGEABLE_LANGUAGES)}"
            )

        for pkg in packages:
            if not PACKAGE_NAME_RE.match(pkg):
                raise ValueError(f"Invalid package name: '{pkg}'")

    async def execute(self, params: ToolParams) -> ToolResult:
        settings = get_settings()
        packages = params.args["packages"]
        language = params.args.get("language", settings.code.default_language)
        connection_id = params.connection_state.connection_id

        if language not in _INSTALL_CMD:
            return ToolResult(success=False, data={}, error=f"Unsupported language: {language}")

        cmd = _INSTALL_CMD[language](packages)
        image = _INSTALL_IMAGE[language]
        vol_name = get_volume_name(
            settings.code.package_volume_prefix, language, connection_id,
        )
        volumes = {vol_name: _INSTALL_MOUNT[language]}

        try:
            result = await get_sandbox().execute_command(
                cmd=cmd, image=image, network=True,
                volumes=volumes,
            )
        except Exception as e:
            return ToolResult(success=False, data={}, error=str(e))

        return ToolResult(
            success=result.exit_code == 0,
            data={
                "packages": packages,
                "language": language,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
            },
            error=result.stderr if result.exit_code != 0 else None,
        )

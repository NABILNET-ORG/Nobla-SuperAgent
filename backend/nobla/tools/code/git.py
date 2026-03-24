"""GitTool — single tool with 7 subcommands and conditional approval."""
from __future__ import annotations

import shlex
from urllib.parse import urlparse

from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.code.runner import get_sandbox, get_settings
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool

_VALID_OPERATIONS = {"clone", "status", "diff", "log", "commit", "push", "create_pr"}
_NETWORK_OPERATIONS = {"clone", "push", "create_pr"}
_APPROVAL_OPERATIONS = {"push", "create_pr"}


def _validate_repo_url(url: str, allowed_hosts: list[str]) -> None:
    """Validate that repo URL uses an allowed host."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError(f"Invalid repo URL: {url!r} — must be https://host/repo")
    if parsed.hostname not in allowed_hosts:
        raise ValueError(
            f"Host '{parsed.hostname}' not in allowed hosts: {allowed_hosts}"
        )


@register_tool
class GitTool(BaseTool):
    name = "git.ops"
    description = "Git operations: clone, status, diff, log, commit, push, create PR"
    category = ToolCategory.GIT
    tier = Tier.ELEVATED
    requires_approval = False  # Conditional — overridden by needs_approval()

    def needs_approval(self, params: ToolParams) -> bool:
        return params.args.get("operation") in _APPROVAL_OPERATIONS

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
            n = str(args.get("count", 10))
            return ["git", "-C", path, "log", "--oneline", f"-{n}"]

        if operation == "commit":
            msg = shlex.quote(args["message"])
            return [
                "sh", "-c",
                f"cd {shlex.quote(path)} && git add -A && git commit -m {msg}",
            ]

        if operation == "push":
            branch = args.get("branch", "")
            push_cmd = "git push"
            if branch:
                push_cmd = f"git push origin {shlex.quote(branch)}"
            return [
                "sh", "-c",
                f"cd {shlex.quote(path)} && {push_cmd}",
            ]

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

        vol_name = (
            f"{settings.code.git_workspace_volume_prefix}-{connection_id[:8]}"
        )
        volumes = {vol_name: "/workspace"}

        timeout = settings.code.git_timeout

        try:
            result = await get_sandbox().execute_command(
                cmd=cmd, image=image, timeout=timeout,
                network=needs_net, volumes=volumes,
            )
        except Exception as e:
            return ToolResult(success=False, data={}, error=str(e))

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

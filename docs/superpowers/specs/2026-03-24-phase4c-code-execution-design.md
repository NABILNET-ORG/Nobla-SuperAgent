# Phase 4C Design Spec: Code Execution Tools

**Date:** 2026-03-24
**Author:** NABILNET.AI
**Status:** Approved
**Scope:** 5 code execution tools + platform changes (BaseTool, ToolExecutor, SandboxManager, Settings)
**Depends on:** Phase 4-Pre (tool platform), Phase 1B (SandboxManager, permissions), Phase 2A (LLM router)
**Parent spec:** `docs/superpowers/specs/2026-03-23-phase4-computer-control-vision-design.md` (Section 6.3)

---

## 1. Overview

Phase 4C adds code execution tools to the Nobla tool platform. Five tools wrap existing infrastructure (SandboxManager, LLMRouter) to provide sandboxed code running, package management, code generation, error debugging, and git operations — all with tier-gated permissions, audit logging, and the tool platform's execution pipeline.

### Goals

- Sandboxed code execution with package persistence via Docker volumes
- LLM-powered code generation with optional immediate execution
- Error analysis and fix suggestions via LLM
- Git operations with conditional approval for externally-visible actions
- All tools follow Phase 4A patterns (lazy settings, asyncio.to_thread, @register_tool)

### Non-Goals

- Replacing SandboxManager — tools wrap it, sandbox stays in `security/sandbox.py`
- Full GitHub/GitLab API integration — `gh` CLI with fallback URL for Phase 4C
- Language auto-detection — language is required (default Python)
- Persistent containers — Docker volumes for state, ephemeral containers for execution
- Project scaffolding — deferred to Phase 6 (BACKLOG-SCAFFOLD)

---

## 2. Architecture

### 2.1 File Layout

**New files:**
```
backend/nobla/tools/code/
├── __init__.py       # Auto-discovery imports + shared helpers
├── runner.py         # CodeRunnerTool + run_code() free function (~110 lines)
├── packages.py       # PackageInstallTool (~100 lines)
├── codegen.py        # CodeGenerationTool (~130 lines)
├── debug.py          # DebugAssistantTool (~120 lines)
└── git.py            # GitTool — single tool, 7 subcommands (~150 lines)
```

**Modified files:**
```
backend/nobla/config/settings.py       # +CodeExecutionSettings (~15 lines)
backend/nobla/tools/base.py            # +needs_approval() method (~3 lines)
backend/nobla/tools/executor.py        # Change approval check (~1 line)
backend/nobla/security/sandbox.py      # +execute_command(), +cleanup_volumes(),
                                       #  extend execute() and kill_all()
backend/nobla/tools/__init__.py        # +code import for auto-discovery
```

### 2.2 Data Flow

```
User/LLM Orchestrator
    │
    ├─ code.run ──────► run_code() ──► SandboxManager.execute() + package volume
    │
    ├─ code.install ──► SandboxManager.execute_command() + package volume + network
    │
    ├─ code.generate ─► get_router().route() ─► _extract_code() ─► run_code() [if run=True]
    │
    ├─ code.debug ────► _parse_error() ─► get_router().route() ─► suggestion
    │
    └─ git.ops ───────► _build_command() ─► SandboxManager.execute_command() + workspace volume
                         └─ push/PR: needs_approval() → approval dialog first
```

### 2.3 Volume Strategy

Docker volumes persist state across ephemeral container runs.

| Volume Pattern | Purpose | Mounted At | Cleanup |
|----------------|---------|------------|---------|
| `nobla-pkg-{lang}-{conn_id[:8]}` | Installed packages (pip/npm) | `/packages/{language}` | Session end / kill switch |
| `nobla-git-{conn_id[:8]}` | Git workspace (cloned repos) | `/workspace` | Session end / kill switch |

**Persistence modes:**
- `persist_packages = False` (default): Volume name includes `connection_id[:8]`, cleaned on session end. Privacy-first — no leftover state.
- `persist_packages = True`: Volume name includes `user_id`, survives across sessions.

**Environment variables** for package discovery:
```python
PACKAGE_ENV = {
    "python": {"PYTHONPATH": "/packages/python"},
    "javascript": {"NODE_PATH": "/packages/node/node_modules"},
}
```

---

## 3. Platform Changes

### 3.1 CodeExecutionSettings

Added to `config/settings.py`, wired as `Settings.code`:

```python
class CodeExecutionSettings(BaseModel):
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

**Wired into `Settings` class:**

```python
class Settings(BaseSettings):
    # ...existing fields...
    code: CodeExecutionSettings = Field(default_factory=CodeExecutionSettings)
```

**`SandboxSettings.allowed_images` update:** Add `node:20-slim` and `alpine/git:latest` to the default allowed images list:

```python
class SandboxSettings(BaseModel):
    # ...existing fields...
    allowed_images: list[str] = ["python:3.12-slim", "node:20-slim", "bash:5", "alpine/git:latest"]
```

`execute_command()` must perform the same image allowlist check as `get_image()` — reject any image not in `allowed_images`.

### 3.2 BaseTool + ToolExecutor: Conditional Approval

**These two changes are atomic — both must be applied together.** Applying the executor change without the BaseTool method causes `AttributeError` on every tool invocation.

Add `needs_approval()` method to `tools/base.py`:

```python
def needs_approval(self, params: ToolParams) -> bool:
    """Override for conditional approval (e.g. GitTool: push yes, clone no)."""
    return self.requires_approval
```

Default returns the static class variable — fully backward-compatible. Tools override for per-operation logic.

Change one line in `tools/executor.py`:

```python
# Before:
if tool.requires_approval:
# After:
if tool.needs_approval(params):
```

### 3.4 SandboxManager Changes

**Extended `execute()` signature:**

```python
async def execute(
    self, code: str, language: str = "python", timeout: int | None = None,
    network: bool | None = None, volumes: dict[str, str] | None = None,
    environment: dict[str, str] | None = None,
) -> SandboxResult:
```

- `network: bool | None` — overrides `self.config.network_enabled` when set
- `volumes: dict[str, str] | None` — `{volume_name: container_path}`, converted to Docker SDK format internally: `{name: {"bind": path, "mode": "rw"}}`
- `environment: dict[str, str] | None` — passed to Docker `container.run(environment=...)`

All three default to `None` (existing behavior unchanged).

**`read_only` handling with volumes:** The current `execute()` passes `read_only=True` to Docker. This blocks pip/npm from writing temp files and metadata outside the volume mount. When `volumes` is non-None, the container must also mount additional `tmpfs` entries for temp/cache directories:

```python
tmpfs_mounts = {"/tmp": "size=64m"}  # existing
if volumes:
    tmpfs_mounts.update({
        "/root": "size=32m",       # npm cache, pip config
        "/home": "size=32m",       # fallback home dir
    })
```

This preserves `read_only=True` on the root filesystem (security) while allowing pip/npm to function via tmpfs for ephemeral writes and volumes for persistent packages.

**New `execute_command()` method:**

```python
async def execute_command(
    self, cmd: list[str], image: str, timeout: int | None = None,
    network: bool | None = None, volumes: dict[str, str] | None = None,
    environment: dict[str, str] | None = None,
) -> SandboxResult:
    """Execute a pre-built command list in a container.

    Used by PackageInstallTool and GitTool where the command is built
    as a safe list rather than code + language.
    """
```

Reuses the same Docker logic as `execute()` but accepts `cmd` directly and `image` explicitly (git uses `alpine/git`, packages use the language image).

**New `cleanup_volumes()` method:**

```python
async def cleanup_volumes(self, prefix: str) -> None:
    """Remove all Docker volumes matching the prefix.

    Called on session disconnect and kill switch activation.
    """
```

**Extended `kill_all()`:**

```python
async def kill_all(self) -> None:
    # ...existing container kill logic...
    # NEW: also clean up volumes using configured prefixes (not hardcoded)
    settings = get_settings()
    await self.cleanup_volumes(settings.code.package_volume_prefix)
    await self.cleanup_volumes(settings.code.git_workspace_volume_prefix)
```

Volume prefixes are read from `CodeExecutionSettings` at call time, not hardcoded. If an operator changes the prefix, `kill_all()` still cleans the correct volumes.

### 3.5 Auto-Discovery Wiring

`tools/__init__.py`:

```python
from nobla.tools import vision  # noqa: F401
from nobla.tools import code    # noqa: F401  — NEW
```

`tools/code/__init__.py`:

```python
from nobla.tools.code import runner, packages, codegen, debug, git  # noqa: F401
```

---

## 4. Shared Helpers

Defined in `tools/code/__init__.py`:

### 4.1 Volume Naming

```python
PACKAGEABLE_LANGUAGES = {"python", "javascript"}

PACKAGE_MOUNT = "/packages"

PACKAGE_ENV = {
    "python": {"PYTHONPATH": "/packages/python"},
    "javascript": {"NODE_PATH": "/packages/node/node_modules"},
}

def get_volume_name(prefix: str, language: str, connection_id: str) -> str:
    """Consistent volume naming shared by runner and packages tools."""
    return f"{prefix}-{language}-{connection_id[:8]}"
```

### 4.2 Code Extraction

Defined in `codegen.py`:

```python
def _extract_code(response: str) -> str:
    """Strip markdown code fences from LLM response."""
    match = re.search(r"```(?:\w*)\n(.*?)```", response, re.DOTALL)
    return match.group(1).strip() if match else response.strip()
```

---

## 5. Tool Specifications

### 5.1 CodeRunnerTool (`runner.py`)

**Registration:** `name = "code.run"`, `category = ToolCategory.CODE`, `tier = Tier.STANDARD`, `requires_approval = False`

**Purpose:** Thin wrapper around `SandboxManager.execute()`. Adds package volume mounting, output truncation, and structured results.

**Params:**
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `code` | str | Yes | — | Code to execute |
| `language` | str | No | `settings.code.default_language` | `"python"`, `"javascript"`, or `"bash"` |
| `timeout` | int | No | sandbox default | Override execution timeout (seconds) |

**Validation:**
- `code_settings.enabled` must be `True`
- `language` must be in `supported_languages`
- `code` must be non-empty

**Execution:**
1. Build volume mount (if language is in `PACKAGEABLE_LANGUAGES`)
2. Call `SandboxManager.execute()` with volume + environment
3. Truncate stdout/stderr to `max_output_length`
4. Return structured `ToolResult`

**Result data:**
```python
{
    "stdout": str,
    "stderr": str,
    "exit_code": int,
    "language": str,
    "timed_out": bool,
    "truncated": bool,
    "execution_time_ms": int,
}
```

**Shared free function:** `run_code(code, language, connection_id) -> SandboxResult`

The core execution logic lives in a module-level free function, not the `execute()` method. This allows `CodeGenerationTool` to call it directly without going through the tool platform (avoids double audit). `CodeRunnerTool.execute()` calls `run_code()` then wraps + truncates into `ToolResult`.

### 5.2 PackageInstallTool (`packages.py`)

**Registration:** `name = "code.install_package"`, `category = ToolCategory.CODE`, `tier = Tier.ELEVATED`, `requires_approval = False`

**Purpose:** Installs pip/npm packages into a Docker volume shared with `code.run`.

**Params:**
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `packages` | list[str] | Yes | — | Package names with optional version specifiers |
| `language` | str | No | `settings.code.default_language` | `"python"` or `"javascript"` (not `"bash"`) |

**Validation:**
- `code_settings.enabled` must be `True`
- `language` must be in `PACKAGEABLE_LANGUAGES` (not bash)
- `packages` must be non-empty
- Each package name must match safety regex: `^[@a-zA-Z0-9][a-zA-Z0-9_\-\.]*(/[a-zA-Z0-9][a-zA-Z0-9_\-\.]*)?([>=<!][^\s,]+)?(,[^\s,]+)*$` — allows npm scoped packages (`@scope/name`) and version specifiers, but blocks path traversal (`../`, `./`, leading dots/slashes)

**Execution:**
1. Build install command as a **list** (not string interpolation):
   - Python: `["pip", "install", "--no-cache-dir", "--target", "/packages/python", *packages]`
   - JavaScript: `["npm", "install", "--prefix", "/packages/node", *packages]`
2. Call `SandboxManager.execute_command()` with same volume as `code.run` + `network=True`
3. Return overall success based on exit code

**Result data:**
```python
{
    "success": bool,
    "packages": list[str],
    "output": str,
    "language": str,
}
```

**Security:**
- ELEVATED tier gates network access
- Package name regex prevents command injection
- Commands built as lists, never string-interpolated
- Network enabled only for this specific tool execution

### 5.3 CodeGenerationTool (`codegen.py`)

**Registration:** `name = "code.generate"`, `category = ToolCategory.CODE`, `tier = Tier.STANDARD`, `requires_approval = False`

**Purpose:** Routes a natural language description through LLMRouter with a code-generation system prompt. Optionally executes the generated code via `run_code()`.

**Params:**
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `description` | str | Yes | — | What the code should do |
| `language` | str | No | `settings.code.default_language` | Target language |
| `run` | bool | No | `False` | Execute the generated code after generation |
| `context` | str | No | — | Additional context (existing code, constraints) |

**Validation:**
- `code_settings.enabled` must be `True`
- `description` must be non-empty
- `language` must be in `supported_languages`

**Execution:**
1. Build messages:
   - System prompt: `"You are a code generator. Output ONLY executable {language} code. No explanations, no markdown fences, no comments unless critical. The code must be self-contained and runnable."`
   - User message: description + optional context
2. Call `get_router().route(messages, max_tokens=settings.code.codegen_max_tokens)` — router naturally classifies as HARD due to code-related keywords
3. Extract code from response via `_extract_code()` (strips markdown fences if present)
4. If `run=True`: call `run_code(code, language, params.connection_state.connection_id)` directly (raw `SandboxResult`, no double audit). The `connection_id` is threaded from the tool's `ToolParams` to build the correct package volume name.
5. Return combined result

**Result data:**
```python
{
    "code": str,
    "language": str,
    "execution": {              # Only present when run=True
        "stdout": str,
        "stderr": str,
        "exit_code": int,
        "timed_out": bool,
        "execution_time_ms": int,
    } | None,
}
```

**Dependencies:**
- `LLMRouter` — accessed via lazy `get_router()` singleton (same pattern as `get_settings()`)
- `run_code()` — imported from `runner.py`

### 5.4 DebugAssistantTool (`debug.py`)

**Registration:** `name = "code.debug"`, `category = ToolCategory.CODE`, `tier = Tier.STANDARD`, `requires_approval = False`

**Purpose:** Parses error messages, sends structured context to LLM for fix suggestions. Read-only analysis — no code execution.

**Params:**
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `error` | str | Yes | — | Error message or traceback |
| `code` | str | No | — | The code that produced the error |
| `language` | str | No | `settings.code.default_language` | Helps error parsing |

**Validation:**
- `code_settings.enabled` must be `True`
- `error` must be non-empty

**Execution:**
1. Truncate error to `debug_max_error_length` (preprocessing, not validation)
2. Parse error via `_parse_error()` — best-effort regex, never fails:
   - Python: extracts `type`, `message`, `file`, `line` from tracebacks
   - JavaScript: extracts from Node.js error format
   - Bash: extracts line number and message
   - Fallback: `{"type": None, "message": error[:200], "file": None, "line": None}`
3. Build LLM prompt with **raw** (truncated) error + optional code + language
   - System prompt: `"You are a debugging assistant. Analyze the error and suggest a fix. Be concise: state the cause in 1-2 sentences, then provide the corrected code. If the original code is provided, show the fix as a minimal diff."`
4. Call `get_router().route(messages)`
5. Return parsed error (for UI) + LLM suggestion

**Error patterns:**
```python
ERROR_PATTERNS = {
    "python": re.compile(
        r'(?:File "(?P<file>.+?)", line (?P<line>\d+).*?\n)?'
        r'(?P<type>\w+Error): (?P<message>.+)', re.DOTALL,
    ),
    "javascript": re.compile(
        r'(?P<type>\w*Error): (?P<message>.+?)'
        r'(?:\n\s+at .+?[:\(](?P<file>.+?):(?P<line>\d+))?', re.DOTALL,
    ),
    "bash": re.compile(r'.*line (?P<line>\d+): (?P<message>.+)'),
}
```

**Result data:**
```python
{
    "parsed_error": {
        "type": str | None,
        "message": str,
        "file": str | None,
        "line": int | None,
    },
    "suggestion": str,
    "language": str,
}
```

### 5.5 GitTool (`git.py`)

**Registration:** `name = "git.ops"`, `category = ToolCategory.GIT`, `tier = Tier.ELEVATED`, `requires_approval = False` (static), conditional via `needs_approval()` override

**Purpose:** Single tool with 7 subcommands for git operations. Runs commands via `SandboxManager.execute_command()` with workspace volume. Conditional approval for push/PR.

**Params:**
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `operation` | str | Yes | — | `"clone"`, `"status"`, `"diff"`, `"log"`, `"commit"`, `"push"`, `"create_pr"` |
| `repo_url` | str | For clone | — | Repository URL (HTTPS or SSH) |
| `path` | str | No | `"/workspace"` | Working directory |
| `message` | str | For commit | — | Commit message |
| `branch` | str | No | current | Branch for push |
| `title` | str | For create_pr | — | PR title |
| `body` | str | No | `""` | PR description |
| `base_branch` | str | No | `"main"` | PR base branch |

**Operations:**

| Operation | Command Format | Network | Approval | Docker Image |
|-----------|---------------|---------|----------|-------------|
| `clone` | `["git", "clone", "--depth", "1", url, path]` | Yes | No | `alpine/git` |
| `status` | `["git", "-C", path, "status"]` | No | No | `alpine/git` |
| `diff` | `["git", "-C", path, "diff"]` | No | No | `alpine/git` |
| `log` | `["git", "-C", path, "log", "--oneline", "-20"]` | No | No | `alpine/git` |
| `commit` | `["sh", "-c", "cd ... && git add -A && git commit -m ..."]` | No | No | `alpine/git` |
| `push` | `["git", "-C", path, "push", "origin", branch]` | Yes | **Yes** | `alpine/git` |
| `create_pr` | `["sh", "-c", "cd ... && gh pr create ..."]` | Yes | **Yes** | `alpine/git` |

**List commands vs sh -c:** Only `commit` and `create_pr` use `sh -c` (compound commands). The other 5 use safe list commands with no shell interpretation — minimizes injection surface. `sh` is used instead of `bash` because `alpine/git` (Alpine Linux) does not include `bash`.

**Shell escaping:** All user values in `sh -c` commands use `shlex.quote()`.

**Validation:**
- `code_settings.enabled` must be `True`
- `operation` must be a valid subcommand
- Per-operation required params (clone needs repo_url, commit needs message, create_pr needs title)
- **Clone URL validation:**
  - Block local paths: reject URLs starting with `/` or `file://`
  - Host whitelist: extract host from HTTPS (`urllib.parse`) or SSH (`regex`) URL, check against `git_allowed_hosts`

**Conditional approval:**
```python
def needs_approval(self, params: ToolParams) -> bool:
    op = params.args.get("operation", "")
    return op in ("push", "create_pr")
```

**Approval dialog context:**
```python
def describe_action(self, params: ToolParams) -> str:
    op = params.args["operation"]
    if op == "push":
        return f"Push to {params.args.get('branch', 'current branch')}"
    if op == "create_pr":
        return f"Create PR: {params.args.get('title', 'untitled')}"
    return f"Git {op}"
```

**Workspace volume:** Every operation mounts `nobla-git-{connection_id[:8]}` at `/workspace`. Clone writes to it; subsequent operations read/modify it. Same cleanup as package volumes (session end + kill switch).

**`create_pr` and the `gh` CLI:** The stock `alpine/git` image does **not** include `gh`. Out of the box, `create_pr` will always trigger the fallback. This is by design for Phase 4C — full `gh` support requires a custom Docker image:

```dockerfile
# Example: custom git image with gh CLI (future enhancement)
FROM alpine/git:latest
RUN apk add --no-cache github-cli
```

Users who want native PR creation can set `git_image` in `CodeExecutionSettings` to a custom image that includes `gh`, and add it to `SandboxSettings.allowed_images`. Until then, the fallback provides a direct URL:

```python
{
    "success": False,
    "error": "GitHub CLI (gh) not available — use the URL below to create the PR manually",
    "fallback_url": "https://github.com/{owner}/{repo}/compare/{base}...{branch}",
}
```

**Result data:**
```python
{
    "operation": str,
    "stdout": str,
    "stderr": str,
    "exit_code": int,
    "success": bool,
}
```

---

## 6. Permission Model

| Tool | Required Tier | Approval | Rationale |
|------|--------------|----------|-----------|
| `code.run` | STANDARD | No | Sandboxed execution, no external access |
| `code.install_package` | ELEVATED | No | Requires network access |
| `code.generate` | STANDARD | No | LLM-driven, output is text (or sandboxed if run=True) |
| `code.debug` | STANDARD | No | Read-only analysis |
| `git.ops` (clone) | ELEVATED | No | Network + disk write |
| `git.ops` (status/diff/log) | ELEVATED | No | Read-only repo access |
| `git.ops` (commit) | ELEVATED | No | Local repo modification |
| `git.ops` (push) | ELEVATED | **Yes** | Remote modification — externally visible |
| `git.ops` (create_pr) | ELEVATED | **Yes** | External service action — externally visible |

**Principle:** Approval is required for actions that are externally visible (push, PR). Sandboxed and local actions skip approval for speed.

---

## 7. Error Handling

### Graceful Degradation

| Condition | Behavior |
|-----------|----------|
| Docker unavailable | Return clear error: "Docker SDK not available" |
| Language not supported | Validation error with supported list |
| Package install fails | Return output with failure details |
| LLM router has no healthy providers | RuntimeError propagated as tool error |
| `gh` CLI not in container | Return fallback URL for manual PR creation |
| Git clone from non-whitelisted host | Validation error with allowed hosts list |
| Local file path in clone URL | Validation error: "Local paths not allowed" |
| Output exceeds max_output_length | Truncated with `truncated: true` flag |

### JSON-RPC Error Codes

Reuses existing tool platform error codes from Phase 4-Pre:
- `TOOL_VALIDATION_FAILED (-32041)` — bad params, unsupported language, blocked URL
- `TOOL_EXECUTION_ERROR (-32044)` — Docker failure, sandbox timeout
- `TOOL_APPROVAL_DENIED (-32042)` — user denied push/PR
- `TOOL_APPROVAL_TIMEOUT (-32043)` — approval dialog timed out

---

## 8. Testing Strategy

### Unit Tests (per tool, ~250 lines total)

- **CodeRunnerTool:** Mock SandboxManager, verify volume mounting, output truncation, language validation
- **PackageInstallTool:** Mock SandboxManager.execute_command(), verify command list construction (no string interpolation), package name regex, network=True
- **CodeGenerationTool:** Mock LLMRouter, verify system prompt, code fence extraction, run=True integration with mock run_code()
- **DebugAssistantTool:** Test error parsing regex against sample errors (Python traceback, Node error, Bash error, unknown format), mock LLMRouter
- **GitTool:** Verify command construction per operation, needs_approval() returns True for push/PR only, URL validation (block local paths, non-whitelisted hosts), shlex.quote usage

### Platform Change Tests (~50 lines)

- **needs_approval():** Default returns class variable, override works
- **SandboxManager.execute():** New params passed to Docker correctly, None defaults preserve existing behavior
- **SandboxManager.execute_command():** Command list passed to container
- **SandboxManager.cleanup_volumes():** Removes matching volumes

### Integration Tests (~100 lines)

- End-to-end: WebSocket → tool.execute("code.run") → sandbox → result
- Package install → code.run sees installed package
- Code generate with run=True → returns code + execution output
- Git clone → git status shows cloned repo (workspace volume persists)
- Git push triggers approval flow
- Kill switch cleans up volumes

### Security Tests (~50 lines)

- STANDARD tier can access code.run, code.generate, code.debug
- STANDARD tier cannot access code.install_package, git.ops
- Package name regex blocks shell metacharacters
- Git clone blocks local file paths
- Git clone blocks non-whitelisted hosts
- All user values in git commands are shlex.quote'd

---

## 9. Dependencies

| Component | Package | Existing? | Purpose |
|-----------|---------|-----------|---------|
| Sandbox | docker | Yes | Container execution |
| Settings | pydantic | Yes | CodeExecutionSettings |
| LLM routing | (internal) | Yes | code.generate, code.debug |
| Shell escaping | shlex | Yes (stdlib) | Git command safety |
| URL parsing | urllib.parse | Yes (stdlib) | Git URL validation |
| Regex | re | Yes (stdlib) | Error parsing, code extraction, package name validation |
| Git operations | — | No new deps | Uses git CLI in `alpine/git` container |

No new external dependencies. All tools use existing infrastructure (Docker, LLMRouter) via the sandbox and router abstractions.

---

## 10. Open Questions (Resolved)

| Question | Resolution |
|----------|------------|
| Persistent vs ephemeral containers? | Docker volumes for persistence, ephemeral containers for execution |
| Single vs multiple git tools? | Single GitTool with subcommands and conditional approval |
| code.generate auto-run? | Returns code + execution result when `run=True` |
| LLM routing for code tasks? | Router classifies naturally — no forced override |
| Language auto-detection? | Language required with Python default |

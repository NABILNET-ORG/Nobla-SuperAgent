# Phase 4D: Remote Control — Implementation Prompt

Execute the Phase 4D implementation plan to build SSH connection management, remote command execution, and SFTP file transfer for Nobla Agent.

## What's Done

### Completed Phases
- **Phase 1** (1A/1B/1C): Gateway, Auth, Sandbox, Kill Switch, Flutter basic chat
- **Phase 2** (2A/2B): 5-layer memory engine, LLM router with 6 providers, AI search
- **Phase 3** (3A/3B): Voice pipeline (STT/TTS), Persona engine, PersonaPlex, Management UI
- **Phase 4-Pre**: Tool platform — BaseTool ABC, registry, executor, approval manager
- **Phase 4A**: Screen Vision — screenshot capture, OCR, UI element detection, NL targeting (158 tests)
- **Phase 4B**: Computer Control — mouse.control, keyboard.control, file.manage, app.control, clipboard.manage (191 tests)
- **Phase 4C**: Code Execution — code.run, code.install_package, code.generate, code.debug, git.ops (110 tests)

### Phase 4D Design (complete, ready to implement)
- **Design spec:** `docs/superpowers/specs/2026-03-25-phase4d-remote-control-design.md`
- **Implementation plan:** `docs/superpowers/plans/2026-03-25-phase4d-remote-control.md`

## What to Build

**Phase 4D: Remote Control** — 3 tools, shared infrastructure, ~150 tests.

### Tools
| Tool | Purpose | Actions |
|------|---------|---------|
| `ssh.connect` | Connection lifecycle | connect, disconnect, list |
| `ssh.exec` | Remote command execution | run (conditional approval) |
| `sftp.manage` | Remote file transfer | upload, download, list, delete, stat |

### Shared Infrastructure
| Component | File | Purpose |
|-----------|------|---------|
| `RemoteControlSettings` | `backend/nobla/config/settings.py` | Allow-lists, deny-lists, timeouts |
| `RemoteControlGuard` | `backend/nobla/tools/remote/safety.py` | Halt, blocked commands, connection caps |
| `SSHConnectionPool` | `backend/nobla/tools/remote/pool.py` | Persistent sessions with lifecycle |

### 8 Tasks (in order)
1. **RemoteControlSettings** — config + conftest.py + test package setup
2. **RemoteControlGuard** — safety checks (halt, allow-lists, deny-lists)
3. **SSHConnectionPool** — connection lifecycle, cleanup, halt
4. **ssh.connect** — connect/disconnect/list with ADMIN tier
5. **ssh.exec** — run with conditional approval (safe_commands skip, chained require)
6. **sftp.manage** — upload/download/list/delete/stat with path validation
7. **__init__.py wiring** — tool registration + kill switch callbacks
8. **Full test suite + docs** — verify all tests pass, update CLAUDE.md and Plan.md

**Parallelism:** Tasks 2+3 can run in parallel. Tasks 4+5+6 can run in parallel.

## How to Proceed

1. Read the implementation plan: `docs/superpowers/plans/2026-03-25-phase4d-remote-control.md`
2. Use **superpowers:subagent-driven-development** to execute the plan
3. Follow TDD strictly: tests first → run to fail → implement → run to pass → commit
4. Each task has exact code, file paths, and test commands — follow them precisely

### Key Patterns to Follow (from Phase 4B)
- `@register_tool` on `BaseTool` subclasses
- Module-level `_settings_cache` with `_get_settings()` (Phase 4D caches full `Settings` — documented deviation)
- `_settings_override` instance attribute for test injection
- Conditional `needs_approval(params)` override
- `RemoteControlGuard.check(operation, settings, **kwargs)` unified entry point
- `_get_pool()` lazy singleton for SSHConnectionPool
- Autouse fixture in `conftest.py` resets guard + pool between tests
- All error ToolResults use `data={}` (not `data=None`)

### Key Reference Files
- `backend/nobla/tools/control/mouse.py` — Tool structure, settings cache, conditional approval
- `backend/nobla/tools/control/file_manager.py` — Path validation, allow-list pattern
- `backend/nobla/tools/control/safety.py` — InputSafetyGuard (model for RemoteControlGuard)
- `backend/nobla/tools/code/git.py` — Enabled check in validate(), network operations
- `backend/nobla/tools/base.py` — BaseTool ABC
- `backend/nobla/config/settings.py` — ComputerControlSettings (model for RemoteControlSettings)
- `backend/nobla/security/killswitch.py` — Kill switch callback registration
- `backend/tests/tools/control/test_mouse.py` — Test structure, mocking pattern

### Security Constraints (non-negotiable)
- All tools are **ADMIN tier** (Tier.ADMIN)
- 6-layer security: tier gating → allow-lists → deny-lists → conditional approval → rate limits → kill switch
- Credentials (password, passphrase, key content) are **NEVER logged** — redacted in `get_params_summary()`
- Host key verification via `known_hosts_policy` (strict or ask_first_time)
- Remote paths must be absolute, normalised with `posixpath.normpath()`, validated against allow-list
- Kill switch terminates ALL SSH sessions immediately via `SSHConnectionPool.halt()`
- `asyncssh` graceful degradation if not installed

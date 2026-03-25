# Phase 4D: Remote Control — Continuation Prompt

We're building **Nobla Agent** — an open-source, privacy-first AI super agent. Phase 4B: Computer Control is complete and merged. Now it's time to design and implement Phase 4D: Remote Control.

## What's Done

### Completed Phases
- **Phase 1** (1A/1B/1C): Gateway, Auth, Sandbox, Kill Switch, Flutter basic chat
- **Phase 2** (2A/2B): 5-layer memory engine, LLM router with 6 providers, AI search
- **Phase 3** (3A/3B): Voice pipeline (STT/TTS), Persona engine, PersonaPlex, Management UI
- **Phase 4-Pre**: Tool platform — BaseTool ABC, registry, executor, approval manager
- **Phase 4A**: Screen Vision — screenshot capture, OCR, UI element detection, NL targeting (158 tests)
- **Phase 4B**: Computer Control — mouse.control, keyboard.control, file.manage, app.control, clipboard.manage + Flutter approval UI (191 tests)
- **Phase 4C**: Code Execution — code.run, code.install_package, code.generate, code.debug, git.ops (110 tests)

### Phase 4B Architecture (just completed, reference for 4D)
- 5 tools in `backend/nobla/tools/control/` using `@register_tool` on `BaseTool` subclasses
- `InputSafetyGuard` for rate limiting, kill switch halt, platform detection
- `ComputerControlSettings` with allow-list patterns (allowed_read_dirs, allowed_write_dirs, allowed_apps)
- Conditional `needs_approval(params)` per-action (e.g., drag needs approval, click doesn't)
- Host-level execution (not Docker) wrapped in 6-layer security model
- Lazy singletons: `_get_settings()`, `_settings_override` for test injection
- Flutter approval bottom sheet + activity feed in `app/lib/features/security/`
- TDD throughout: tests first, then implementation, 191 tests total

## What to Build Next

**Phase 4D: Remote Control** — SSH connections, remote command execution, file transfer

### Scope (from Plan.md)
- [ ] SSH integration: connect to remote machines
- [ ] Remote command execution with audit logging
- [ ] File transfer: upload/download via SCP/SFTP

### Architecture Considerations
- All remote operations are **ADMIN tier** — highest permission level, requires passphrase
- SSH credentials must NEVER be stored in plaintext — use encrypted keyring or agent forwarding
- Every remote command must be logged to the audit trail with full details
- Remote connections should go through the existing SandboxManager OR a new `RemoteManager`
- Consider using `paramiko` or `asyncssh` for SSH
- File transfers need size limits and allow-list of remote paths
- The approval flow (from Phase 4B) must be used for all remote operations
- Kill switch must be able to terminate active SSH sessions

### Key Files to Reference
- `backend/nobla/tools/control/app.py` — Host-level tool with subprocess management (PID tracking pattern)
- `backend/nobla/tools/control/file_manager.py` — Allow-list pattern for path validation
- `backend/nobla/tools/code/git.py` — Conditional approval pattern, network-enabled operations
- `backend/nobla/tools/base.py` — BaseTool ABC with `needs_approval(params)`
- `backend/nobla/tools/executor.py` — Full execution pipeline with approval flow
- `backend/nobla/security/sandbox.py` — SandboxManager with network/volume support
- `backend/nobla/config/settings.py` — Settings pattern (ComputerControlSettings as reference)
- `app/lib/features/security/` — Flutter approval UI (bottom sheet + activity feed)

### Key Design Constraints
- **750-line hard limit per file** — split into well-named modules
- **Security is non-negotiable** — ADMIN tier, all operations need approval, full audit trail
- **Privacy by default** — SSH keys stay local, no cloud storage of credentials
- **Mobile-first** — Flutter approval UI must work for remote operations
- **Graceful degradation** — if paramiko/asyncssh unavailable, return clear error

## How to Proceed

1. Use **superpowers:brainstorming** to explore requirements, risks, and design decisions for 4D
2. Use **superpowers:writing-plans** to create a detailed implementation plan
3. Get the plan reviewed and approved
4. Use **superpowers:subagent-driven-development** to execute the plan

### Open Questions for Brainstorming
- Should SSH connections use `paramiko` (sync, mature) or `asyncssh` (async-native)?
- How should SSH credentials be managed? Keyring, env vars, agent forwarding, or all three?
- Should remote command execution be a single tool (`ssh.exec`) or compound (`remote.ops` with subcommands)?
- How does SCP/SFTP interact with the existing `file.manage` tool? Separate tool or extension?
- Should there be a connection pool for persistent SSH sessions, or ephemeral per-command?
- What about SSH tunneling / port forwarding for accessing remote services?
- How to handle interactive shells (PTY) vs. non-interactive command execution?

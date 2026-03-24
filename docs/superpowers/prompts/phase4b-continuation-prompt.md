# Phase 4B: Computer Control — Continuation Prompt

We're building **Nobla Agent** — an open-source, privacy-first AI super agent. Phase 4C: Code Execution is complete and merged. Now it's time to design and implement Phase 4B: Computer Control.

## What's Done

### Completed Phases
- **Phase 1** (1A/1B/1C): Gateway, Auth, Sandbox, Kill Switch, Flutter basic chat
- **Phase 2** (2A/2B): 5-layer memory engine, LLM router with 6 providers, AI search
- **Phase 3** (3A/3B): Voice pipeline (STT/TTS), Persona engine, PersonaPlex, Management UI
- **Phase 4-Pre**: Tool platform — BaseTool ABC, registry, executor, approval manager
- **Phase 4A**: Screen Vision — screenshot capture, OCR, UI element detection, NL targeting (158 tests)
- **Phase 4C**: Code Execution — code.run, code.install_package, code.generate, code.debug, git.ops (110 tests)

### Phase 4C Architecture (just completed, reference for 4B)
- 5 tools in `backend/nobla/tools/code/` using `@register_tool` on `BaseTool` subclasses
- `SandboxManager` extended with `execute_command()`, `_run_container()`, volumes/network/environment support
- `needs_approval(params)` for conditional approval (GitTool uses it for push/create_pr)
- Lazy singletons: `get_settings()`, `get_sandbox()`, `get_router()`
- Shared `run_code()` free function reused by CodeRunnerTool and CodeGenerationTool
- `CodeExecutionSettings` in `config/settings.py` with `Field(default_factory=...)`
- TDD throughout: tests first, then implementation, 110 tests total

## What to Build Next

**Phase 4B: Computer Control** — Mouse, keyboard, file management, app control + Flutter approval UI

### Scope (from Plan.md)
- [ ] Mouse control: move, click, drag, scroll
- [ ] Keyboard control: type, shortcuts, key combinations
- [ ] File management: browse, read, write, move, delete
- [ ] App management: launch, close, switch, list
- [ ] Clipboard management
- [ ] Flutter approval UI for dangerous actions

### Architecture Considerations
- All computer control actions execute through the existing `SandboxManager` or via system-level APIs
- Mouse/keyboard actions are **ELEVATED or ADMIN tier** — they affect the user's actual system
- File operations need path validation against allowed directories (similar to git's `_validate_repo_url`)
- The approval UI in Flutter is critical — push/create_pr already use `needs_approval(params)`, 4B extends this pattern
- Screen Vision (Phase 4A) provides the "eyes" — 4B provides the "hands"
- Consider using `pyautogui` or `pynput` for mouse/keyboard (not sandboxed — runs on host)
- File operations could use the existing sandbox for isolation OR run on host with strict path validation

### Key Files to Reference
- `backend/nobla/tools/code/runner.py` — Reference tool implementation (lazy singletons, validation, execution pattern)
- `backend/nobla/tools/code/git.py` — Conditional approval pattern (`needs_approval()` override)
- `backend/nobla/tools/base.py` — BaseTool ABC with `needs_approval(params)`
- `backend/nobla/tools/registry.py` — `@register_tool` decorator
- `backend/nobla/tools/executor.py` — Full execution pipeline with approval flow
- `backend/nobla/tools/vision/` — Screen Vision tools (4B builds on these)
- `backend/nobla/security/sandbox.py` — SandboxManager with `_run_container()`, `execute_command()`
- `backend/nobla/config/settings.py` — Settings pattern (`CodeExecutionSettings` as reference)
- `app/lib/features/security/` — Existing Flutter security dashboard (extend for approval UI)

### Key Design Constraints
- **750-line hard limit per file** — split into well-named modules
- **Security is non-negotiable** — 4-tier permission model, all dangerous actions need approval
- **Privacy by default** — no data leaves user's machine unless explicit
- **Mobile-first** — Flutter is the primary interface, approval UI must work on mobile
- **Graceful degradation** — if pyautogui unavailable, return clear error

## How to Proceed

1. Use **superpowers:brainstorming** to explore requirements, risks, and design decisions for 4B
2. Use **superpowers:writing-plans** to create a detailed implementation plan (like Phase 4C's plan)
3. Get the plan reviewed and approved
4. Use **superpowers:subagent-driven-development** to execute the plan (same workflow as 4C)

### Open Questions for Brainstorming
- Should mouse/keyboard tools run on host (pyautogui) or in sandbox (xdotool in Docker with X11 forwarding)?
- How granular should file permissions be? Allow-list of directories? Regex patterns?
- Should the Flutter approval UI be a modal dialog, a persistent panel, or a notification-style prompt?
- How does 4B interact with 4A (vision)? E.g., "click the Submit button" = vision finds it → mouse clicks coordinates
- Should clipboard operations be a separate tool or part of keyboard control?
- What about multi-monitor support for mouse operations?

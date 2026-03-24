We're building **Nobla Agent** — an open-source, privacy-first AI super agent. Phase 4C: Code Execution has been designed and planned. Now it's time to implement.

### What's Done

- **Design spec** (approved, reviewed 3 iterations): `docs/superpowers/specs/2026-03-24-phase4c-code-execution-design.md`
- **Implementation plan** (approved, reviewed): `docs/superpowers/plans/2026-03-24-phase4c-code-execution.md`

### What to Build

**Phase 4C: Code Execution** — 5 tools in `backend/nobla/tools/code/` plus platform changes:

1. `code.run` — Wraps SandboxManager with Docker volume mounting for packages
2. `code.install_package` — pip/npm install into shared Docker volume, network enabled
3. `code.generate` — LLM router with code-gen system prompt, optional sandbox execution
4. `code.debug` — Error parsing + LLM fix suggestions, read-only
5. `git.ops` — Single tool, 7 subcommands (clone/status/diff/log/commit/push/create_pr), conditional approval for push/PR

**Platform changes:**
- `config/settings.py` — Add `CodeExecutionSettings` + update `SandboxSettings.allowed_images`
- `tools/base.py` — Add `needs_approval(params)` method (3 lines)
- `tools/executor.py` — Change approval check to use `needs_approval(params)` (1 line)
- `security/sandbox.py` — Add `volumes`/`network`/`environment` to `execute()`, new `execute_command()`, new `cleanup_volumes()`, extend `kill_all()`

### How to Proceed

1. Read the implementation plan: `docs/superpowers/plans/2026-03-24-phase4c-code-execution.md`
2. Use **superpowers:subagent-driven-development** to execute the plan
3. Tasks 0-1 must go first (platform foundation), then Tasks 2-6 can be parallelized, Task 7 last (wiring + integration)

### Key Patterns (from Phase 4A)
- Lazy `get_settings()` with module-level cache
- `@register_tool` decorator on BaseTool subclasses
- `asyncio.to_thread()` for blocking calls
- TDD: write tests first, then implement
- 750-line hard limit per file

### Key Files to Reference
- `backend/nobla/tools/vision/capture.py` — Reference tool implementation
- `backend/nobla/tools/base.py` — BaseTool ABC
- `backend/nobla/tools/registry.py` — @register_tool
- `backend/nobla/security/sandbox.py` — SandboxManager to extend
- `backend/nobla/brain/router.py` — LLMRouter for codegen/debug
- `backend/tests/test_tool_executor.py` — Test patterns

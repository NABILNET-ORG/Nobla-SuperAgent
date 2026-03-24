# Phase 4C: Code Execution — Continuation Prompt

Copy and paste everything below the line into a new Claude Code session.

---

We're building **Nobla Agent** — an open-source, privacy-first AI super agent. We just completed **Phase 4A: Screen Vision** and are ready to start **Phase 4C: Code Execution**.

### What's Done

**Phase 4-Pre** (Tool Platform Foundation — 51 tests):
- `backend/nobla/tools/models.py` — ToolCategory, ToolParams, ToolResult, ApprovalRequest, ApprovalStatus
- `backend/nobla/tools/base.py` — BaseTool ABC (execute, validate, describe_action, get_params_summary)
- `backend/nobla/tools/registry.py` — @register_tool decorator + ToolRegistry
- `backend/nobla/tools/executor.py` — ToolExecutor with 5-step pipeline, semaphore concurrency, kill switch
- `backend/nobla/tools/approval.py` — ApprovalManager (asyncio.Future WebSocket round-trip)
- `backend/nobla/gateway/tool_handlers.py` — tool.execute, tool.list, tool.approval_response RPC
- `backend/nobla/config/settings.py` — ToolPlatformSettings + VisionSettings

**Phase 4A** (Screen Vision — 158 tests):
- `backend/nobla/tools/vision/capture.py` — ScreenshotTool (mss, multi-monitor, downscaling)
- `backend/nobla/tools/vision/ocr.py` — OCRTool (Tesseract + EasyOCR fallback)
- `backend/nobla/tools/vision/detection.py` — UIDetectionTool (OCR heuristics + UI-TARS stub)
- `backend/nobla/tools/vision/targeting.py` — ElementTargetingTool (NL → coordinates)
- `backend/nobla/tools/vision/cache.py` — ElementCache with TTL + thumbnail hashing
- Key patterns: dual interface (public execute + internal method), lazy `get_settings()`, `asyncio.to_thread()` for blocking calls, `@register_tool` decorator

**Phases 1-3** (previously completed): Gateway, Auth, Sandbox, Memory System, LLM Router, Search, Voice Pipeline, Persona Engine, Management UI.

### What's Next

**Phase 4C: Code Execution** — tools that plug into the tool platform. From the spec at `docs/superpowers/specs/2026-03-23-phase4-computer-control-vision-design.md`, Section 6.3:

**Scope:** `backend/nobla/tools/code/` — 5 tools

**Tools to build:**
1. `code.run` — Thin wrapper around existing `SandboxManager` (`security/sandbox.py`). Adds language auto-detection, structured output parsing, tool platform integration. Tier: STANDARD, no approval.
2. `code.install_package` — Runs pip/npm install inside a persistent sandbox container. Tier: ELEVATED, no approval.
3. `code.generate` — Routes description through LLM router (`brain/router.py`) with code-generation system prompt. Returns generated code + optional sandbox execution. Tier: STANDARD, no approval.
4. `code.debug` — Parses error messages, identifies error type, suggests fixes via LLM. Read-only analysis. Tier: STANDARD, no approval.
5. `git.*` — Git operations via subprocess in sandbox. Clone, commit, push, PR creation. GitHub/GitLab API integration for PR creation. Tier: ELEVATED, push/PR require approval.

**Key design:** `code.run` does NOT replace `SandboxManager` — it wraps it. The sandbox stays in `security/sandbox.py` for kill switch integration.

### How to Proceed

1. Use **superpowers:brainstorming** to design Phase 4C (the spec has high-level design, but we need detailed implementation design for the 5 code tools)
2. The design spec answers are in `docs/superpowers/specs/2026-03-23-phase4-computer-control-vision-design.md` (Section 6.3) and `PRD.md`
3. After design approval → **superpowers:writing-plans** → **superpowers:subagent-driven-development** to implement

### Key Files to Read First
- `docs/superpowers/specs/2026-03-23-phase4-computer-control-vision-design.md` — Full Phase 4 design spec (Section 6.3 = Code Execution)
- `docs/superpowers/plans/2026-03-24-phase4a-screen-vision.md` — Completed Phase 4A plan (reference for patterns)
- `backend/nobla/tools/base.py` — BaseTool ABC
- `backend/nobla/tools/registry.py` — @register_tool decorator
- `backend/nobla/tools/vision/capture.py` — Reference implementation (dual interface, lazy settings pattern)
- `backend/nobla/security/sandbox.py` — Existing SandboxManager (code.run wraps this)
- `backend/nobla/brain/router.py` — LLM router (code.generate uses this)
- `backend/nobla/config/settings.py` — Where to add CodeExecutionSettings

### Constraints
- 750-line hard limit per file
- TDD: write tests first
- Each tool is a class inheriting BaseTool with @register_tool
- Lazy `get_settings()` pattern (not module-scope `Settings()`)
- `asyncio.to_thread()` for blocking calls
- Privacy-first: all processing local, no cloud APIs unless explicitly enabled

Start by reading the design spec, then brainstorm the Phase 4C implementation details.

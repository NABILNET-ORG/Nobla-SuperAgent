# Phase 4A: Screen Vision — Continuation Prompt

Copy and paste this into a new Claude Code session to continue Phase 4 development.

---

## Prompt

We're building **Nobla Agent** — an open-source, privacy-first AI super agent. We just completed **Phase 4-Pre: Tool Platform Foundation** and are ready to start **Phase 4A: Screen Vision**.

### What's Done

**Phase 4-Pre** (just completed — all committed on `main`, 51 tests passing):
- `backend/nobla/tools/models.py` — ToolCategory, ToolParams, ToolResult, ApprovalRequest, ApprovalStatus
- `backend/nobla/tools/base.py` — BaseTool ABC (execute, validate, describe_action, get_params_summary)
- `backend/nobla/tools/registry.py` — @register_tool decorator + ToolRegistry (get, list_all, list_by_category, list_available, get_manifest)
- `backend/nobla/tools/executor.py` — ToolExecutor with 5-step pipeline (exists → permission → validate → approve → execute), semaphore concurrency, kill switch integration (handle_kill cancels tasks + denies approvals), activity feed notifications via WebSocket
- `backend/nobla/tools/approval.py` — ApprovalManager (asyncio.Future-based WebSocket approval round-trip)
- `backend/nobla/gateway/tool_handlers.py` — tool.execute, tool.list, tool.approval_response RPC methods
- `backend/nobla/gateway/code_handlers.py` — Extracted code.execute handler (delegates to tool platform when available)
- `backend/nobla/config/settings.py` — ToolPlatformSettings added
- `backend/nobla/gateway/app.py` — ToolExecutor + ApprovalManager wired into app lifespan with kill switch callback

**Phases 1-3** (previously completed): Gateway, Auth, Sandbox, Memory System, LLM Router, Search, Voice Pipeline, Persona Engine, Management UI.

### What's Next

**Phase 4A: Screen Vision** — the first tools to plug into the tool platform. From the spec at `docs/superpowers/specs/2026-03-23-phase4-computer-control-vision-design.md`, Section 6.2:

**Scope:** `backend/nobla/tools/vision/` — 4 tools

**Tools to build:**
1. `screenshot.capture` — Uses `mss` (python-mss) for fast cross-platform capture. Returns base64 PNG/JPEG. Supports multi-monitor, region capture, resolution scaling. Tier: STANDARD, no approval needed.
2. `ocr.extract` — Tesseract (primary) + EasyOCR (fallback). Returns text with bounding box coordinates and confidence scores. Multi-language via settings. Tier: STANDARD.
3. `ui.detect_elements` — UI-TARS model for GUI element detection. Returns element list with type, label, bounding box, confidence. Progressive: disabled by default, falls back to OCR-based detection. Tier: STANDARD.
4. `ui.target_element` — Natural language → (x, y) coordinates. Takes a description ("the blue Submit button") and returns the best matching element's center coordinates. Uses vision tools internally. Tier: STANDARD.

**Settings to add:** `VisionSettings` to `config/settings.py` (already designed in spec Section 4).

**Tech stack:** python-mss, Pillow, pytesseract, easyocr, UI-TARS (optional)

### How to Proceed

1. Use **superpowers:brainstorming** to design Phase 4A (the spec has high-level design, but we need detailed implementation design for the 4 vision tools)
2. The answers to clarifying questions are in `docs/superpowers/specs/2026-03-23-phase4-computer-control-vision-design.md` and `PRD.md`
3. After design approval → **superpowers:writing-plans** → **superpowers:subagent-driven-development** to implement

### Key Files to Read First
- `docs/superpowers/specs/2026-03-23-phase4-computer-control-vision-design.md` — Full Phase 4 design spec
- `docs/superpowers/plans/2026-03-23-phase4-pre-tool-platform.md` — Completed plan (reference for patterns)
- `backend/nobla/tools/base.py` — BaseTool ABC (tools inherit from this)
- `backend/nobla/tools/registry.py` — @register_tool decorator (tools register with this)
- `backend/nobla/tools/executor.py` — ToolExecutor (runs tools through the pipeline)
- `backend/nobla/config/settings.py` — Where to add VisionSettings

### Constraints
- 750-line hard limit per file
- TDD: write tests first
- Each vision tool is a class inheriting BaseTool with @register_tool
- UI-TARS is progressive (off by default, system works with OCR alone)
- Privacy-first: all processing local, no cloud APIs unless explicitly enabled

Start by reading the design spec, then brainstorm the Phase 4A implementation details.

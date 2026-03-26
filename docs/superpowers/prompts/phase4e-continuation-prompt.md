# Phase 4E: Flutter Tool UI — Continuation Prompt

Paste the following into a new Claude Code session to begin Phase 4E.

---

## Prompt

Continue building Nobla Agent. Phase 4E: Flutter Tool UI — screen mirror, activity feed, and tool browser.

### What's Done

#### Completed Phases
- **Phase 1** (1A/1B/1C): Gateway, Auth, Sandbox, Kill Switch, Flutter basic chat
- **Phase 2** (2A/2B): 5-layer memory engine, LLM router with 6 providers, AI search
- **Phase 3** (3A/3B): Voice pipeline (STT/TTS), Persona engine, PersonaPlex, Management UI
- **Phase 4-Pre**: Tool platform — BaseTool ABC, registry, executor, approval manager
- **Phase 4A**: Screen Vision — screenshot capture, OCR, UI element detection, NL targeting (158 tests)
- **Phase 4B**: Computer Control — mouse.control, keyboard.control, file.manage, app.control, clipboard.manage (191 tests)
- **Phase 4C**: Code Execution — code.run, code.install_package, code.generate, code.debug, git.ops (110 tests)
- **Phase 4D**: Remote Control — ssh.connect, ssh.exec, sftp.manage (116 tests)

### What to Build Next

**Phase 4E: Flutter Tool UI** — The frontend counterpart to the tool platform built in Phases 4A-4D.

| Component | Purpose |
|-----------|---------|
| Screen mirror | Real-time view of what the agent sees (Phase 4A screenshots streamed to Flutter) |
| Activity feed | Live log of all tool executions with status, timing, and approval history |
| Tool browser | Browse available tools by category, view descriptions, tier requirements |

### How to Proceed

1. Use **superpowers:brainstorming** to explore requirements and UI design
2. Use **superpowers:writing-plans** to create a detailed implementation plan
3. Use **superpowers:subagent-driven-development** to execute the plan

### Key Reference Files
- `app/lib/features/` — Existing Flutter feature modules
- `app/lib/core/` — Theme, routing, DI (Riverpod)
- `backend/nobla/tools/models.py` — ToolCategory, ToolResult, ApprovalRequest
- `backend/nobla/tools/executor.py` — Tool execution pipeline (emits events)
- `backend/nobla/gateway/websocket.py` — WebSocket event broadcasting
- `docs/superpowers/specs/2026-03-25-phase4d-remote-control-design.md` — Section 9 (Flutter Integration) for reuse patterns

### Design Constraints
- Mobile-first (Flutter 3.x / Dart)
- Riverpod for state management
- Reuse existing approval_sheet.dart and activity_feed.dart where possible
- WebSocket for real-time updates
- 750-line hard limit per file

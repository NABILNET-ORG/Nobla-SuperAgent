# Phase 4E: Flutter Tool UI — Implementation Prompt

Paste the following into a new Claude Code session to implement Phase 4E.

---

## Prompt

Continue building Nobla Agent. Implement Phase 4E: Flutter Tool UI — screen mirror, activity feed, and tool browser.

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

#### Phase 4E Design & Plan (Already Complete)
- **Design spec:** `docs/superpowers/specs/2026-03-25-phase4e-flutter-tool-ui-design.md`
- **Implementation plan:** `docs/superpowers/plans/2026-03-25-phase4e-flutter-tool-ui.md`

### What to Implement

**Phase 4E has a 12-task implementation plan ready.** Use `superpowers:subagent-driven-development` to execute it.

#### The 12 Tasks (in order)

| Task | What It Builds |
|------|---------------|
| 1 | Models — ToolCategory, ToolManifestEntry, MirrorState, ActivityFilter + ActivityEntry category field |
| 2 | Shared activity provider — extract from ApprovalNotifier, refactor security feature |
| 3 | NotificationDispatcher — wire tool.activity events |
| 4 | Tool catalog provider + browser widgets (ToolCard, ToolCategorySection) |
| 5 | Mirror provider — subscribe/unsubscribe/capture with compute() decode |
| 6 | Filtered activity provider — category/status filtering |
| 7 | Activity feed widgets — filter bar, list, detail sheet |
| 8 | Mirror view widget — InteractiveViewer + capture button |
| 9 | ToolsScreen + router — TabBar host + 6th nav tab |
| 10 | Backend — mirror_handlers.py (subscribe/unsubscribe/capture RPC) |
| 11 | Backend — executor mirror integration + disconnect cleanup |
| 12 | Full integration test + CLAUDE.md update |

#### Key Architecture Decisions (from design spec)
- **New 6th "Tools" tab** in bottom NavigationBar (between Persona and Settings)
- **TabBar with 3 sub-views:** Mirror | Activity | Browse
- **Screen mirror:** Hybrid — event-driven screenshots on tool execution + manual "Capture Now" button
- **Activity feed:** Filterable by category/status, tap-to-expand detail sheet, 200-entry buffer
- **Tool browser:** Read-only catalog grouped by category with tier badges and approval icons
- **Shared activity state:** Extracted from security's ApprovalNotifier into shared provider
- **Mirror screenshots:** Separate `tool.mirror.frame` notification (not stuffed into tool.activity)
- **Background capture:** `asyncio.create_task()` with debounce — zero impact on tool execution latency
- **Base64 decode:** Flutter `compute()` in background isolate to avoid UI jank

### How to Proceed

1. Read the implementation plan: `docs/superpowers/plans/2026-03-25-phase4e-flutter-tool-ui.md`
2. Use **superpowers:subagent-driven-development** to execute all 12 tasks
3. Each task has complete code, tests, and commit instructions
4. Use **superpowers:verification-before-completion** before claiming done

### Key Reference Files
- `app/lib/features/security/models/approval_models.dart` — ActivityEntry, ActivityStatus (to modify)
- `app/lib/features/security/providers/approval_provider.dart` — ApprovalNotifier (to refactor)
- `app/lib/features/security/widgets/activity_feed.dart` — Existing feed (to update provider ref)
- `app/lib/core/providers/notification_provider.dart` — NotificationDispatcher (to add cases)
- `app/lib/core/routing/app_router.dart` — GoRouter + HomeShell (to add 6th tab)
- `app/lib/main.dart` — Provider initialization
- `backend/nobla/tools/executor.py` — ToolExecutor._audit() (to add mirror trigger)
- `backend/nobla/gateway/tool_handlers.py` — RPC handler pattern to follow
- `backend/nobla/gateway/websocket.py` — ConnectionManager.disconnect() (to add cleanup)
- `backend/nobla/tools/vision/capture.py` — ScreenshotTool (used by mirror capture)

### Design Constraints
- Mobile-first (Flutter 3.x / Dart)
- Riverpod StateNotifier for state management
- WebSocket JSON-RPC 2.0 for real-time updates
- 750-line hard limit per file
- TDD: write tests before implementation
- All code in the plan — follow it exactly

# Continuation Prompt — After Phase 4E Flutter Tool UI Implementation

**Paste this into a new Claude Code session to continue development.**

---

## Context

Nobla Agent is on `main`. **530 tests passing (85 Flutter + 445 backend).**

### What was just completed:

**Phase 4E — Flutter Tool UI IMPLEMENTATION (12 tasks, all complete):**

1. **Models** (`features/tools/models/tool_models.dart`): ToolCategory enum (9 values), ToolManifestEntry, MirrorState (copyWith), ActivityFilter (matches/isActive). Added `ToolCategory? category` field to ActivityEntry in approval_models.dart.

2. **Shared Activity Provider** (`shared/providers/tool_activity_provider.dart`): ToolActivityNotifier — prepend-first 200-entry buffer. Extracted from ApprovalNotifier (removed `activities` from ApprovalState, removed `onActivity` method). Updated ActivityFeed widget to use shared provider.

3. **NotificationDispatcher** (`core/providers/notification_provider.dart`): Added `tool.activity` case (creates ActivityEntry.fromJson, adds to toolActivityProvider) and `tool.mirror.frame` case (routes to toolMirrorProvider.onScreenshotNotification).

4. **Tool Catalog Provider + Browser Widgets**: `tool_catalog_provider.dart` (FutureProvider via tool.list RPC), `tool_card.dart` (tier badge SAFE/STD/ELEV/ADMIN + lock icon), `tool_category_section.dart` (collapsible with category icon/color map + count badge).

5. **Mirror Provider** (`tool_mirror_provider.dart`): ToolMirrorNotifier with subscribe/unsubscribe/captureNow/onScreenshotNotification. Base64 decode via `compute()` in background isolate. RpcSender callback pattern for testability.

6. **Filtered Activity Provider** (`filtered_activity_provider.dart`): activityFilterProvider (StateProvider<ActivityFilter>) + filteredActivityProvider (derived Provider applying filter to shared activity list).

7. **Activity Feed Widgets**: `activity_filter_bar.dart` (horizontal FilterChip bar — category chips with icons + status chips + "Clear all"), `activity_list.dart` (ActivityListTab with empty state), `activity_detail_sheet.dart` (modal bottom sheet with status badge + metadata).

8. **Mirror View Widget** (`mirror_view.dart`): MirrorView with InteractiveViewer (0.5x-4x zoom), _MirrorStatusBar (live/paused dot, last updated, capture button), _MirrorPlaceholder (error/empty states).

9. **Tools Screen + Router**: `tools_screen.dart` (ConsumerStatefulWidget with TabController, 3 tabs: Mirror/Activity/Browse, _BrowseTab with shimmer loading + RefreshIndicator + category grouping). Updated `app_router.dart` — added 6th nav tab "Tools" at index 4, shifted Settings to index 5.

10. **Backend Mirror Handlers** (`gateway/mirror_handlers.py`): handle_mirror_subscribe/unsubscribe/capture RPC methods + is_mirror_active/is_capture_in_progress/capture_and_send/remove_subscriber helpers. Uses @rpc_method decorator.

11. **Backend Executor Integration**: Added `is_mirror_active`/`is_capture_in_progress`/`capture_and_send` imports to executor.py. After `_audit()` broadcasts tool.activity, triggers `asyncio.create_task(capture_and_send(conn_id))` if mirror active. Added `remove_subscriber(connection_id)` in websocket.py `disconnect()`.

12. **Verification**: 530 tests passing, flutter analyze clean (0 issues), CLAUDE.md updated.

### Architecture decisions to preserve:
- **Shared activity state**: ToolActivityNotifier in `shared/providers/` — consumed by both security (compact feed) and tools (filterable full feed)
- **200-entry buffer** for activity feed (vs old 50 in ApprovalNotifier)
- **Mirror subscribe/unsubscribe pattern**: Event-driven screenshots via `tool.mirror.frame` notifications + manual `tool.mirror.capture` RPC
- **compute() for base64 decode**: Background isolate to prevent UI jank on large screenshots
- **RpcSender callback**: ToolMirrorNotifier takes `sendRpc` callback for testability without real WebSocket
- **6th nav tab**: Tools at index 4, Settings shifted to index 5
- **TabController lifecycle**: subscribe on Mirror tab focus, no ref.read in dispose (causes StateError)
- **Background capture**: `asyncio.create_task()` with `is_capture_in_progress` guard — non-blocking, single-flight
- **Mirror cleanup**: `remove_subscriber()` called in both websocket disconnect and manual unsubscribe

### Module structure (new files):
```
app/lib/
├── features/tools/
│   ├── models/tool_models.dart           # ToolCategory, ToolManifestEntry, MirrorState, ActivityFilter
│   ├── providers/
│   │   ├── tool_catalog_provider.dart    # FutureProvider for tool.list RPC
│   │   ├── tool_mirror_provider.dart     # ToolMirrorNotifier (subscribe/capture/decode)
│   │   └── filtered_activity_provider.dart # Filter state + derived filtered list
│   ├── screens/tools_screen.dart         # TabBar host (Mirror/Activity/Browse)
│   └── widgets/
│       ├── mirror_view.dart              # InteractiveViewer + capture button
│       ├── activity_list.dart            # Filtered activity feed tab
│       ├── activity_filter_bar.dart      # Category + status filter chips
│       ├── activity_detail_sheet.dart    # Modal bottom sheet for entry details
│       ├── tool_card.dart                # Single tool with tier badge + lock icon
│       └── tool_category_section.dart    # Collapsible category group
├── shared/providers/
│   └── tool_activity_provider.dart       # Shared 200-entry activity buffer
backend/nobla/gateway/
└── mirror_handlers.py                    # Mirror subscribe/unsubscribe/capture RPC
```

### Modified files:
- `approval_models.dart` — Added `ToolCategory? category` field to ActivityEntry
- `approval_provider.dart` — Removed activity management (delegated to shared provider)
- `activity_feed.dart` — Switched from injected provider to shared toolActivityProvider
- `notification_provider.dart` — Added tool.activity + tool.mirror.frame dispatch
- `app_router.dart` — 6th nav tab (Tools) at index 4, Settings at index 5
- `executor.py` — Mirror capture trigger after audit + mirror imports
- `websocket.py` — Mirror cleanup in disconnect()

### What to do next — choose one:

**Option A: Phase 6 v2 enhancements (async parallel, delegation, capability discovery)**
- Make orchestrator execute tasks in parallel via A2A protocol + wait_for_result
- Implement depth-limited delegation in _handle_delegation
- Implement query_capabilities request/response pattern
- Add real MCP transport (stdio/SSE) to MCPClientManager

**Option B: Phase 5 — Remaining channel adapters (WhatsApp, Slack, Signal, Teams, etc.)**
- 15 platform adapters following the Telegram/Discord pattern

**Option C: Phase 6 — Webhooks & Workflows**
- Receive and process external events
- Multi-step workflow builder in natural language

**Option D: Phase 7 — Full Feature Set**
- Media, finance, health, social, smart home tools

### Test commands:
```bash
# Run all Flutter tests (85 tests)
cd app && flutter test

# Run all backend tests (445 tests)
cd backend && pytest tests/test_telegram.py tests/test_discord_adapter.py tests/test_scheduler.py tests/test_channels.py tests/test_event_bus.py tests/test_skills.py tests/test_agents.py tests/test_agents_advanced.py tests/gateway/test_mirror_handlers.py tests/tools/test_executor_mirror.py -v

# Run flutter analyze
cd app && flutter analyze

# Verify line counts
wc -l app/lib/features/tools/**/*.dart app/lib/shared/providers/*.dart backend/nobla/gateway/mirror_handlers.py
```

### Key files to read first:
- `CLAUDE.md` — Full project guide with all phase status
- `app/lib/features/tools/screens/tools_screen.dart` — TabBar host entry point
- `app/lib/features/tools/providers/tool_mirror_provider.dart` — Mirror state management
- `app/lib/shared/providers/tool_activity_provider.dart` — Shared activity buffer
- `app/lib/core/providers/notification_provider.dart` — WebSocket notification dispatch
- `app/lib/core/routing/app_router.dart` — Navigation with 6 tabs
- `backend/nobla/gateway/mirror_handlers.py` — Mirror RPC handlers
- `backend/nobla/tools/executor.py` — Tool execution pipeline + mirror trigger
- `backend/nobla/gateway/websocket.py` — Connection lifecycle + mirror cleanup

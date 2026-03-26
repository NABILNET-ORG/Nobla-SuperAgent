# Phase 4E: Flutter Tool UI — Design Specification

**Date:** 2026-03-25
**Status:** Approved
**Phase:** 4E
**Scope:** Screen mirror, activity feed, tool browser — Flutter frontend for the tool platform (Phases 4A-4D)

---

## 1. Overview

Phase 4E builds the Flutter UI counterpart to the backend tool platform. It gives users visibility into what their agent is doing (mirror), what it has done (activity feed), and what it can do (tool browser).

Three components, one new navigation tab:

| Component | Purpose |
|-----------|---------|
| Screen Mirror | Real-time view of agent screenshots, event-driven + manual capture |
| Activity Feed | Filterable log of tool executions with detail drill-down |
| Tool Browser | Read-only catalog of available tools grouped by category |

## 2. Navigation

**New 6th tab** in the bottom NavigationBar.

- Label: "Tools"
- Icon: `build_outlined` / `build` (selected)
- Position: 5th slot (between Persona and Settings)
- The Tools tab contains a top `TabBar` with 3 sub-views: Mirror | Activity | Browse

**Rationale:** Tools are the core value proposition of Phases 4A-4D. They deserve first-class navigation, not burial under Dashboard or Security. Material 3 NavigationBar handles 6 items well on mobile.

## 3. Feature Module Structure

```
app/lib/features/tools/
├── screens/
│   └── tools_screen.dart              # TabBar host (Mirror | Activity | Browse)
├── providers/
│   ├── tool_mirror_provider.dart      # Mirror subscription + screenshot stream
│   ├── filtered_activity_provider.dart # Filtering logic on shared activity state
│   └── tool_catalog_provider.dart     # Tool manifest from tool.list RPC
├── widgets/
│   ├── mirror_view.dart               # Screenshot + pinch-to-zoom + capture button
│   ├── activity_list.dart             # Filtered activity entries list
│   ├── activity_detail_sheet.dart     # Tap-to-expand bottom sheet with full params
│   ├── activity_filter_bar.dart       # Filter chips (category, status)
│   ├── tool_category_section.dart     # Category header + tool cards
│   └── tool_card.dart                 # Individual tool card
└── models/
    └── tool_models.dart               # ToolManifestEntry, MirrorState, ActivityFilter, ToolCategory

app/lib/shared/providers/
    └── tool_activity_provider.dart    # Shared activity state (extracted from security)
```

**11 new files** in this module, plus 1 shared provider extraction (see Section 9 for full count including modifications).

**11 new files.** All well under the 750-line limit. Follows the same directory pattern as existing features (security, persona, chat).

## 4. State Management (Providers)

### 4.1 Shared Activity Provider

**File:** `app/lib/shared/providers/tool_activity_provider.dart`

```
ToolActivityNotifier (StateNotifier<List<ActivityEntry>>)
```

- Registered with `NotificationDispatcher` for `tool.activity` events (follows existing event flow pattern)
- Maintains a buffer of up to 200 entries (upgraded from security feature's 50)
- Methods: `addEntry()`, `clear()`
- Consumed by both the security feature (compact summary) and tools feature (filtered full view)

**Extraction:** The existing `approval_provider.dart` currently manages both approval queue AND activity entries. After extraction, it delegates activity tracking to this shared provider and focuses solely on approval queue management.

### 4.2 Filtered Activity Provider

**File:** `tools/providers/filtered_activity_provider.dart`

```
ActivityFilter { categories: Set<ToolCategory>?, statuses: Set<ActivityStatus>? }

activityFilterProvider (StateProvider<ActivityFilter>)
  - Holds current filter state, toggled by filter chips

filteredActivityProvider (derived provider)
  - Reads from shared ToolActivityNotifier
  - Applies current ActivityFilter
  - Returns filtered List<ActivityEntry>
```

### 4.3 Mirror Provider

**File:** `tools/providers/tool_mirror_provider.dart`

```
MirrorState { isSubscribed: bool, latestScreenshot: Uint8List?, lastUpdated: DateTime?, isCapturing: bool }

ToolMirrorNotifier (StateNotifier<MirrorState>)
```

Two distinct input paths:

- **Event-driven:** Receives `tool.mirror.frame` notifications → `compute()` decode in background isolate → update state
- **Manual capture:** `captureNow()` → sets `isCapturing: true` → awaits `tool.mirror.capture` RPC response → `compute()` decode → update state

Key behaviors:
- `subscribe()` / `unsubscribe()` send RPC calls to toggle event-driven mode
- Auto-subscribes when mirror tab is visible, unsubscribes when user swipes away (tied to `TabController` listener)
- Base64 decoding always uses `compute()` to avoid UI thread jank (screenshots are 1-3MB encoded)
- Only ONE screenshot in memory at a time — previous is discarded
- Also unsubscribes on `dispose()` as safety net

### 4.4 Tool Catalog Provider

**File:** `tools/providers/tool_catalog_provider.dart`

```
toolCatalogProvider (FutureProvider<List<ToolManifestEntry>>)
```

- Calls `tool.list` RPC on first load
- Refresh via `ref.invalidate(toolCatalogProvider)` on pull-to-refresh
- Grouping by category done in the widget layer, not the provider
- No real-time updates needed — tool list is static during a session

## 5. Screen Mirror Component

**Widget:** `mirror_view.dart`

### Layout (top to bottom)

1. **Status bar** — Small row: green/red dot for subscription status, "Last updated: 3s ago" text, camera icon button ("Capture") on the right
2. **Screenshot area** — `InteractiveViewer` wrapping `Image.memory()` for pinch-to-zoom and pan. Takes all remaining space. `BoxFit.contain` to scale while maintaining aspect ratio.
3. **Placeholder** (when no screenshot available) — Centered muted icon + "No screenshots yet — activity will appear here when tools execute"

### Behaviors

- No loading spinner during event-driven updates — screenshots swap in silently
- Brief `CircularProgressIndicator` overlay only during manual "Capture Now" (while `isCapturing: true`)
- WebSocket disconnect: status dot goes red, capture button disabled, "Reconnecting..." message
- Large screenshots: `compute()` decode + `Image.memory` with `cacheWidth` to limit memory
- Rapid updates: latest screenshot wins, no animation, no queue

### Subscription Lifecycle

- `tools_screen.dart` has a `TabController` listener
- Tab index 0 (Mirror) becomes active → `subscribe()`
- Tab index changes away from 0 → `unsubscribe()`
- `dispose()` → `unsubscribe()` as safety net
- Screenshots only flow over WebSocket when user is looking at the mirror tab

## 6. Activity Feed Component

### 6.1 Filter Bar

**Widget:** `activity_filter_bar.dart`

- Horizontal scrollable row of `FilterChip` widgets
- **Category chips** (outlined style): Only categories that have entries appear — no dead chips
- **16px gap** separating groups
- **Status chips** (tonal style): Success, Failed, Denied, Pending (`ActivityStatus` enum)
- **"Clear all"** text button appears at end of row only when any filter is active
- Tapping a chip toggles it in `activityFilterProvider`

### 6.2 Activity List

**Widget:** `activity_list.dart`

- `ListView.builder` consuming `filteredActivityProvider`
- Each entry row:
  - **Leading:** Category icon in fixed color per category (SSH always blue, Vision always purple, Code always teal, etc.)
  - **Status indicator:** Small colored dot on the row (green/red/orange/grey) — separate from category icon
  - **Title:** Tool name (e.g., "ssh.exec")
  - **Subtitle:** Description truncated to one line
  - **Trailing:** Execution time (e.g., "245ms") + relative timestamp ("2m ago")
- Tap a row → opens `activity_detail_sheet.dart`
- Empty states: "No activity yet" / "No matches for current filters"
- All 200 entries in memory, filtered client-side. `ListView.builder` handles virtualization.

### 6.3 Activity Detail Sheet

**Widget:** `activity_detail_sheet.dart`

- Modal bottom sheet (follows existing `approval_sheet.dart` pattern)
- Contents:
  - Tool name chip with category color
  - Status badge with color (success/failed/denied)
  - Full description (unwrapped)
  - Execution time
  - Absolute timestamp ("Mar 25, 2026 at 2:30:14 PM")
  - Expandable "Parameters" section with formatted JSON (reuses pattern from approval_sheet.dart)
- No screenshot reference — screenshots are not stored per entry (memory concern: 200 entries x 1-5MB = non-starter on mobile)
- Dismiss by swiping down or tapping outside

## 7. Tool Browser Component

### 7.1 Category Section

**Widget:** `tool_category_section.dart`

- Header row: category icon (fixed color) + category name + tool count badge
- Below header: list of `ToolCard` widgets
- Categories sorted: Vision, Input, File System, App Control, Code, Git, SSH, Clipboard, Search
- Expand/collapse behavior: if more than 3 categories have tools, collapsed by default (tap header to expand). If 3 or fewer, all expanded.

### 7.2 Tool Card

**Widget:** `tool_card.dart`

- `Card` widget:
  - **Title:** Tool name (e.g., "ssh.connect")
  - **Subtitle:** Description from manifest
  - **Trailing badges:**
    - Tier chip: SAFE (green) / STANDARD (blue) / ELEVATED (orange) / ADMIN (red)
    - Lock icon if `requires_approval` is true
- Read-only. No tap action, no run button, no detail page.
- Compact: 4-5 tools visible on screen without scrolling

### 7.3 Browse Tab Layout

- `RefreshIndicator` wrapping `ListView` of `ToolCategorySection` widgets
- Pull-to-refresh calls `ref.invalidate(toolCatalogProvider)`
- Loading: shimmer placeholders (project already uses `shimmer` package)
- Error: "Couldn't load tools" with retry button
- `FutureProvider.when()` handles loading/error/data states naturally

## 8. Backend Additions

Minimal backend scope — 1 new file, 2 modifications.

### 8.1 New: Mirror Handlers

**File:** `backend/nobla/gateway/mirror_handlers.py` (~70 lines)

```
_mirror_subscribers: set[str]         # connection_ids with active mirrors
_capture_in_progress: bool = False    # debounce guard

@rpc_method("tool.mirror.subscribe")
  → Adds connection_id to _mirror_subscribers
  → Returns {"status": "subscribed"}

@rpc_method("tool.mirror.unsubscribe")
  → Removes connection_id from _mirror_subscribers
  → Returns {"status": "unsubscribed"}

@rpc_method("tool.mirror.capture")
  → Calls screenshot.capture tool directly
  → Returns {"screenshot_b64": "...", "error": null}
  → On failure: {"screenshot_b64": null, "error": "Screenshot unavailable"}

is_mirror_active(connection_id) → bool
is_capture_in_progress() → bool
capture_and_send(connection_id) → background task
remove_subscriber(connection_id) → disconnect cleanup
```

### 8.2 Modified: Tool Executor

**File:** `backend/nobla/tools/executor.py` — `_audit()` method

After broadcasting `tool.activity`, spawn a background screenshot capture:

```python
# After existing _audit() broadcast:
if is_mirror_active(connection_id) and not is_capture_in_progress():
    asyncio.create_task(capture_and_send(connection_id))
```

- Screenshot capture runs as `asyncio.create_task()` — zero impact on tool execution latency
- Debounce: if a capture is already in flight, skip. Prevents wasted work during rapid tool execution.
- `capture_and_send()` sends a separate `tool.mirror.frame` notification (not embedded in `tool.activity`)

### 8.3 Modified: WebSocket Disconnect

**File:** `backend/nobla/gateway/websocket.py` — disconnect handler

```python
# In disconnect handler:
mirror_handlers.remove_subscriber(connection_id)
```

Prevents stale subscriber entries if Flutter app disconnects without unsubscribing.

### 8.4 WebSocket Protocol Summary

**New RPC methods:**

| Method | Direction | Purpose |
|--------|-----------|---------|
| `tool.mirror.subscribe` | Client → Server | Start receiving event-driven screenshots |
| `tool.mirror.unsubscribe` | Client → Server | Stop receiving screenshots |
| `tool.mirror.capture` | Client → Server | On-demand screenshot (request/response) |

**New notification:**

| Method | Direction | Payload |
|--------|-----------|---------|
| `tool.mirror.frame` | Server → Client | `{ screenshot_b64: string, timestamp: string }` |

**Existing (unchanged):**

| Method | Direction | Purpose |
|--------|-----------|---------|
| `tool.activity` | Server → Client | Tool execution metadata (lightweight, no screenshots) |
| `tool.list` | Client → Server | Get tool manifest for browser |
| `tool.approval_request` | Server → Client | Approval prompt |
| `tool.approval_response` | Client → Server | User approval/denial |

### 8.5 Graceful Degradation

- If Phase 4A vision tools are unavailable (headless server, missing dependencies):
  - `tool.mirror.capture` returns `{"screenshot_b64": null, "error": "Screenshot unavailable"}`
  - Background capture task silently skips — no `tool.mirror.frame` sent
  - Flutter shows "Screenshots unavailable on this server" placeholder

## 9. Files Changed Summary

| Type | Count | Files |
|------|-------|-------|
| New Flutter | 11 | tools_screen, mirror_view, activity_list, activity_filter_bar, activity_detail_sheet, tool_category_section, tool_card, tool_models, filtered_activity_provider, tool_mirror_provider, tool_catalog_provider |
| New Shared | 1 | shared/providers/tool_activity_provider.dart |
| New Backend | 1 | gateway/mirror_handlers.py |
| Modified Flutter | 5 | app_router.dart, notification_provider.dart, approval_provider.dart, approval_models.dart, security/activity_feed.dart |
| Modified Backend | 2 | executor.py, websocket.py |
| **Total** | **20** | 13 new + 7 modified |

## 10. Models

**New in `tool_models.dart`:**

```dart
enum ToolCategory { vision, input, fileSystem, appControl, code, git, ssh, clipboard, search }

class ToolManifestEntry {
  final String name;
  final String description;
  final ToolCategory category;
  final String tier;          // SAFE, STANDARD, ELEVATED, ADMIN
  final bool requiresApproval;
}

class MirrorState {
  final bool isSubscribed;
  final Uint8List? latestScreenshot;
  final DateTime? lastUpdated;
  final bool isCapturing;
}

class ActivityFilter {
  final Set<ToolCategory>? categories;
  final Set<ActivityStatus>? statuses;
}
```

**Modified in `security/models/approval_models.dart`:** `ActivityEntry` gains a new `ToolCategory? category` field, populated from the backend `tool.activity` event's `category` field. This enables category-based filtering in the activity feed and category icon rendering. `ActivityStatus` also already lives here — both are imported by `tool_models.dart`, not re-declared.

## 11. Design Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Navigation | New 6th tab | Tools are core value — deserve first-class status |
| Mirror update strategy | Hybrid (event-driven + manual) | Efficient bandwidth, full user control |
| Activity feed level | Filterable with detail drill-down | Justifies dedicated tab without backend persistence scope creep |
| Tool browser interaction | Read-only catalog | Tools invoked by agent via chat, not manually by users |
| Backend scope | Minimal (mirror handlers only) | UI phase — avoid touching all tool subclasses |
| Mirror notification | Separate `tool.mirror.frame` | Keep `tool.activity` lightweight for all clients |
| Screenshot in activity entries | Not stored | 200 entries x 1-5MB = non-starter on mobile |
| Screenshot decode | `compute()` isolate | Prevent UI thread jank from 1-3MB base64 decode |
| Mirror capture in executor | Background `asyncio.create_task` | Zero impact on tool execution latency |
| Rapid captures | Debounce with `_capture_in_progress` flag | Prevent wasted work during burst activity |
| Activity state | Shared provider extraction | Avoid duplicate state between security and tools features |
| Category vs status visuals | Separate (fixed icon color + status dot) | Two visual dimensions stay distinct |

## 12. Out of Scope

- Tool execution from the browser UI (parameter forms, "Run" button)
- Tool favorites/pinning
- Persisted activity log (server-side database, pagination)
- SFTP progress tracking via WebSocket
- Full-screen immersive mirror mode
- Screenshot history (only latest held in memory)
- Tool manifest enrichment (parameter schemas, usage examples)

These can be added in future iterations without architectural changes.

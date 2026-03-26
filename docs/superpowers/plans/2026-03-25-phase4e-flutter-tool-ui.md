# Phase 4E: Flutter Tool UI — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new "Tools" tab in the Flutter app with screen mirror, filterable activity feed, and read-only tool browser — plus minimal backend mirror handlers.

**Architecture:** New `features/tools/` module with 3 TabBar sub-views consuming WebSocket notifications via Riverpod providers. Shared activity state extracted from security feature. Backend adds mirror subscription RPC handlers and screenshot capture in executor's audit path.

**Tech Stack:** Flutter 3.x, Riverpod (StateNotifier), GoRouter, WebSocket (JSON-RPC 2.0), Python/FastAPI backend

**Spec:** `docs/superpowers/specs/2026-03-25-phase4e-flutter-tool-ui-design.md`

---

## File Map

### New Files (13)

| File | Responsibility |
|------|---------------|
| `app/lib/features/tools/models/tool_models.dart` | ToolCategory enum, ToolManifestEntry, MirrorState, ActivityFilter |
| `app/lib/shared/providers/tool_activity_provider.dart` | Shared activity state (200 entries), registered with NotificationDispatcher |
| `app/lib/features/tools/providers/filtered_activity_provider.dart` | ActivityFilter state + derived filtered list |
| `app/lib/features/tools/providers/tool_mirror_provider.dart` | Mirror subscription, screenshot decode via compute() |
| `app/lib/features/tools/providers/tool_catalog_provider.dart` | FutureProvider calling tool.list RPC |
| `app/lib/features/tools/screens/tools_screen.dart` | TabBar host (Mirror / Activity / Browse) |
| `app/lib/features/tools/widgets/mirror_view.dart` | InteractiveViewer screenshot display + capture button |
| `app/lib/features/tools/widgets/activity_list.dart` | ListView.builder with filtered entries |
| `app/lib/features/tools/widgets/activity_filter_bar.dart` | Filter chips (category + status) |
| `app/lib/features/tools/widgets/activity_detail_sheet.dart` | Modal bottom sheet with full entry details |
| `app/lib/features/tools/widgets/tool_category_section.dart` | Collapsible category group with header |
| `app/lib/features/tools/widgets/tool_card.dart` | Single tool card with tier badge + approval icon |
| `backend/nobla/gateway/mirror_handlers.py` | Mirror subscribe/unsubscribe/capture RPC + background capture |

### Modified Files (7)

| File | Change |
|------|--------|
| `app/lib/features/security/models/approval_models.dart` | Add `ToolCategory? category` field to ActivityEntry |
| `app/lib/shared/providers/tool_activity_provider.dart` | (new — extracted from approval_provider) |
| `app/lib/features/security/providers/approval_provider.dart` | Remove activity management, delegate to shared provider |
| `app/lib/features/security/widgets/activity_feed.dart` | Switch to shared tool_activity_provider |
| `app/lib/core/providers/notification_provider.dart` | Add tool.activity + tool.mirror.frame dispatch |
| `app/lib/core/routing/app_router.dart` | Add /home/tools route + 6th nav tab |
| `backend/nobla/tools/executor.py` | Add mirror screenshot capture in _audit() |
| `backend/nobla/gateway/websocket.py:89-92` | Add mirror cleanup in disconnect() |

---

## Task 1: Models — ToolCategory enum and ActivityEntry category field

**Files:**
- Create: `app/lib/features/tools/models/tool_models.dart`
- Modify: `app/lib/features/security/models/approval_models.dart`
- Test: `app/test/features/tools/models/tool_models_test.dart`

- [ ] **Step 1: Write tests for ToolCategory and updated ActivityEntry**

```dart
// app/test/features/tools/models/tool_models_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';

void main() {
  group('ToolCategory', () {
    test('has all 9 categories', () {
      expect(ToolCategory.values.length, 9);
      expect(ToolCategory.values, contains(ToolCategory.ssh));
      expect(ToolCategory.values, contains(ToolCategory.vision));
      expect(ToolCategory.values, contains(ToolCategory.code));
    });

    test('fromString parses backend category strings', () {
      expect(ToolCategory.fromString('ssh'), ToolCategory.ssh);
      expect(ToolCategory.fromString('vision'), ToolCategory.vision);
      expect(ToolCategory.fromString('file_system'), ToolCategory.fileSystem);
      expect(ToolCategory.fromString('app_control'), ToolCategory.appControl);
      expect(ToolCategory.fromString('unknown'), isNull);
    });
  });

  group('ToolManifestEntry', () {
    test('fromJson parses backend manifest', () {
      final entry = ToolManifestEntry.fromJson({
        'name': 'ssh.connect',
        'description': 'SSH connection management',
        'category': 'ssh',
        'tier': 4,
        'requires_approval': true,
      });
      expect(entry.name, 'ssh.connect');
      expect(entry.category, ToolCategory.ssh);
      expect(entry.tier, 4);
      expect(entry.requiresApproval, true);
    });
  });

  group('ActivityEntry with category', () {
    test('fromJson parses category field', () {
      final entry = ActivityEntry.fromJson({
        'tool_name': 'ssh.exec',
        'action': 'execute',
        'description': 'Run ls on server',
        'status': 'success',
        'category': 'ssh',
        'execution_time_ms': 245,
        'timestamp': '2026-03-25T14:30:00Z',
      });
      expect(entry.category, ToolCategory.ssh);
    });

    test('fromJson handles missing category gracefully', () {
      final entry = ActivityEntry.fromJson({
        'tool_name': 'ssh.exec',
        'status': 'success',
        'timestamp': '2026-03-25T14:30:00Z',
      });
      expect(entry.category, isNull);
    });
  });

  group('ActivityFilter', () {
    test('empty filter matches everything', () {
      final filter = ActivityFilter();
      expect(filter.categories, isNull);
      expect(filter.statuses, isNull);
    });

    test('matches checks category and status', () {
      final filter = ActivityFilter(
        categories: {ToolCategory.ssh},
        statuses: {ActivityStatus.success},
      );
      final entry = ActivityEntry(
        toolName: 'ssh.exec',
        action: 'execute',
        description: 'test',
        status: ActivityStatus.success,
        category: ToolCategory.ssh,
        timestamp: DateTime.now(),
      );
      expect(filter.matches(entry), true);
    });

    test('matches rejects wrong category', () {
      final filter = ActivityFilter(categories: {ToolCategory.code});
      final entry = ActivityEntry(
        toolName: 'ssh.exec',
        action: '',
        description: '',
        status: ActivityStatus.success,
        category: ToolCategory.ssh,
        timestamp: DateTime.now(),
      );
      expect(filter.matches(entry), false);
    });
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app && flutter test test/features/tools/models/tool_models_test.dart`
Expected: FAIL — files don't exist yet

- [ ] **Step 3: Create tool_models.dart**

```dart
// app/lib/features/tools/models/tool_models.dart
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';

/// Tool categories matching backend ToolCategory enum.
enum ToolCategory {
  vision,
  input,
  fileSystem,
  appControl,
  code,
  git,
  ssh,
  clipboard,
  search;

  /// Parse a backend category string like "file_system" into enum value.
  static ToolCategory? fromString(String? s) => switch (s) {
        'vision' => ToolCategory.vision,
        'input' => ToolCategory.input,
        'file_system' => ToolCategory.fileSystem,
        'app_control' => ToolCategory.appControl,
        'code' => ToolCategory.code,
        'git' => ToolCategory.git,
        'ssh' => ToolCategory.ssh,
        'clipboard' => ToolCategory.clipboard,
        'search' => ToolCategory.search,
        _ => null,
      };

  /// Human-readable label for display.
  String get label => switch (this) {
        ToolCategory.vision => 'Vision',
        ToolCategory.input => 'Input',
        ToolCategory.fileSystem => 'File System',
        ToolCategory.appControl => 'App Control',
        ToolCategory.code => 'Code',
        ToolCategory.git => 'Git',
        ToolCategory.ssh => 'SSH',
        ToolCategory.clipboard => 'Clipboard',
        ToolCategory.search => 'Search',
      };
}

/// A tool entry from the backend manifest (tool.list RPC).
@immutable
class ToolManifestEntry {
  final String name;
  final String description;
  final ToolCategory? category;
  final int tier;
  final bool requiresApproval;

  const ToolManifestEntry({
    required this.name,
    required this.description,
    this.category,
    required this.tier,
    required this.requiresApproval,
  });

  factory ToolManifestEntry.fromJson(Map<String, dynamic> json) {
    return ToolManifestEntry(
      name: json['name'] as String,
      description: json['description'] as String? ?? '',
      category: ToolCategory.fromString(json['category'] as String?),
      tier: json['tier'] as int? ?? 1,
      requiresApproval: json['requires_approval'] as bool? ?? false,
    );
  }
}

/// State for the screen mirror.
@immutable
class MirrorState {
  final bool isSubscribed;
  final Uint8List? latestScreenshot;
  final DateTime? lastUpdated;
  final bool isCapturing;
  final String? error;

  const MirrorState({
    this.isSubscribed = false,
    this.latestScreenshot,
    this.lastUpdated,
    this.isCapturing = false,
    this.error,
  });

  MirrorState copyWith({
    bool? isSubscribed,
    Uint8List? latestScreenshot,
    DateTime? lastUpdated,
    bool? isCapturing,
    String? error,
    bool clearScreenshot = false,
    bool clearError = false,
  }) {
    return MirrorState(
      isSubscribed: isSubscribed ?? this.isSubscribed,
      latestScreenshot:
          clearScreenshot ? null : (latestScreenshot ?? this.latestScreenshot),
      lastUpdated: lastUpdated ?? this.lastUpdated,
      isCapturing: isCapturing ?? this.isCapturing,
      error: clearError ? null : (error ?? this.error),
    );
  }
}

/// Filter state for the activity feed.
@immutable
class ActivityFilter {
  final Set<ToolCategory>? categories;
  final Set<ActivityStatus>? statuses;

  const ActivityFilter({this.categories, this.statuses});

  /// Returns true if [entry] passes this filter.
  bool matches(ActivityEntry entry) {
    if (categories != null &&
        categories!.isNotEmpty &&
        (entry.category == null || !categories!.contains(entry.category))) {
      return false;
    }
    if (statuses != null &&
        statuses!.isNotEmpty &&
        !statuses!.contains(entry.status)) {
      return false;
    }
    return true;
  }

  ActivityFilter copyWith({
    Set<ToolCategory>? categories,
    Set<ActivityStatus>? statuses,
    bool clearCategories = false,
    bool clearStatuses = false,
  }) {
    return ActivityFilter(
      categories: clearCategories ? null : (categories ?? this.categories),
      statuses: clearStatuses ? null : (statuses ?? this.statuses),
    );
  }

  /// True if any filter is active.
  bool get isActive =>
      (categories != null && categories!.isNotEmpty) ||
      (statuses != null && statuses!.isNotEmpty);
}
```

- [ ] **Step 4: Add category field to ActivityEntry**

In `app/lib/features/security/models/approval_models.dart`, add the import and field:

```dart
// Add at top of file:
import 'package:nobla_agent/features/tools/models/tool_models.dart';

// Add to ActivityEntry class — new field:
  final ToolCategory? category;

// Update constructor:
  const ActivityEntry({
    required this.toolName,
    required this.action,
    required this.description,
    required this.status,
    this.executionTimeMs,
    this.category,
    required this.timestamp,
  });

// Update fromJson:
  factory ActivityEntry.fromJson(Map<String, dynamic> json) {
    return ActivityEntry(
      toolName: json['tool_name'] as String,
      action: json['action'] as String? ?? '',
      description: json['description'] as String? ?? '',
      status: _parseStatus(json['status'] as String? ?? 'success'),
      category: ToolCategory.fromString(json['category'] as String?),
      executionTimeMs: json['execution_time_ms'] as int?,
      timestamp:
          DateTime.tryParse(json['timestamp'] as String? ?? '') ?? DateTime.now(),
    );
  }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd app && flutter test test/features/tools/models/tool_models_test.dart -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add app/lib/features/tools/models/tool_models.dart \
  app/lib/features/security/models/approval_models.dart \
  app/test/features/tools/models/tool_models_test.dart
git commit -m "feat(tools): add ToolCategory, ToolManifestEntry, MirrorState, ActivityFilter models"
```

---

## Task 2: Shared Activity Provider — extract from ApprovalNotifier

**Files:**
- Create: `app/lib/shared/providers/tool_activity_provider.dart`
- Modify: `app/lib/features/security/providers/approval_provider.dart`
- Modify: `app/lib/features/security/widgets/activity_feed.dart`
- Test: `app/test/shared/providers/tool_activity_provider_test.dart`

- [ ] **Step 1: Write tests for ToolActivityNotifier**

```dart
// app/test/shared/providers/tool_activity_provider_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/shared/providers/tool_activity_provider.dart';

void main() {
  late ToolActivityNotifier notifier;

  setUp(() {
    notifier = ToolActivityNotifier();
  });

  tearDown(() {
    notifier.dispose();
  });

  ActivityEntry _makeEntry({
    String toolName = 'test.tool',
    ActivityStatus status = ActivityStatus.success,
  }) {
    return ActivityEntry(
      toolName: toolName,
      action: 'test',
      description: 'test entry',
      status: status,
      timestamp: DateTime.now(),
    );
  }

  test('starts with empty list', () {
    expect(notifier.state, isEmpty);
  });

  test('addEntry prepends to list', () {
    final e1 = _makeEntry(toolName: 'first');
    final e2 = _makeEntry(toolName: 'second');
    notifier.addEntry(e1);
    notifier.addEntry(e2);
    expect(notifier.state.length, 2);
    expect(notifier.state.first.toolName, 'second');
  });

  test('enforces max 200 entries', () {
    for (var i = 0; i < 210; i++) {
      notifier.addEntry(_makeEntry(toolName: 'tool.$i'));
    }
    expect(notifier.state.length, 200);
    expect(notifier.state.first.toolName, 'tool.209');
  });

  test('clear removes all entries', () {
    notifier.addEntry(_makeEntry());
    notifier.addEntry(_makeEntry());
    notifier.clear();
    expect(notifier.state, isEmpty);
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app && flutter test test/shared/providers/tool_activity_provider_test.dart`
Expected: FAIL — file doesn't exist

- [ ] **Step 3: Create shared ToolActivityNotifier**

```dart
// app/lib/shared/providers/tool_activity_provider.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';

/// Maximum number of activity entries kept in memory.
const int maxActivityEntries = 200;

/// Shared notifier for tool activity events from the backend.
///
/// Both the security feature (compact feed) and tools feature
/// (filterable full feed) consume this provider.
class ToolActivityNotifier extends StateNotifier<List<ActivityEntry>> {
  ToolActivityNotifier() : super(const []);

  /// Prepend a new activity entry, enforcing the max buffer size.
  void addEntry(ActivityEntry entry) {
    final updated = [entry, ...state];
    if (updated.length > maxActivityEntries) {
      state = updated.sublist(0, maxActivityEntries);
    } else {
      state = updated;
    }
  }

  /// Remove all entries.
  void clear() => state = const [];
}

final toolActivityProvider =
    StateNotifierProvider<ToolActivityNotifier, List<ActivityEntry>>((ref) {
  return ToolActivityNotifier();
});
```

- [ ] **Step 4: Refactor ApprovalNotifier — remove activity management**

Replace the `ApprovalNotifier` and `ApprovalState` in `app/lib/features/security/providers/approval_provider.dart`:

```dart
import 'dart:async';
import 'dart:collection';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';

/// Immutable state exposed by [ApprovalNotifier].
class ApprovalState {
  final ApprovalRequest? current;
  final int remainingSeconds;

  const ApprovalState({
    this.current,
    this.remainingSeconds = 0,
  });

  ApprovalState copyWith({
    ApprovalRequest? current,
    int? remainingSeconds,
    bool clearCurrent = false,
  }) {
    return ApprovalState(
      current: clearCurrent ? null : (current ?? this.current),
      remainingSeconds: remainingSeconds ?? this.remainingSeconds,
    );
  }
}

/// Manages approval requests queue and countdown timer.
///
/// Activity feed is now managed by [ToolActivityNotifier] in shared providers.
class ApprovalNotifier extends StateNotifier<ApprovalState> {
  final void Function(Map<String, dynamic>) sendWebSocketMessage;
  final Queue<ApprovalRequest> _queue = Queue<ApprovalRequest>();
  Timer? _countdownTimer;

  ApprovalNotifier({required this.sendWebSocketMessage})
      : super(const ApprovalState());

  void onApprovalRequest(ApprovalRequest request) {
    if (state.current == null) {
      _showRequest(request);
    } else {
      _queue.add(request);
    }
  }

  void approve(String requestId) {
    if (state.current?.requestId != requestId) return;
    _respond(requestId, approved: true);
    _processNext();
  }

  void deny(String requestId) {
    if (state.current?.requestId != requestId) return;
    _respond(requestId, approved: false);
    _processNext();
  }

  void _showRequest(ApprovalRequest request) {
    _countdownTimer?.cancel();
    state = state.copyWith(
      current: request,
      remainingSeconds: request.timeoutSeconds,
      clearCurrent: false,
    );
    _startCountdown(request);
  }

  void _startCountdown(ApprovalRequest request) {
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      final next = state.remainingSeconds - 1;
      if (next <= 0) {
        deny(request.requestId);
      } else {
        state = state.copyWith(remainingSeconds: next);
      }
    });
  }

  void _respond(String requestId, {required bool approved}) {
    _countdownTimer?.cancel();
    sendWebSocketMessage({
      'jsonrpc': '2.0',
      'method': 'tool.approval_response',
      'params': {
        'request_id': requestId,
        'approved': approved,
      },
    });
  }

  void _processNext() {
    if (_queue.isNotEmpty) {
      _showRequest(_queue.removeFirst());
    } else {
      state = state.copyWith(clearCurrent: true, remainingSeconds: 0);
    }
  }

  @override
  void dispose() {
    _countdownTimer?.cancel();
    super.dispose();
  }
}
```

- [ ] **Step 5: Update ActivityFeed widget to use shared provider**

In `app/lib/features/security/widgets/activity_feed.dart`, change the provider reference:

```dart
// Replace the import:
import 'package:nobla_agent/shared/providers/tool_activity_provider.dart';

// Replace the class:
class ActivityFeed extends ConsumerWidget {
  const ActivityFeed({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final activities = ref.watch(toolActivityProvider);
    // ... rest stays the same, just remove the `provider` constructor param
    // and use toolActivityProvider directly
```

Remove the `provider` constructor parameter. The widget now reads from the global shared provider directly instead of being injected with a specific ApprovalNotifier instance.

- [ ] **Step 6: Run all existing tests to verify no regressions**

Run: `cd app && flutter test`
Expected: ALL PASS (existing security tests + new shared provider tests)

- [ ] **Step 7: Commit**

```bash
git add app/lib/shared/providers/tool_activity_provider.dart \
  app/lib/features/security/providers/approval_provider.dart \
  app/lib/features/security/widgets/activity_feed.dart \
  app/test/shared/providers/tool_activity_provider_test.dart
git commit -m "refactor(security): extract shared ToolActivityNotifier from ApprovalNotifier"
```

---

## Task 3: NotificationDispatcher — wire tool.activity and tool.mirror.frame

**Files:**
- Modify: `app/lib/core/providers/notification_provider.dart`
- Test: `app/test/core/providers/notification_provider_test.dart`

- [ ] **Step 1: Write tests for new dispatch cases**

```dart
// app/test/core/providers/notification_provider_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/shared/providers/tool_activity_provider.dart';

void main() {
  test('tool.activity notification adds entry to shared provider', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(toolActivityProvider.notifier);
    expect(container.read(toolActivityProvider), isEmpty);

    // Simulate what NotificationDispatcher does:
    final params = {
      'tool_name': 'ssh.exec',
      'category': 'ssh',
      'description': 'Execute ls',
      'status': 'success',
      'execution_time_ms': 100,
      'timestamp': '2026-03-25T14:30:00Z',
    };
    notifier.addEntry(ActivityEntry.fromJson(params));

    expect(container.read(toolActivityProvider).length, 1);
    expect(container.read(toolActivityProvider).first.toolName, 'ssh.exec');
  });
}
```

- [ ] **Step 2: Run tests to verify they pass** (this tests the provider directly, not the dispatcher wiring)

Run: `cd app && flutter test test/core/providers/notification_provider_test.dart -v`
Expected: PASS

- [ ] **Step 3: Add tool.activity and tool.mirror.frame dispatch**

In `app/lib/core/providers/notification_provider.dart`, add the new cases:

```dart
import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/shared/providers/tool_activity_provider.dart';

// ... existing KillSwitchNotifier, BudgetWarning, providers unchanged ...

class NotificationDispatcher {
  final WidgetRef _ref;
  StreamSubscription? _subscription;
  NotificationDispatcher(this._ref);

  void listen(JsonRpcClient rpc) {
    _subscription?.cancel();
    _subscription = rpc.notificationStream.listen(_dispatch);
  }

  void _dispatch(Map<String, dynamic> notification) {
    final method = notification['method'] as String?;
    final params = notification['params'] as Map<String, dynamic>? ?? {};
    switch (method) {
      case 'system.killed':
        _ref.read(killSwitchProvider.notifier).updateFromNotification(params);
      case 'system.budget_warning':
        _ref.read(budgetWarningProvider.notifier).state = BudgetWarning(
          period: params['period'] as String? ?? '',
          limit: (params['limit'] as num?)?.toDouble() ?? 0,
          spent: (params['spent'] as num?)?.toDouble() ?? 0,
        );
      case 'tool.activity':
        _ref
            .read(toolActivityProvider.notifier)
            .addEntry(ActivityEntry.fromJson(params));
      case 'tool.mirror.frame':
        _ref
            .read(toolMirrorProvider.notifier)
            .onScreenshotNotification(params);
    }
  }

  void dispose() {
    _subscription?.cancel();
  }
}
```

**Note:** The `tool.mirror.frame` case references `toolMirrorProvider` which will be created in Task 5. For now, add only the `tool.activity` case. The `tool.mirror.frame` case will be added in Task 5 after the mirror provider exists.

- [ ] **Step 4: Run tests**

Run: `cd app && flutter test`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add app/lib/core/providers/notification_provider.dart \
  app/test/core/providers/notification_provider_test.dart
git commit -m "feat(notifications): dispatch tool.activity events to shared activity provider"
```

---

## Task 4: Tool Catalog Provider + Tool Browser Widgets

**Files:**
- Create: `app/lib/features/tools/providers/tool_catalog_provider.dart`
- Create: `app/lib/features/tools/widgets/tool_card.dart`
- Create: `app/lib/features/tools/widgets/tool_category_section.dart`
- Test: `app/test/features/tools/providers/tool_catalog_provider_test.dart`
- Test: `app/test/features/tools/widgets/tool_card_test.dart`

- [ ] **Step 1: Write tests for catalog provider**

```dart
// app/test/features/tools/providers/tool_catalog_provider_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';

void main() {
  group('ToolManifestEntry.fromJson', () {
    test('parses a complete manifest list', () {
      final jsonList = [
        {
          'name': 'screenshot.capture',
          'description': 'Capture screenshot',
          'category': 'vision',
          'tier': 2,
          'requires_approval': false,
        },
        {
          'name': 'ssh.connect',
          'description': 'SSH connection management',
          'category': 'ssh',
          'tier': 4,
          'requires_approval': true,
        },
      ];
      final entries =
          jsonList.map((j) => ToolManifestEntry.fromJson(j)).toList();
      expect(entries.length, 2);
      expect(entries[0].category, ToolCategory.vision);
      expect(entries[1].requiresApproval, true);
    });

    test('groups by category correctly', () {
      final entries = [
        ToolManifestEntry(
            name: 'a', description: '', category: ToolCategory.ssh,
            tier: 1, requiresApproval: false),
        ToolManifestEntry(
            name: 'b', description: '', category: ToolCategory.ssh,
            tier: 1, requiresApproval: false),
        ToolManifestEntry(
            name: 'c', description: '', category: ToolCategory.code,
            tier: 1, requiresApproval: false),
      ];
      final grouped = <ToolCategory, List<ToolManifestEntry>>{};
      for (final e in entries) {
        if (e.category != null) {
          grouped.putIfAbsent(e.category!, () => []).add(e);
        }
      }
      expect(grouped[ToolCategory.ssh]!.length, 2);
      expect(grouped[ToolCategory.code]!.length, 1);
    });
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app && flutter test test/features/tools/providers/tool_catalog_provider_test.dart`
Expected: PASS (these test the model, which already exists from Task 1)

- [ ] **Step 3: Create tool_catalog_provider.dart**

```dart
// app/lib/features/tools/providers/tool_catalog_provider.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/main.dart' show jsonRpcProvider;

/// Fetches the tool manifest from the backend via tool.list RPC.
///
/// Refresh with `ref.invalidate(toolCatalogProvider)`.
final toolCatalogProvider =
    FutureProvider<List<ToolManifestEntry>>((ref) async {
  final rpc = ref.watch(jsonRpcProvider);
  final result = await rpc.call('tool.list', {});
  final tools = result['tools'] as List<dynamic>? ?? [];
  return tools
      .map((t) => ToolManifestEntry.fromJson(t as Map<String, dynamic>))
      .toList();
});
```

- [ ] **Step 4: Create tool_card.dart**

```dart
// app/lib/features/tools/widgets/tool_card.dart
import 'package:flutter/material.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';

/// Displays a single tool from the manifest.
class ToolCard extends StatelessWidget {
  final ToolManifestEntry tool;
  const ToolCard({super.key, required this.tool});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    tool.name,
                    style: theme.textTheme.bodyMedium
                        ?.copyWith(fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    tool.description,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            _TierBadge(tier: tool.tier),
            if (tool.requiresApproval) ...[
              const SizedBox(width: 6),
              Icon(Icons.lock_outline,
                  size: 16, color: theme.colorScheme.onSurfaceVariant),
            ],
          ],
        ),
      ),
    );
  }
}

class _TierBadge extends StatelessWidget {
  final int tier;
  const _TierBadge({required this.tier});

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (tier) {
      1 => ('SAFE', Colors.green),
      2 => ('STD', Colors.blue),
      3 => ('ELEV', Colors.orange),
      4 => ('ADMIN', Colors.red),
      _ => ('T$tier', Colors.grey),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w700,
          color: color,
        ),
      ),
    );
  }
}
```

- [ ] **Step 5: Create tool_category_section.dart**

```dart
// app/lib/features/tools/widgets/tool_category_section.dart
import 'package:flutter/material.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/features/tools/widgets/tool_card.dart';

/// Category icon and color mapping.
const _categoryStyles = <ToolCategory, (IconData, Color)>{
  ToolCategory.vision: (Icons.visibility, Colors.purple),
  ToolCategory.input: (Icons.mouse, Colors.indigo),
  ToolCategory.fileSystem: (Icons.folder, Colors.amber),
  ToolCategory.appControl: (Icons.apps, Colors.teal),
  ToolCategory.code: (Icons.code, Colors.cyan),
  ToolCategory.git: (Icons.merge_type, Colors.deepOrange),
  ToolCategory.ssh: (Icons.terminal, Colors.blue),
  ToolCategory.clipboard: (Icons.content_paste, Colors.pink),
  ToolCategory.search: (Icons.search, Colors.green),
};

/// Icon for a [ToolCategory], using consistent colors.
(IconData, Color) categoryStyle(ToolCategory cat) =>
    _categoryStyles[cat] ?? (Icons.build, Colors.grey);

/// Collapsible section showing tools in a single category.
class ToolCategorySection extends StatefulWidget {
  final ToolCategory category;
  final List<ToolManifestEntry> tools;
  final bool initiallyExpanded;

  const ToolCategorySection({
    super.key,
    required this.category,
    required this.tools,
    this.initiallyExpanded = true,
  });

  @override
  State<ToolCategorySection> createState() => _ToolCategorySectionState();
}

class _ToolCategorySectionState extends State<ToolCategorySection> {
  late bool _expanded;

  @override
  void initState() {
    super.initState();
    _expanded = widget.initiallyExpanded;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final (icon, color) = categoryStyle(widget.category);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: () => setState(() => _expanded = !_expanded),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              children: [
                Icon(icon, color: color, size: 20),
                const SizedBox(width: 8),
                Text(
                  widget.category.label,
                  style: theme.textTheme.titleSmall
                      ?.copyWith(fontWeight: FontWeight.w600),
                ),
                const SizedBox(width: 8),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(
                    '${widget.tools.length}',
                    style: theme.textTheme.labelSmall,
                  ),
                ),
                const Spacer(),
                Icon(
                  _expanded ? Icons.expand_less : Icons.expand_more,
                  size: 20,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ],
            ),
          ),
        ),
        if (_expanded)
          ...widget.tools.map((t) => ToolCard(tool: t)),
      ],
    );
  }
}
```

- [ ] **Step 6: Write widget test for ToolCard**

```dart
// app/test/features/tools/widgets/tool_card_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/features/tools/widgets/tool_card.dart';

void main() {
  testWidgets('ToolCard displays tool name and description', (tester) async {
    const tool = ToolManifestEntry(
      name: 'ssh.connect',
      description: 'SSH connection management',
      category: ToolCategory.ssh,
      tier: 4,
      requiresApproval: true,
    );
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: ToolCard(tool: tool))),
    );
    expect(find.text('ssh.connect'), findsOneWidget);
    expect(find.text('SSH connection management'), findsOneWidget);
    expect(find.text('ADMIN'), findsOneWidget);
    expect(find.byIcon(Icons.lock_outline), findsOneWidget);
  });

  testWidgets('ToolCard hides lock icon when no approval required',
      (tester) async {
    const tool = ToolManifestEntry(
      name: 'screenshot.capture',
      description: 'Capture screenshot',
      category: ToolCategory.vision,
      tier: 2,
      requiresApproval: false,
    );
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: ToolCard(tool: tool))),
    );
    expect(find.byIcon(Icons.lock_outline), findsNothing);
    expect(find.text('STD'), findsOneWidget);
  });
}
```

- [ ] **Step 7: Run tests**

Run: `cd app && flutter test test/features/tools/ -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add app/lib/features/tools/providers/tool_catalog_provider.dart \
  app/lib/features/tools/widgets/tool_card.dart \
  app/lib/features/tools/widgets/tool_category_section.dart \
  app/test/features/tools/providers/tool_catalog_provider_test.dart \
  app/test/features/tools/widgets/tool_card_test.dart
git commit -m "feat(tools): add tool catalog provider and browser widgets"
```

---

## Task 5: Mirror Provider — subscription, decode, capture

**Files:**
- Create: `app/lib/features/tools/providers/tool_mirror_provider.dart`
- Modify: `app/lib/core/providers/notification_provider.dart` (add tool.mirror.frame case)
- Test: `app/test/features/tools/providers/tool_mirror_provider_test.dart`

- [ ] **Step 1: Write tests for ToolMirrorNotifier**

```dart
// app/test/features/tools/providers/tool_mirror_provider_test.dart
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/features/tools/providers/tool_mirror_provider.dart';

void main() {
  late ToolMirrorNotifier notifier;

  setUp(() {
    notifier = ToolMirrorNotifier(
      sendRpc: (method, params) async => <String, dynamic>{},
    );
  });

  tearDown(() => notifier.dispose());

  test('starts unsubscribed with no screenshot', () {
    expect(notifier.state.isSubscribed, false);
    expect(notifier.state.latestScreenshot, isNull);
    expect(notifier.state.isCapturing, false);
  });

  test('subscribe sets isSubscribed true', () async {
    await notifier.subscribe();
    expect(notifier.state.isSubscribed, true);
  });

  test('unsubscribe sets isSubscribed false', () async {
    await notifier.subscribe();
    await notifier.unsubscribe();
    expect(notifier.state.isSubscribed, false);
  });

  test('onScreenshotNotification decodes base64 screenshot', () async {
    // Create a tiny 1x1 white PNG as base64
    final pngBytes = Uint8List.fromList([
      0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
    ]);
    final b64 = base64Encode(pngBytes);

    await notifier.onScreenshotNotification({
      'screenshot_b64': b64,
      'timestamp': '2026-03-25T14:30:00Z',
    });

    expect(notifier.state.latestScreenshot, isNotNull);
    expect(notifier.state.latestScreenshot!.length, pngBytes.length);
    expect(notifier.state.lastUpdated, isNotNull);
  });

  test('onScreenshotNotification ignores null screenshot', () async {
    await notifier.onScreenshotNotification({
      'screenshot_b64': null,
      'timestamp': '2026-03-25T14:30:00Z',
    });
    expect(notifier.state.latestScreenshot, isNull);
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app && flutter test test/features/tools/providers/tool_mirror_provider_test.dart`
Expected: FAIL — file doesn't exist

- [ ] **Step 3: Create ToolMirrorNotifier**

```dart
// app/lib/features/tools/providers/tool_mirror_provider.dart
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/main.dart' show jsonRpcProvider;

/// Callback type for sending RPC calls.
typedef RpcSender = Future<Map<String, dynamic>> Function(
    String method, Map<String, dynamic> params);

/// Decode base64 in a background isolate to avoid UI jank.
Uint8List _decodeBase64(String encoded) => base64Decode(encoded);

/// Manages mirror subscription state and screenshot display.
class ToolMirrorNotifier extends StateNotifier<MirrorState> {
  final RpcSender _sendRpc;

  ToolMirrorNotifier({required RpcSender sendRpc})
      : _sendRpc = sendRpc,
        super(const MirrorState());

  /// Subscribe to event-driven screenshots.
  Future<void> subscribe() async {
    if (state.isSubscribed) return;
    try {
      await _sendRpc('tool.mirror.subscribe', {});
      state = state.copyWith(isSubscribed: true, clearError: true);
    } catch (e) {
      state = state.copyWith(error: 'Failed to subscribe: $e');
    }
  }

  /// Unsubscribe from event-driven screenshots.
  Future<void> unsubscribe() async {
    if (!state.isSubscribed) return;
    try {
      await _sendRpc('tool.mirror.unsubscribe', {});
    } catch (_) {
      // Best effort — server may already have disconnected
    }
    state = state.copyWith(isSubscribed: false);
  }

  /// Manual capture — request-response pattern.
  Future<void> captureNow() async {
    if (state.isCapturing) return;
    state = state.copyWith(isCapturing: true, clearError: true);
    try {
      final result = await _sendRpc('tool.mirror.capture', {});
      final b64 = result['screenshot_b64'] as String?;
      final error = result['error'] as String?;
      if (b64 != null) {
        final bytes = await compute(_decodeBase64, b64);
        state = state.copyWith(
          latestScreenshot: bytes,
          lastUpdated: DateTime.now(),
          isCapturing: false,
        );
      } else {
        state = state.copyWith(
          isCapturing: false,
          error: error ?? 'No screenshot returned',
        );
      }
    } catch (e) {
      state = state.copyWith(isCapturing: false, error: 'Capture failed: $e');
    }
  }

  /// Handle event-driven screenshot notification from backend.
  Future<void> onScreenshotNotification(Map<String, dynamic> params) async {
    final b64 = params['screenshot_b64'] as String?;
    if (b64 == null) return;
    try {
      final bytes = await compute(_decodeBase64, b64);
      state = state.copyWith(
        latestScreenshot: bytes,
        lastUpdated: DateTime.now(),
      );
    } catch (_) {
      // Silently skip corrupt frames
    }
  }
}

final toolMirrorProvider =
    StateNotifierProvider<ToolMirrorNotifier, MirrorState>((ref) {
  final rpc = ref.watch(jsonRpcProvider);
  return ToolMirrorNotifier(
    sendRpc: (method, params) => rpc.call(method, params),
  );
});
```

- [ ] **Step 4: Add tool.mirror.frame dispatch to NotificationDispatcher**

In `app/lib/core/providers/notification_provider.dart`, add the import and case:

```dart
// Add import:
import 'package:nobla_agent/features/tools/providers/tool_mirror_provider.dart';

// Add case in _dispatch switch:
      case 'tool.mirror.frame':
        _ref
            .read(toolMirrorProvider.notifier)
            .onScreenshotNotification(params);
```

- [ ] **Step 5: Run tests**

Run: `cd app && flutter test test/features/tools/providers/tool_mirror_provider_test.dart -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add app/lib/features/tools/providers/tool_mirror_provider.dart \
  app/lib/core/providers/notification_provider.dart \
  app/test/features/tools/providers/tool_mirror_provider_test.dart
git commit -m "feat(tools): add mirror provider with subscribe/capture/decode"
```

---

## Task 6: Filtered Activity Provider

**Files:**
- Create: `app/lib/features/tools/providers/filtered_activity_provider.dart`
- Test: `app/test/features/tools/providers/filtered_activity_provider_test.dart`

- [ ] **Step 1: Write tests**

```dart
// app/test/features/tools/providers/filtered_activity_provider_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/features/tools/providers/filtered_activity_provider.dart';
import 'package:nobla_agent/shared/providers/tool_activity_provider.dart';

void main() {
  late ProviderContainer container;

  setUp(() {
    container = ProviderContainer();
  });

  tearDown(() => container.dispose());

  void addEntry(String toolName, ActivityStatus status, ToolCategory cat) {
    container.read(toolActivityProvider.notifier).addEntry(ActivityEntry(
          toolName: toolName,
          action: '',
          description: '',
          status: status,
          category: cat,
          timestamp: DateTime.now(),
        ));
  }

  test('no filter returns all entries', () {
    addEntry('ssh.exec', ActivityStatus.success, ToolCategory.ssh);
    addEntry('code.run', ActivityStatus.failed, ToolCategory.code);
    final filtered = container.read(filteredActivityProvider);
    expect(filtered.length, 2);
  });

  test('category filter narrows results', () {
    addEntry('ssh.exec', ActivityStatus.success, ToolCategory.ssh);
    addEntry('code.run', ActivityStatus.failed, ToolCategory.code);
    container.read(activityFilterProvider.notifier).state =
        ActivityFilter(categories: {ToolCategory.ssh});
    final filtered = container.read(filteredActivityProvider);
    expect(filtered.length, 1);
    expect(filtered.first.toolName, 'ssh.exec');
  });

  test('status filter narrows results', () {
    addEntry('ssh.exec', ActivityStatus.success, ToolCategory.ssh);
    addEntry('code.run', ActivityStatus.failed, ToolCategory.code);
    container.read(activityFilterProvider.notifier).state =
        ActivityFilter(statuses: {ActivityStatus.failed});
    final filtered = container.read(filteredActivityProvider);
    expect(filtered.length, 1);
    expect(filtered.first.toolName, 'code.run');
  });

  test('combined filter applies both', () {
    addEntry('ssh.exec', ActivityStatus.success, ToolCategory.ssh);
    addEntry('ssh.connect', ActivityStatus.failed, ToolCategory.ssh);
    addEntry('code.run', ActivityStatus.success, ToolCategory.code);
    container.read(activityFilterProvider.notifier).state = ActivityFilter(
      categories: {ToolCategory.ssh},
      statuses: {ActivityStatus.success},
    );
    final filtered = container.read(filteredActivityProvider);
    expect(filtered.length, 1);
    expect(filtered.first.toolName, 'ssh.exec');
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app && flutter test test/features/tools/providers/filtered_activity_provider_test.dart`
Expected: FAIL

- [ ] **Step 3: Create filtered_activity_provider.dart**

```dart
// app/lib/features/tools/providers/filtered_activity_provider.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/shared/providers/tool_activity_provider.dart';

/// Holds the current filter state for the activity feed.
final activityFilterProvider = StateProvider<ActivityFilter>((ref) {
  return const ActivityFilter();
});

/// Derived provider that applies the current filter to the shared activity list.
final filteredActivityProvider = Provider<List<ActivityEntry>>((ref) {
  final entries = ref.watch(toolActivityProvider);
  final filter = ref.watch(activityFilterProvider);
  if (!filter.isActive) return entries;
  return entries.where((e) => filter.matches(e)).toList();
});
```

- [ ] **Step 4: Run tests**

Run: `cd app && flutter test test/features/tools/providers/filtered_activity_provider_test.dart -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add app/lib/features/tools/providers/filtered_activity_provider.dart \
  app/test/features/tools/providers/filtered_activity_provider_test.dart
git commit -m "feat(tools): add filtered activity provider with category/status filtering"
```

---

## Task 7: Activity Feed Widgets — filter bar, list, detail sheet

**Files:**
- Create: `app/lib/features/tools/widgets/activity_filter_bar.dart`
- Create: `app/lib/features/tools/widgets/activity_list.dart`
- Create: `app/lib/features/tools/widgets/activity_detail_sheet.dart`
- Test: `app/test/features/tools/widgets/activity_list_test.dart`

- [ ] **Step 1: Create activity_filter_bar.dart**

```dart
// app/lib/features/tools/widgets/activity_filter_bar.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/features/tools/providers/filtered_activity_provider.dart';
import 'package:nobla_agent/features/tools/widgets/tool_category_section.dart';
import 'package:nobla_agent/shared/providers/tool_activity_provider.dart';

/// Horizontal filter chip bar for the activity feed.
class ActivityFilterBar extends ConsumerWidget {
  const ActivityFilterBar({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filter = ref.watch(activityFilterProvider);
    final entries = ref.watch(toolActivityProvider);

    // Only show categories that have entries.
    final activeCategories = <ToolCategory>{};
    for (final e in entries) {
      if (e.category != null) activeCategories.add(e.category!);
    }

    return SizedBox(
      height: 48,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        children: [
          // Category chips (outlined)
          for (final cat in ToolCategory.values)
            if (activeCategories.contains(cat))
              Padding(
                padding: const EdgeInsets.only(right: 6),
                child: FilterChip(
                  label: Text(cat.label),
                  avatar: Icon(categoryStyle(cat).$1,
                      size: 16, color: categoryStyle(cat).$2),
                  selected: filter.categories?.contains(cat) ?? false,
                  onSelected: (selected) {
                    final current = {...?filter.categories};
                    selected ? current.add(cat) : current.remove(cat);
                    ref.read(activityFilterProvider.notifier).state =
                        filter.copyWith(
                      categories: current.isEmpty ? null : current,
                      clearCategories: current.isEmpty,
                    );
                  },
                ),
              ),

          // Gap
          if (activeCategories.isNotEmpty) const SizedBox(width: 10),

          // Status chips (tonal)
          for (final status in ActivityStatus.values)
            Padding(
              padding: const EdgeInsets.only(right: 6),
              child: FilterChip(
                label: Text(status.name),
                selected: filter.statuses?.contains(status) ?? false,
                selectedColor:
                    Theme.of(context).colorScheme.secondaryContainer,
                onSelected: (selected) {
                  final current = {...?filter.statuses};
                  selected ? current.add(status) : current.remove(status);
                  ref.read(activityFilterProvider.notifier).state =
                      filter.copyWith(
                    statuses: current.isEmpty ? null : current,
                    clearStatuses: current.isEmpty,
                  );
                },
              ),
            ),

          // Clear all button
          if (filter.isActive)
            Center(
              child: TextButton(
                onPressed: () {
                  ref.read(activityFilterProvider.notifier).state =
                      const ActivityFilter();
                },
                child: const Text('Clear all'),
              ),
            ),
        ],
      ),
    );
  }
}
```

- [ ] **Step 2: Create activity_detail_sheet.dart**

```dart
// app/lib/features/tools/widgets/activity_detail_sheet.dart
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/features/tools/widgets/tool_category_section.dart';

/// Shows full details for a single activity entry.
void showActivityDetailSheet(BuildContext context, ActivityEntry entry) {
  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
    ),
    builder: (_) => _ActivityDetailContent(entry: entry),
  );
}

class _ActivityDetailContent extends StatelessWidget {
  final ActivityEntry entry;
  const _ActivityDetailContent({required this.entry});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final (icon, color) = entry.category != null
        ? categoryStyle(entry.category!)
        : (Icons.build, Colors.grey);

    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Drag handle
          Center(
            child: Container(
              width: 32,
              height: 4,
              decoration: BoxDecoration(
                color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.3),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Tool name + category chip
          Row(
            children: [
              Icon(icon, color: color, size: 20),
              const SizedBox(width: 8),
              Text(
                entry.toolName,
                style: theme.textTheme.titleMedium
                    ?.copyWith(fontWeight: FontWeight.w600),
              ),
              const Spacer(),
              _StatusBadge(status: entry.status),
            ],
          ),
          const SizedBox(height: 12),

          // Description
          if (entry.description.isNotEmpty)
            Text(entry.description, style: theme.textTheme.bodyMedium),
          const SizedBox(height: 12),

          // Metadata row
          Row(
            children: [
              if (entry.executionTimeMs != null) ...[
                Icon(Icons.timer_outlined,
                    size: 14, color: theme.colorScheme.onSurfaceVariant),
                const SizedBox(width: 4),
                Text('${entry.executionTimeMs}ms',
                    style: theme.textTheme.bodySmall),
                const SizedBox(width: 16),
              ],
              Icon(Icons.schedule,
                  size: 14, color: theme.colorScheme.onSurfaceVariant),
              const SizedBox(width: 4),
              Text(
                _formatAbsoluteTime(entry.timestamp),
                style: theme.textTheme.bodySmall,
              ),
            ],
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }

  String _formatAbsoluteTime(DateTime dt) {
    final months = [
      '', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
    ];
    final h = dt.hour > 12 ? dt.hour - 12 : (dt.hour == 0 ? 12 : dt.hour);
    final amPm = dt.hour >= 12 ? 'PM' : 'AM';
    final min = dt.minute.toString().padLeft(2, '0');
    final sec = dt.second.toString().padLeft(2, '0');
    return '${months[dt.month]} ${dt.day}, ${dt.year} at $h:$min:$sec $amPm';
  }
}

class _StatusBadge extends StatelessWidget {
  final ActivityStatus status;
  const _StatusBadge({required this.status});

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (status) {
      ActivityStatus.success => ('Success', Colors.green),
      ActivityStatus.failed => ('Failed', Colors.red),
      ActivityStatus.denied => ('Denied', Colors.orange),
      ActivityStatus.pending => ('Pending', Colors.grey),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        label,
        style: TextStyle(
            fontSize: 12, fontWeight: FontWeight.w600, color: color),
      ),
    );
  }
}
```

- [ ] **Step 3: Create activity_list.dart**

```dart
// app/lib/features/tools/widgets/activity_list.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/features/tools/providers/filtered_activity_provider.dart';
import 'package:nobla_agent/features/tools/widgets/activity_detail_sheet.dart';
import 'package:nobla_agent/features/tools/widgets/activity_filter_bar.dart';
import 'package:nobla_agent/features/tools/widgets/tool_category_section.dart';

/// Full activity feed tab with filter bar and scrollable list.
class ActivityListTab extends ConsumerWidget {
  const ActivityListTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final entries = ref.watch(filteredActivityProvider);
    final filter = ref.watch(activityFilterProvider);

    return Column(
      children: [
        const ActivityFilterBar(),
        const Divider(height: 1),
        Expanded(
          child: entries.isEmpty
              ? _EmptyState(hasFilter: filter.isActive)
              : ListView.separated(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  itemCount: entries.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, index) => _ActivityRow(
                    entry: entries[index],
                    onTap: () =>
                        showActivityDetailSheet(context, entries[index]),
                  ),
                ),
        ),
      ],
    );
  }
}

class _EmptyState extends StatelessWidget {
  final bool hasFilter;
  const _EmptyState({required this.hasFilter});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            hasFilter ? Icons.filter_list_off : Icons.history,
            size: 48,
            color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.4),
          ),
          const SizedBox(height: 12),
          Text(
            hasFilter ? 'No matches for current filters' : 'No activity yet',
            style: theme.textTheme.bodyMedium?.copyWith(
              color:
                  theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.6),
            ),
          ),
        ],
      ),
    );
  }
}

class _ActivityRow extends StatelessWidget {
  final ActivityEntry entry;
  final VoidCallback onTap;
  const _ActivityRow({required this.entry, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final (icon, color) = entry.category != null
        ? categoryStyle(entry.category!)
        : (Icons.build, Colors.grey);
    final statusColor = switch (entry.status) {
      ActivityStatus.success => Colors.green,
      ActivityStatus.failed => Colors.red,
      ActivityStatus.denied => Colors.orange,
      ActivityStatus.pending => Colors.grey,
    };

    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Row(
          children: [
            // Category icon + status dot
            Stack(
              children: [
                Icon(icon, color: color, size: 24),
                Positioned(
                  right: -2,
                  bottom: -2,
                  child: Container(
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(
                      color: statusColor,
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: theme.colorScheme.surface,
                        width: 1.5,
                      ),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(width: 12),
            // Content
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    entry.toolName,
                    style: theme.textTheme.bodyMedium
                        ?.copyWith(fontWeight: FontWeight.w600),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (entry.description.isNotEmpty) ...[
                    const SizedBox(height: 2),
                    Text(
                      entry.description,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ],
              ),
            ),
            // Trailing
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                if (entry.executionTimeMs != null)
                  Text(
                    '${entry.executionTimeMs}ms',
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant
                          .withValues(alpha: 0.7),
                    ),
                  ),
                Text(
                  _formatRelativeTime(entry.timestamp),
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant
                        .withValues(alpha: 0.7),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _formatRelativeTime(DateTime timestamp) {
    final diff = DateTime.now().difference(timestamp);
    if (diff.inSeconds < 60) return '${diff.inSeconds}s ago';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    return '${diff.inHours}h ago';
  }
}
```

- [ ] **Step 4: Write widget test**

```dart
// app/test/features/tools/widgets/activity_list_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/features/tools/widgets/activity_list.dart';
import 'package:nobla_agent/shared/providers/tool_activity_provider.dart';

void main() {
  testWidgets('shows empty state when no entries', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(home: Scaffold(body: ActivityListTab())),
      ),
    );
    expect(find.text('No activity yet'), findsOneWidget);
  });

  testWidgets('displays activity entries', (tester) async {
    final container = ProviderContainer();
    container.read(toolActivityProvider.notifier).addEntry(ActivityEntry(
          toolName: 'ssh.exec',
          action: 'execute',
          description: 'Run ls on server',
          status: ActivityStatus.success,
          category: ToolCategory.ssh,
          timestamp: DateTime.now(),
          executionTimeMs: 245,
        ));

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: ActivityListTab())),
      ),
    );
    await tester.pump();

    expect(find.text('ssh.exec'), findsOneWidget);
    expect(find.text('Run ls on server'), findsOneWidget);
    expect(find.text('245ms'), findsOneWidget);
  });
}
```

- [ ] **Step 5: Run tests**

Run: `cd app && flutter test test/features/tools/widgets/activity_list_test.dart -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add app/lib/features/tools/widgets/activity_filter_bar.dart \
  app/lib/features/tools/widgets/activity_list.dart \
  app/lib/features/tools/widgets/activity_detail_sheet.dart \
  app/test/features/tools/widgets/activity_list_test.dart
git commit -m "feat(tools): add filterable activity feed widgets"
```

---

## Task 8: Mirror View Widget

**Files:**
- Create: `app/lib/features/tools/widgets/mirror_view.dart`
- Test: `app/test/features/tools/widgets/mirror_view_test.dart`

- [ ] **Step 1: Create mirror_view.dart**

```dart
// app/lib/features/tools/widgets/mirror_view.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/tools/providers/tool_mirror_provider.dart';

/// Displays the latest screenshot with pinch-to-zoom and manual capture.
class MirrorView extends ConsumerWidget {
  const MirrorView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final mirror = ref.watch(toolMirrorProvider);
    final theme = Theme.of(context);

    return Column(
      children: [
        // Status bar
        _MirrorStatusBar(mirror: mirror, ref: ref),
        const Divider(height: 1),
        // Screenshot area
        Expanded(
          child: mirror.latestScreenshot != null
              ? InteractiveViewer(
                  minScale: 0.5,
                  maxScale: 4.0,
                  child: Center(
                    child: Stack(
                      alignment: Alignment.center,
                      children: [
                        Image.memory(
                          mirror.latestScreenshot!,
                          fit: BoxFit.contain,
                          gaplessPlayback: true,
                        ),
                        if (mirror.isCapturing)
                          Container(
                            color: Colors.black26,
                            child: const CircularProgressIndicator(),
                          ),
                      ],
                    ),
                  ),
                )
              : _MirrorPlaceholder(
                  error: mirror.error,
                  isCapturing: mirror.isCapturing,
                ),
        ),
      ],
    );
  }
}

class _MirrorStatusBar extends StatelessWidget {
  final MirrorState mirror;
  final WidgetRef ref;
  const _MirrorStatusBar({required this.mirror, required this.ref});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          // Subscription indicator
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              color: mirror.isSubscribed ? Colors.green : Colors.red,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 8),
          Text(
            mirror.isSubscribed ? 'Live' : 'Paused',
            style: theme.textTheme.labelMedium,
          ),
          if (mirror.lastUpdated != null) ...[
            const SizedBox(width: 8),
            Text(
              _formatLastUpdated(mirror.lastUpdated),
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
          const Spacer(),
          // Capture button
          IconButton(
            icon: const Icon(Icons.camera_alt_outlined),
            tooltip: 'Capture Now',
            onPressed: mirror.isCapturing
                ? null
                : () => ref.read(toolMirrorProvider.notifier).captureNow(),
          ),
        ],
      ),
    );
  }

  String _formatLastUpdated(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inSeconds < 60) return 'Updated ${diff.inSeconds}s ago';
    if (diff.inMinutes < 60) return 'Updated ${diff.inMinutes}m ago';
    return 'Updated ${diff.inHours}h ago';
  }
}

class _MirrorPlaceholder extends StatelessWidget {
  final String? error;
  final bool isCapturing;
  const _MirrorPlaceholder({this.error, this.isCapturing = false});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (isCapturing) {
      return const Center(child: CircularProgressIndicator());
    }
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            error != null ? Icons.error_outline : Icons.screenshot_monitor,
            size: 48,
            color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.4),
          ),
          const SizedBox(height: 12),
          Text(
            error ?? 'No screenshots yet',
            style: theme.textTheme.bodyMedium?.copyWith(
              color:
                  theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.6),
            ),
            textAlign: TextAlign.center,
          ),
          if (error == null) ...[
            const SizedBox(height: 4),
            Text(
              'Activity will appear here when tools execute',
              style: theme.textTheme.bodySmall?.copyWith(
                color:
                    theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.4),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
```

- [ ] **Step 2: Write widget test**

```dart
// app/test/features/tools/widgets/mirror_view_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/tools/widgets/mirror_view.dart';
import 'package:nobla_agent/features/tools/providers/tool_mirror_provider.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';

void main() {
  testWidgets('shows placeholder when no screenshot', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          toolMirrorProvider.overrideWith(
            (ref) => ToolMirrorNotifier(
                sendRpc: (m, p) async => <String, dynamic>{}),
          ),
        ],
        child: const MaterialApp(home: Scaffold(body: MirrorView())),
      ),
    );
    expect(find.text('No screenshots yet'), findsOneWidget);
    expect(find.byIcon(Icons.camera_alt_outlined), findsOneWidget);
  });
}
```

- [ ] **Step 3: Run tests**

Run: `cd app && flutter test test/features/tools/widgets/mirror_view_test.dart -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add app/lib/features/tools/widgets/mirror_view.dart \
  app/test/features/tools/widgets/mirror_view_test.dart
git commit -m "feat(tools): add mirror view with pinch-to-zoom and capture button"
```

---

## Task 9: Tools Screen + Router Integration

**Files:**
- Create: `app/lib/features/tools/screens/tools_screen.dart`
- Modify: `app/lib/core/routing/app_router.dart`
- Test: `app/test/features/tools/screens/tools_screen_test.dart`

- [ ] **Step 1: Create tools_screen.dart**

```dart
// app/lib/features/tools/screens/tools_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/tools/providers/tool_mirror_provider.dart';
import 'package:nobla_agent/features/tools/widgets/mirror_view.dart';
import 'package:nobla_agent/features/tools/widgets/activity_list.dart';
import 'package:nobla_agent/features/tools/providers/tool_catalog_provider.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/features/tools/widgets/tool_category_section.dart';
import 'package:shimmer/shimmer.dart';

class ToolsScreen extends ConsumerStatefulWidget {
  const ToolsScreen({super.key});

  @override
  ConsumerState<ToolsScreen> createState() => _ToolsScreenState();
}

class _ToolsScreenState extends ConsumerState<ToolsScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
    _tabController.addListener(_onTabChanged);
  }

  void _onTabChanged() {
    if (_tabController.indexIsChanging) return;
    final mirror = ref.read(toolMirrorProvider.notifier);
    if (_tabController.index == 0) {
      mirror.subscribe();
    } else {
      mirror.unsubscribe();
    }
  }

  @override
  void dispose() {
    _tabController.removeListener(_onTabChanged);
    ref.read(toolMirrorProvider.notifier).unsubscribe();
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Tools'),
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(icon: Icon(Icons.screenshot_monitor), text: 'Mirror'),
            Tab(icon: Icon(Icons.history), text: 'Activity'),
            Tab(icon: Icon(Icons.widgets_outlined), text: 'Browse'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: const [
          MirrorView(),
          ActivityListTab(),
          _BrowseTab(),
        ],
      ),
    );
  }
}

class _BrowseTab extends ConsumerWidget {
  const _BrowseTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final catalogAsync = ref.watch(toolCatalogProvider);

    return catalogAsync.when(
      loading: () => _ShimmerLoading(),
      error: (err, _) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 48),
            const SizedBox(height: 12),
            const Text("Couldn't load tools"),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: () => ref.invalidate(toolCatalogProvider),
              child: const Text('Retry'),
            ),
          ],
        ),
      ),
      data: (tools) {
        // Group by category
        final grouped = <ToolCategory, List<ToolManifestEntry>>{};
        for (final t in tools) {
          if (t.category != null) {
            grouped.putIfAbsent(t.category!, () => []).add(t);
          }
        }
        // Sort categories in defined order
        final sortedCats = ToolCategory.values
            .where((c) => grouped.containsKey(c))
            .toList();

        if (sortedCats.isEmpty) {
          return const Center(child: Text('No tools available'));
        }

        return RefreshIndicator(
          onRefresh: () async => ref.invalidate(toolCatalogProvider),
          child: ListView.builder(
            itemCount: sortedCats.length,
            itemBuilder: (context, index) {
              final cat = sortedCats[index];
              return ToolCategorySection(
                category: cat,
                tools: grouped[cat]!,
                initiallyExpanded: sortedCats.length <= 3,
              );
            },
          ),
        );
      },
    );
  }
}

class _ShimmerLoading extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Shimmer.fromColors(
      baseColor: Theme.of(context).colorScheme.surfaceContainerHighest,
      highlightColor: Theme.of(context).colorScheme.surface,
      child: ListView.builder(
        itemCount: 5,
        padding: const EdgeInsets.all(16),
        itemBuilder: (_, __) => Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Container(
            height: 60,
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(8),
            ),
          ),
        ),
      ),
    );
  }
}
```

- [ ] **Step 2: Update app_router.dart**

Add the Tools tab as the 5th destination (index 4), pushing Settings to index 5:

```dart
// Add import at top:
import 'package:nobla_agent/features/tools/screens/tools_screen.dart';

// Add route inside ShellRoute.routes, before settings:
          GoRoute(
            path: '/home/tools',
            builder: (context, state) => const ToolsScreen(),
          ),

// Update HomeShell.onDestinationSelected switch:
        onDestinationSelected: (index) {
          switch (index) {
            case 0:
              context.go('/home/chat');
            case 1:
              context.go('/home/dashboard');
            case 2:
              context.go('/home/memory');
            case 3:
              context.go('/home/persona');
            case 4:
              context.go('/home/tools');
            case 5:
              context.go('/home/settings');
          }
        },

// Add NavigationDestination before Settings:
          NavigationDestination(
            icon: Icon(Icons.build_outlined),
            selectedIcon: Icon(Icons.build),
            label: 'Tools',
          ),

// Update _calculateIndex:
  int _calculateIndex(String location) {
    if (location.startsWith('/home/dashboard')) return 1;
    if (location.startsWith('/home/memory')) return 2;
    if (location.startsWith('/home/persona')) return 3;
    if (location.startsWith('/home/tools')) return 4;
    if (location.startsWith('/home/settings')) return 5;
    return 0;
  }
```

- [ ] **Step 3: Write basic screen test**

```dart
// app/test/features/tools/screens/tools_screen_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/tools/screens/tools_screen.dart';
import 'package:nobla_agent/features/tools/providers/tool_mirror_provider.dart';
import 'package:nobla_agent/features/tools/providers/tool_catalog_provider.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';

void main() {
  testWidgets('ToolsScreen shows 3 tabs', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          toolMirrorProvider.overrideWith(
            (ref) => ToolMirrorNotifier(
                sendRpc: (m, p) async => <String, dynamic>{}),
          ),
          toolCatalogProvider.overrideWith(
            (ref) async => <ToolManifestEntry>[],
          ),
        ],
        child: const MaterialApp(home: ToolsScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Mirror'), findsOneWidget);
    expect(find.text('Activity'), findsOneWidget);
    expect(find.text('Browse'), findsOneWidget);
  });
}
```

- [ ] **Step 4: Run all tests**

Run: `cd app && flutter test`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add app/lib/features/tools/screens/tools_screen.dart \
  app/lib/core/routing/app_router.dart \
  app/test/features/tools/screens/tools_screen_test.dart
git commit -m "feat(tools): add ToolsScreen with TabBar and 6th nav tab"
```

---

## Task 10: Backend — Mirror Handlers

**Files:**
- Create: `backend/nobla/gateway/mirror_handlers.py`
- Test: `backend/tests/gateway/test_mirror_handlers.py`

- [ ] **Step 1: Write tests**

```python
# backend/tests/gateway/test_mirror_handlers.py
"""Tests for mirror subscription and capture handlers."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nobla.gateway.mirror_handlers import (
    handle_mirror_subscribe,
    handle_mirror_unsubscribe,
    handle_mirror_capture,
    is_mirror_active,
    remove_subscriber,
    _mirror_subscribers,
)
from nobla.gateway.websocket import ConnectionState


@pytest.fixture(autouse=True)
def _clear_subscribers():
    _mirror_subscribers.clear()
    yield
    _mirror_subscribers.clear()


def _make_state(cid: str = "conn-1") -> ConnectionState:
    return ConnectionState(connection_id=cid, user_id="user-1", tier=4)


@pytest.mark.asyncio
async def test_subscribe_adds_connection():
    state = _make_state()
    result = await handle_mirror_subscribe({}, state)
    assert result == {"status": "subscribed"}
    assert is_mirror_active("conn-1")


@pytest.mark.asyncio
async def test_unsubscribe_removes_connection():
    state = _make_state()
    await handle_mirror_subscribe({}, state)
    result = await handle_mirror_unsubscribe({}, state)
    assert result == {"status": "unsubscribed"}
    assert not is_mirror_active("conn-1")


@pytest.mark.asyncio
async def test_unsubscribe_noop_when_not_subscribed():
    state = _make_state()
    result = await handle_mirror_unsubscribe({}, state)
    assert result == {"status": "unsubscribed"}


def test_remove_subscriber_cleans_up():
    _mirror_subscribers.add("conn-1")
    remove_subscriber("conn-1")
    assert not is_mirror_active("conn-1")


def test_remove_subscriber_noop_for_unknown():
    remove_subscriber("unknown")  # Should not raise


@pytest.mark.asyncio
async def test_capture_returns_screenshot():
    mock_registry = MagicMock()
    mock_tool = AsyncMock()
    mock_tool.execute = AsyncMock(return_value=MagicMock(
        success=True, data={"screenshot_b64": "abc123"}
    ))
    mock_registry.get.return_value = mock_tool

    with patch("nobla.gateway.mirror_handlers._get_registry", return_value=mock_registry):
        state = _make_state()
        result = await handle_mirror_capture({}, state)
        assert result["screenshot_b64"] == "abc123"
        assert result["error"] is None


@pytest.mark.asyncio
async def test_capture_returns_error_when_tool_unavailable():
    with patch("nobla.gateway.mirror_handlers._get_registry", return_value=MagicMock(get=MagicMock(return_value=None))):
        state = _make_state()
        result = await handle_mirror_capture({}, state)
        assert result["screenshot_b64"] is None
        assert "unavailable" in result["error"].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/gateway/test_mirror_handlers.py -v`
Expected: FAIL

- [ ] **Step 3: Create mirror_handlers.py**

```python
# backend/nobla/gateway/mirror_handlers.py
"""Mirror subscription and on-demand capture RPC handlers."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from nobla.gateway.websocket import ConnectionState, rpc_method
from nobla.tools.models import ToolParams

logger = structlog.get_logger(__name__)

# Active mirror subscribers (connection IDs).
_mirror_subscribers: set[str] = set()
_capture_in_progress: bool = False


def _get_registry():
    from nobla.gateway.tool_handlers import get_tool_registry
    return get_tool_registry()


def _get_connection_manager():
    from nobla.gateway.tool_handlers import get_tool_executor
    executor = get_tool_executor()
    return executor._cm if executor else None


@rpc_method("tool.mirror.subscribe")
async def handle_mirror_subscribe(
    params: dict, state: ConnectionState,
) -> dict:
    _mirror_subscribers.add(state.connection_id)
    logger.info("mirror.subscribed", connection_id=state.connection_id)
    return {"status": "subscribed"}


@rpc_method("tool.mirror.unsubscribe")
async def handle_mirror_unsubscribe(
    params: dict, state: ConnectionState,
) -> dict:
    _mirror_subscribers.discard(state.connection_id)
    logger.info("mirror.unsubscribed", connection_id=state.connection_id)
    return {"status": "unsubscribed"}


@rpc_method("tool.mirror.capture")
async def handle_mirror_capture(
    params: dict, state: ConnectionState,
) -> dict:
    """On-demand screenshot capture — request/response pattern."""
    registry = _get_registry()
    if not registry:
        return {"screenshot_b64": None, "error": "Tool platform not initialized"}

    tool = registry.get("screenshot.capture")
    if not tool:
        return {"screenshot_b64": None, "error": "Screenshot tool unavailable"}

    try:
        tool_params = ToolParams(
            args={},
            connection_state=state,
        )
        result = await tool.execute(tool_params)
        if result.success and result.data:
            b64 = result.data.get("screenshot_b64")
            return {"screenshot_b64": b64, "error": None}
        return {"screenshot_b64": None, "error": result.error or "Capture failed"}
    except Exception as exc:
        logger.warning("mirror.capture_failed", error=str(exc))
        return {"screenshot_b64": None, "error": f"Capture failed: {exc}"}


def is_mirror_active(connection_id: str) -> bool:
    return connection_id in _mirror_subscribers


def is_capture_in_progress() -> bool:
    return _capture_in_progress


async def capture_and_send(connection_id: str) -> None:
    """Background task: capture screenshot and send as mirror.frame notification."""
    global _capture_in_progress
    _capture_in_progress = True
    try:
        registry = _get_registry()
        cm = _get_connection_manager()
        if not registry or not cm:
            return

        tool = registry.get("screenshot.capture")
        if not tool:
            return

        state = ConnectionState(connection_id=connection_id)
        tool_params = ToolParams(args={}, connection_state=state)
        result = await tool.execute(tool_params)

        if result.success and result.data:
            b64 = result.data.get("screenshot_b64")
            if b64:
                await cm.send_to(connection_id, {
                    "jsonrpc": "2.0",
                    "method": "tool.mirror.frame",
                    "params": {
                        "screenshot_b64": b64,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                })
    except Exception as exc:
        logger.warning("mirror.background_capture_failed", error=str(exc))
    finally:
        _capture_in_progress = False


def remove_subscriber(connection_id: str) -> None:
    """Clean up on WebSocket disconnect."""
    _mirror_subscribers.discard(connection_id)
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/gateway/test_mirror_handlers.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/gateway/mirror_handlers.py \
  backend/tests/gateway/test_mirror_handlers.py
git commit -m "feat(mirror): add mirror subscribe/unsubscribe/capture RPC handlers"
```

---

## Task 11: Backend — Executor mirror integration + disconnect cleanup

**Files:**
- Modify: `backend/nobla/tools/executor.py`
- Modify: `backend/nobla/gateway/websocket.py`
- Test: `backend/tests/tools/test_executor_mirror.py`

- [ ] **Step 1: Write test for mirror capture trigger in executor**

```python
# backend/tests/tools/test_executor_mirror.py
"""Test that executor triggers mirror capture after tool.activity broadcast."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nobla.tools.executor import ToolExecutor
from nobla.tools.models import ToolParams
from nobla.gateway.websocket import ConnectionState


@pytest.mark.asyncio
async def test_audit_triggers_mirror_capture_when_subscribed():
    """When mirror is active for a connection, _audit should spawn capture task."""
    mock_registry = MagicMock()
    mock_tool = MagicMock()
    mock_tool.name = "test.tool"
    mock_tool.category = MagicMock(value="code")
    mock_tool.describe_action.return_value = "Test action"
    mock_tool.get_params_summary.return_value = {}

    mock_cm = AsyncMock()
    mock_audit = AsyncMock()

    executor = ToolExecutor(
        registry=mock_registry,
        permission_checker=MagicMock(),
        audit_logger=mock_audit,
        approval_manager=MagicMock(),
        connection_manager=mock_cm,
    )

    state = ConnectionState(connection_id="conn-1", user_id="u1", tier=4)
    params = ToolParams(args={}, connection_state=state)

    with patch("nobla.tools.executor.is_mirror_active", return_value=True), \
         patch("nobla.tools.executor.is_capture_in_progress", return_value=False), \
         patch("nobla.tools.executor.capture_and_send", new_callable=AsyncMock) as mock_capture, \
         patch("asyncio.create_task") as mock_create_task:
        import time
        await executor._audit(mock_tool, params, "success", time.monotonic())
        mock_create_task.assert_called_once()


@pytest.mark.asyncio
async def test_audit_skips_mirror_when_not_subscribed():
    """When mirror is not active, no capture task is spawned."""
    mock_cm = AsyncMock()
    mock_audit = AsyncMock()
    mock_tool = MagicMock()
    mock_tool.name = "test.tool"
    mock_tool.category = MagicMock(value="code")
    mock_tool.describe_action.return_value = "Test"
    mock_tool.get_params_summary.return_value = {}

    executor = ToolExecutor(
        registry=MagicMock(),
        permission_checker=MagicMock(),
        audit_logger=mock_audit,
        approval_manager=MagicMock(),
        connection_manager=mock_cm,
    )

    state = ConnectionState(connection_id="conn-1", user_id="u1", tier=4)
    params = ToolParams(args={}, connection_state=state)

    with patch("nobla.tools.executor.is_mirror_active", return_value=False), \
         patch("asyncio.create_task") as mock_create_task:
        import time
        await executor._audit(mock_tool, params, "success", time.monotonic())
        mock_create_task.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/tools/test_executor_mirror.py -v`
Expected: FAIL

- [ ] **Step 3: Modify executor.py — add mirror capture after audit**

Add imports at top of `backend/nobla/tools/executor.py`:

```python
from nobla.gateway.mirror_handlers import (
    is_mirror_active,
    is_capture_in_progress,
    capture_and_send,
)
```

Append to the `_audit` method (after the `send_to` call at line 160):

```python
        # Trigger mirror screenshot capture (background, non-blocking)
        if self._cm:
            conn_id = params.connection_state.connection_id
            # ... existing send_to call ...

            # Mirror: capture screenshot if subscriber is active
            if is_mirror_active(conn_id) and not is_capture_in_progress():
                asyncio.create_task(capture_and_send(conn_id))
```

- [ ] **Step 4: Modify websocket.py — add mirror cleanup in disconnect**

In `backend/nobla/gateway/websocket.py`, add to the `disconnect` method (line 89-92):

```python
    def disconnect(self, connection_id: str) -> None:
        """Remove a connection from the active set."""
        self._connections.pop(connection_id, None)
        # Clean up mirror subscriptions
        from nobla.gateway.mirror_handlers import remove_subscriber
        remove_subscriber(connection_id)
        logger.info("ws.disconnected", connection_id=connection_id)
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/tools/test_executor_mirror.py tests/gateway/test_mirror_handlers.py -v`
Expected: ALL PASS

- [ ] **Step 6: Run full backend test suite for regressions**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add backend/nobla/tools/executor.py \
  backend/nobla/gateway/websocket.py \
  backend/tests/tools/test_executor_mirror.py
git commit -m "feat(mirror): integrate mirror capture into executor audit path"
```

---

## Task 12: Full Integration Test + CLAUDE.md Update

**Files:**
- Test: `app/test/features/tools/integration_test.dart`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run full Flutter test suite**

Run: `cd app && flutter test --coverage`
Expected: ALL PASS

- [ ] **Step 2: Run full backend test suite**

Run: `cd backend && python -m pytest tests/ -v --cov=nobla`
Expected: ALL PASS

- [ ] **Step 3: Run flutter analyze**

Run: `cd app && flutter analyze`
Expected: No issues

- [ ] **Step 4: Update CLAUDE.md Phase 4 status table**

Change Phase 4D row to show ✅ Complete (implementation done), add Phase 4E row:

```
| 4D: Remote Control | ✅ Complete | ssh.connect, ssh.exec, sftp.manage (116 tests) |
| 4E: Flutter Tool UI | ✅ Complete | Screen mirror, activity feed, tool browser |
```

Also update the "Currently in **active development**" line to include Phase 4E.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat(tools): complete Phase 4E — Flutter Tool UI with mirror, activity feed, browser"
```

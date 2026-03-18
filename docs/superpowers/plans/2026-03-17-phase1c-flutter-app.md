# Phase 1C: Flutter Mobile App — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Flutter 3.x cross-platform app (Android + iOS + Web) with auth, real-time chat, security dashboard, and kill switch — connecting to the Phase 1A/1B backend via WebSocket JSON-RPC 2.0.

**Architecture:** Infrastructure-first approach. Build WebSocket client and JSON-RPC protocol layer first, then auth state management, then feature screens on top. Riverpod for state, GoRouter for navigation, Material 3 dark theme.

**Tech Stack:** Flutter 3.x, Dart, Riverpod, GoRouter, web_socket_channel, flutter_secure_storage, flutter_markdown

**Spec:** `docs/superpowers/specs/2026-03-17-phase1c-flutter-app-design.md`

---

## File Structure

```
app/
├── lib/
│   ├── main.dart
│   ├── core/
│   │   ├── theme/
│   │   │   └── app_theme.dart
│   │   ├── routing/
│   │   │   └── app_router.dart
│   │   ├── network/
│   │   │   ├── websocket_client.dart
│   │   │   └── jsonrpc_client.dart
│   │   └── providers/
│   │       ├── auth_provider.dart
│   │       ├── config_provider.dart
│   │       └── notification_provider.dart
│   ├── features/
│   │   ├── auth/
│   │   │   ├── screens/
│   │   │   │   ├── login_screen.dart
│   │   │   │   └── register_screen.dart
│   │   │   └── widgets/
│   │   │       └── auth_form.dart
│   │   ├── chat/
│   │   │   ├── screens/
│   │   │   │   └── chat_screen.dart
│   │   │   ├── widgets/
│   │   │   │   ├── message_bubble.dart
│   │   │   │   ├── message_input.dart
│   │   │   │   └── tool_activity_indicator.dart
│   │   │   └── providers/
│   │   │       └── chat_provider.dart
│   │   ├── dashboard/
│   │   │   ├── screens/
│   │   │   │   └── dashboard_screen.dart
│   │   │   └── widgets/
│   │   │       ├── connection_card.dart
│   │   │       ├── security_tier_card.dart
│   │   │       └── cost_card.dart
│   │   └── settings/
│   │       ├── screens/
│   │       │   └── settings_screen.dart
│   │       └── providers/
│   │           └── settings_provider.dart
│   └── shared/
│       ├── widgets/
│       │   ├── kill_switch_fab.dart
│       │   └── connection_indicator.dart
│       └── models/
│           ├── chat_message.dart
│           ├── user_model.dart
│           └── rpc_error.dart
├── test/
│   ├── core/
│   │   ├── network/
│   │   │   ├── websocket_client_test.dart
│   │   │   └── jsonrpc_client_test.dart
│   │   └── providers/
│   │       └── auth_provider_test.dart
│   └── features/
│       ├── auth/
│       │   └── auth_screen_test.dart
│       ├── chat/
│       │   ├── chat_provider_test.dart
│       │   └── chat_screen_test.dart
│       └── dashboard/
│           └── dashboard_screen_test.dart
├── web/
├── android/
├── ios/
└── pubspec.yaml
```

---

### Task 1: Flutter Project Scaffold

**Files:**
- Create: `app/` (Flutter project via `flutter create`)
- Modify: `app/pubspec.yaml`
- Create: `app/lib/main.dart`
- Create: all directory stubs under `app/lib/`

- [ ] **Step 1: Create Flutter project**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent"
flutter create --org ai.nabilnet --project-name nobla_agent app
```

- [ ] **Step 2: Replace pubspec.yaml with project dependencies**

Replace `app/pubspec.yaml` with:
```yaml
name: nobla_agent
description: Privacy-first AI super agent
publish_to: 'none'
version: 0.1.0+1

environment:
  sdk: ^3.5.0

dependencies:
  flutter:
    sdk: flutter
  flutter_riverpod: ^2.5.1
  riverpod_annotation: ^2.3.5
  go_router: ^14.2.0
  web_socket_channel: ^3.0.1
  flutter_secure_storage: ^9.2.2
  shared_preferences: ^2.3.2
  flutter_markdown: ^0.7.3+2
  google_fonts: ^6.2.1
  shimmer: ^3.0.0
  uuid: ^4.5.1

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^4.0.0
  riverpod_generator: ^2.4.3
  build_runner: ^2.4.12
  mocktail: ^1.0.4
```

- [ ] **Step 3: Install dependencies**

```bash
cd app && flutter pub get
```

- [ ] **Step 4: Create directory structure**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/app"
mkdir -p lib/core/theme lib/core/routing lib/core/network lib/core/providers
mkdir -p lib/features/auth/screens lib/features/auth/widgets
mkdir -p lib/features/chat/screens lib/features/chat/widgets lib/features/chat/providers
mkdir -p lib/features/dashboard/screens lib/features/dashboard/widgets
mkdir -p lib/features/settings/screens lib/features/settings/providers
mkdir -p lib/shared/widgets lib/shared/models
mkdir -p test/core/network test/core/providers
mkdir -p test/features/auth test/features/chat test/features/dashboard
```

- [ ] **Step 5: Write minimal main.dart**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

void main() {
  runApp(const ProviderScope(child: NoblaApp()));
}

class NoblaApp extends StatelessWidget {
  const NoblaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Nobla Agent',
      theme: ThemeData.dark(useMaterial3: true),
      home: const Scaffold(
        body: Center(child: Text('Nobla Agent')),
      ),
    );
  }
}
```

- [ ] **Step 6: Verify build**

```bash
cd app && flutter analyze && flutter test
```

- [ ] **Step 7: Commit**

```bash
git add app/
git commit -m "feat: scaffold Flutter project with dependencies"
```

---

### Task 2: Shared Models & RPC Error Types

**Files:**
- Create: `app/lib/shared/models/rpc_error.dart`
- Create: `app/lib/shared/models/chat_message.dart`
- Create: `app/lib/shared/models/user_model.dart`
- Test: `app/test/core/network/jsonrpc_client_test.dart` (error model tests)

- [ ] **Step 1: Write tests for RPC error models**

Create `app/test/shared/models/rpc_error_test.dart`:
```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/shared/models/rpc_error.dart';

void main() {
  group('RpcError', () {
    test('fromJson parses standard error', () {
      final json = {'code': -32011, 'message': 'Auth required', 'data': {'method': 'chat.send'}};
      final error = RpcError.fromJson(json);
      expect(error.code, -32011);
      expect(error.message, 'Auth required');
      expect(error.data?['method'], 'chat.send');
    });

    test('isAuthRequired returns true for -32011', () {
      final error = RpcError(code: -32011, message: 'Auth required');
      expect(error.isAuthRequired, true);
      expect(error.isPermissionDenied, false);
    });

    test('isBudgetExceeded returns true for -32020', () {
      final error = RpcError(code: -32020, message: 'Budget exceeded');
      expect(error.isBudgetExceeded, true);
    });

    test('isServerKilled returns true for -32030', () {
      final error = RpcError(code: -32030, message: 'Server killed');
      expect(error.isServerKilled, true);
    });
  });

  group('ChatMessage', () {
    test('fromRpcResponse maps snake_case to camelCase', () {
      final json = {
        'message': 'Hello world',
        'model': 'gemini-2.0-flash',
        'tokens_used': 142,
        'cost_usd': 0.001,
        'conversation_id': 'conv-123',
      };
      final msg = ChatMessage.fromRpcResponse(json, isUser: false);
      expect(msg.content, 'Hello world');
      expect(msg.model, 'gemini-2.0-flash');
      expect(msg.tokensUsed, 142);
      expect(msg.costUsd, 0.001);
      expect(msg.isUser, false);
    });

    test('user message factory creates correct message', () {
      final msg = ChatMessage.user('Hello');
      expect(msg.isUser, true);
      expect(msg.content, 'Hello');
      expect(msg.status, MessageStatus.sending);
    });
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd app && flutter test test/shared/models/rpc_error_test.dart
```
Expected: FAIL — files don't exist yet

- [ ] **Step 3: Implement rpc_error.dart**

Create `app/lib/shared/models/rpc_error.dart`:
```dart
class RpcError implements Exception {
  final int code;
  final String message;
  final Map<String, dynamic>? data;

  const RpcError({required this.code, required this.message, this.data});

  factory RpcError.fromJson(Map<String, dynamic> json) {
    return RpcError(
      code: json['code'] as int,
      message: json['message'] as String,
      data: json['data'] as Map<String, dynamic>?,
    );
  }

  bool get isAuthRequired => code == -32011;
  bool get isAuthFailed => code == -32012;
  bool get isTokenExpired => code == -32013;
  bool get isPermissionDenied => code == -32010;
  bool get isBudgetExceeded => code == -32020;
  bool get isServerKilled => code == -32030;
  bool get isParseError => code == -32700;
  bool get isMethodNotFound => code == -32601;
  bool get isInternalError => code == -32603;

  @override
  String toString() => 'RpcError($code): $message';
}
```

- [ ] **Step 4: Implement chat_message.dart**

Create `app/lib/shared/models/chat_message.dart`:
```dart
import 'package:uuid/uuid.dart';

enum MessageStatus { sending, sent, error }

class ChatMessage {
  final String id;
  final String content;
  final bool isUser;
  final DateTime timestamp;
  final String? model;
  final int? tokensUsed;
  final double? costUsd;
  final MessageStatus status;

  const ChatMessage({
    required this.id,
    required this.content,
    required this.isUser,
    required this.timestamp,
    this.model,
    this.tokensUsed,
    this.costUsd,
    this.status = MessageStatus.sent,
  });

  factory ChatMessage.user(String content) {
    return ChatMessage(
      id: const Uuid().v4(),
      content: content,
      isUser: true,
      timestamp: DateTime.now(),
      status: MessageStatus.sending,
    );
  }

  factory ChatMessage.fromRpcResponse(
    Map<String, dynamic> json, {
    required bool isUser,
  }) {
    return ChatMessage(
      id: const Uuid().v4(),
      content: json['message'] as String,
      isUser: isUser,
      timestamp: DateTime.now(),
      model: json['model'] as String?,
      tokensUsed: json['tokens_used'] as int?,
      costUsd: (json['cost_usd'] as num?)?.toDouble(),
      status: MessageStatus.sent,
    );
  }

  ChatMessage copyWith({MessageStatus? status, String? content}) {
    return ChatMessage(
      id: id,
      content: content ?? this.content,
      isUser: isUser,
      timestamp: timestamp,
      model: model,
      tokensUsed: tokensUsed,
      costUsd: costUsd,
      status: status ?? this.status,
    );
  }
}
```

- [ ] **Step 5: Implement user_model.dart**

Create `app/lib/shared/models/user_model.dart`:
```dart
class UserModel {
  final String userId;
  final String displayName;
  final int tier;

  const UserModel({
    required this.userId,
    required this.displayName,
    this.tier = 1,
  });

  UserModel copyWith({int? tier, String? displayName}) {
    return UserModel(
      userId: userId,
      displayName: displayName ?? this.displayName,
      tier: tier ?? this.tier,
    );
  }

  String get tierName {
    switch (tier) {
      case 1: return 'SAFE';
      case 2: return 'STANDARD';
      case 3: return 'ELEVATED';
      case 4: return 'ADMIN';
      default: return 'UNKNOWN';
    }
  }
}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd app && flutter test test/shared/models/rpc_error_test.dart
```
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add app/lib/shared/ app/test/shared/
git commit -m "feat: add shared models (RpcError, ChatMessage, UserModel)"
```

---

### Task 3: WebSocket Client

**Files:**
- Create: `app/lib/core/network/websocket_client.dart`
- Create: `app/test/core/network/websocket_client_test.dart`

- [ ] **Step 1: Write WebSocket client tests**

Create `app/test/core/network/websocket_client_test.dart`:
```dart
import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/core/network/websocket_client.dart';

void main() {
  group('WebSocketClient', () {
    late WebSocketClient client;

    setUp(() {
      client = WebSocketClient();
    });

    tearDown(() {
      client.dispose();
    });

    test('initial status is disconnected', () {
      expect(client.currentStatus, ConnectionStatus.disconnected);
    });

    test('connect changes status to connecting then handles failure', () async {
      final statuses = <ConnectionStatus>[];
      client.statusStream.listen(statuses.add);

      // Connecting to invalid URL should fail gracefully
      await client.connect('ws://localhost:99999/invalid');

      // Allow time for status changes
      await Future.delayed(const Duration(milliseconds: 100));
      expect(statuses, contains(ConnectionStatus.connecting));
    });

    test('disconnect resets status', () {
      client.disconnect();
      expect(client.currentStatus, ConnectionStatus.disconnected);
    });

    test('messageStream is a broadcast stream', () {
      // Should not throw when listened to multiple times
      client.messageStream.listen((_) {});
      client.messageStream.listen((_) {});
    });
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd app && flutter test test/core/network/websocket_client_test.dart
```
Expected: FAIL — class doesn't exist

- [ ] **Step 3: Implement WebSocket client**

Create `app/lib/core/network/websocket_client.dart`:
```dart
import 'dart:async';
import 'dart:math';
import 'package:web_socket_channel/web_socket_channel.dart';

enum ConnectionStatus { disconnected, connecting, connected, error }

class WebSocketClient {
  WebSocketChannel? _channel;
  final _statusController = StreamController<ConnectionStatus>.broadcast();
  final _messageController = StreamController<String>.broadcast();
  ConnectionStatus _currentStatus = ConnectionStatus.disconnected;
  String? _url;
  Timer? _reconnectTimer;
  Timer? _heartbeatTimer;
  int _reconnectAttempts = 0;
  bool _disposed = false;

  Stream<ConnectionStatus> get statusStream => _statusController.stream;
  Stream<String> get messageStream => _messageController.stream;
  ConnectionStatus get currentStatus => _currentStatus;

  void _setStatus(ConnectionStatus status) {
    _currentStatus = status;
    if (!_disposed) _statusController.add(status);
  }

  Future<void> connect(String url) async {
    _url = url;
    _reconnectAttempts = 0;
    await _doConnect();
  }

  Future<void> _doConnect() async {
    if (_disposed) return;
    _setStatus(ConnectionStatus.connecting);
    try {
      final uri = Uri.parse(_url!);
      _channel = WebSocketChannel.connect(uri);
      await _channel!.ready;
      _setStatus(ConnectionStatus.connected);
      _reconnectAttempts = 0;
      _startHeartbeat();
      _channel!.stream.listen(
        (data) {
          if (!_disposed) _messageController.add(data as String);
        },
        onDone: _onDisconnected,
        onError: (_) => _onDisconnected(),
      );
    } catch (e) {
      _setStatus(ConnectionStatus.error);
      _scheduleReconnect();
    }
  }

  void _onDisconnected() {
    _stopHeartbeat();
    if (!_disposed && _url != null) {
      _setStatus(ConnectionStatus.disconnected);
      _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    if (_disposed || _url == null) return;
    _reconnectAttempts++;
    final delay = min(pow(2, _reconnectAttempts).toInt(), 30);
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(Duration(seconds: delay), _doConnect);
  }

  void _startHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (_currentStatus == ConnectionStatus.connected) {
        try {
          // Send a JSON-RPC health ping
          send('{"jsonrpc":"2.0","method":"system.health","id":0}');
        } catch (_) {
          _onDisconnected();
        }
      }
    });
  }

  void _stopHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
  }

  void send(String message) {
    _channel?.sink.add(message);
  }

  void disconnect() {
    _url = null;
    _reconnectTimer?.cancel();
    _stopHeartbeat();
    _channel?.sink.close();
    _channel = null;
    _setStatus(ConnectionStatus.disconnected);
  }

  void dispose() {
    _disposed = true;
    disconnect();
    _statusController.close();
    _messageController.close();
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd app && flutter test test/core/network/websocket_client_test.dart
```
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add app/lib/core/network/websocket_client.dart app/test/core/network/websocket_client_test.dart
git commit -m "feat: add WebSocket client with auto-reconnect and heartbeat"
```

---

### Task 4: JSON-RPC Client

**Files:**
- Create: `app/lib/core/network/jsonrpc_client.dart`
- Create: `app/test/core/network/jsonrpc_client_test.dart`

- [ ] **Step 1: Write JSON-RPC client tests**

Create `app/test/core/network/jsonrpc_client_test.dart`:
```dart
import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';
import 'package:nobla_agent/core/network/websocket_client.dart';
import 'package:nobla_agent/shared/models/rpc_error.dart';

/// Fake WebSocket client for testing JSON-RPC layer in isolation
class FakeWebSocketClient extends WebSocketClient {
  final sentMessages = <String>[];
  final _fakeMessageController = StreamController<String>.broadcast();

  @override
  Stream<String> get messageStream => _fakeMessageController.stream;

  @override
  ConnectionStatus get currentStatus => ConnectionStatus.connected;

  @override
  void send(String message) {
    sentMessages.add(message);
  }

  void simulateResponse(String json) {
    _fakeMessageController.add(json);
  }

  @override
  void dispose() {
    _fakeMessageController.close();
  }
}

void main() {
  late FakeWebSocketClient fakeWs;
  late JsonRpcClient rpc;

  setUp(() {
    fakeWs = FakeWebSocketClient();
    rpc = JsonRpcClient(fakeWs);
  });

  tearDown(() {
    rpc.dispose();
    fakeWs.dispose();
  });

  group('JsonRpcClient', () {
    test('call sends properly formatted JSON-RPC request', () async {
      final future = rpc.call('system.health', {});

      // Extract the sent message and respond
      await Future.delayed(const Duration(milliseconds: 10));
      expect(fakeWs.sentMessages, hasLength(1));
      final sent = jsonDecode(fakeWs.sentMessages.first) as Map<String, dynamic>;
      expect(sent['jsonrpc'], '2.0');
      expect(sent['method'], 'system.health');
      expect(sent['id'], isA<int>());

      // Simulate response
      fakeWs.simulateResponse(jsonEncode({
        'jsonrpc': '2.0',
        'id': sent['id'],
        'result': {'status': 'ok'},
      }));

      final result = await future;
      expect(result['status'], 'ok');
    });

    test('call throws RpcError on error response', () async {
      final future = rpc.call('chat.send', {'message': 'hi'});

      await Future.delayed(const Duration(milliseconds: 10));
      final sent = jsonDecode(fakeWs.sentMessages.first);

      fakeWs.simulateResponse(jsonEncode({
        'jsonrpc': '2.0',
        'id': sent['id'],
        'error': {'code': -32011, 'message': 'Auth required'},
      }));

      expect(() => future, throwsA(isA<RpcError>()));
    });

    test('notifications are delivered via notificationStream', () async {
      final notifications = <Map<String, dynamic>>[];
      rpc.notificationStream.listen(notifications.add);

      fakeWs.simulateResponse(jsonEncode({
        'jsonrpc': '2.0',
        'method': 'system.killed',
        'params': {'stage': 'soft'},
      }));

      await Future.delayed(const Duration(milliseconds: 10));
      expect(notifications, hasLength(1));
      expect(notifications.first['method'], 'system.killed');
    });

    test('auto-increments request IDs', () async {
      rpc.call('method1', {});
      rpc.call('method2', {});

      await Future.delayed(const Duration(milliseconds: 10));
      final id1 = jsonDecode(fakeWs.sentMessages[0])['id'] as int;
      final id2 = jsonDecode(fakeWs.sentMessages[1])['id'] as int;
      expect(id2, id1 + 1);
    });
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd app && flutter test test/core/network/jsonrpc_client_test.dart
```
Expected: FAIL — class doesn't exist

- [ ] **Step 3: Implement JSON-RPC client**

Create `app/lib/core/network/jsonrpc_client.dart`:
```dart
import 'dart:async';
import 'dart:convert';
import 'package:nobla_agent/core/network/websocket_client.dart';
import 'package:nobla_agent/shared/models/rpc_error.dart';

class JsonRpcClient {
  final WebSocketClient _ws;
  int _nextId = 1;
  final _pendingCalls = <int, Completer<Map<String, dynamic>>>{};
  final _notificationController =
      StreamController<Map<String, dynamic>>.broadcast();
  StreamSubscription? _messageSubscription;

  JsonRpcClient(this._ws) {
    _messageSubscription = _ws.messageStream.listen(_handleMessage);
  }

  Stream<Map<String, dynamic>> get notificationStream =>
      _notificationController.stream;

  Future<Map<String, dynamic>> call(
    String method, [
    Map<String, dynamic> params = const {},
    Duration timeout = const Duration(seconds: 30),
  ]) {
    final id = _nextId++;
    final request = {
      'jsonrpc': '2.0',
      'method': method,
      'params': params,
      'id': id,
    };

    final completer = Completer<Map<String, dynamic>>();
    _pendingCalls[id] = completer;

    _ws.send(jsonEncode(request));

    // Timeout handling
    return completer.future.timeout(timeout, onTimeout: () {
      _pendingCalls.remove(id);
      throw RpcError(code: -32000, message: 'Request timed out');
    });
  }

  void _handleMessage(String raw) {
    try {
      final json = jsonDecode(raw) as Map<String, dynamic>;

      // Check if it's a response (has id)
      if (json.containsKey('id') && json['id'] != null) {
        final id = json['id'] as int;
        final completer = _pendingCalls.remove(id);
        if (completer == null) return;

        if (json.containsKey('error') && json['error'] != null) {
          completer.completeError(
            RpcError.fromJson(json['error'] as Map<String, dynamic>),
          );
        } else {
          completer.complete(
            json['result'] as Map<String, dynamic>? ?? {},
          );
        }
      } else if (json.containsKey('method')) {
        // Server-push notification (no id)
        _notificationController.add(json);
      }
    } catch (e) {
      // Ignore malformed messages
    }
  }

  void dispose() {
    _messageSubscription?.cancel();
    _notificationController.close();
    // Complete pending calls with error
    for (final completer in _pendingCalls.values) {
      completer.completeError(
        RpcError(code: -32000, message: 'Client disposed'),
      );
    }
    _pendingCalls.clear();
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd app && flutter test test/core/network/jsonrpc_client_test.dart
```
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add app/lib/core/network/jsonrpc_client.dart app/test/core/network/jsonrpc_client_test.dart
git commit -m "feat: add JSON-RPC 2.0 client with error mapping and notifications"
```

---

### Task 5: Config & Theme Providers

**Files:**
- Create: `app/lib/core/providers/config_provider.dart`
- Create: `app/lib/core/theme/app_theme.dart`

- [ ] **Step 1: Implement config provider**

Create `app/lib/core/providers/config_provider.dart`:
```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AppConfig {
  final String serverUrl;
  final String displayName;
  final bool isDarkMode;

  const AppConfig({
    this.serverUrl = 'ws://localhost:8000/ws',
    this.displayName = 'User',
    this.isDarkMode = true,
  });

  AppConfig copyWith({String? serverUrl, String? displayName, bool? isDarkMode}) {
    return AppConfig(
      serverUrl: serverUrl ?? this.serverUrl,
      displayName: displayName ?? this.displayName,
      isDarkMode: isDarkMode ?? this.isDarkMode,
    );
  }
}

class ConfigNotifier extends StateNotifier<AppConfig> {
  ConfigNotifier() : super(const AppConfig());

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    state = AppConfig(
      serverUrl: prefs.getString('server_url') ?? 'ws://localhost:8000/ws',
      displayName: prefs.getString('display_name') ?? 'User',
      isDarkMode: prefs.getBool('is_dark_mode') ?? true,
    );
  }

  Future<void> setServerUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('server_url', url);
    state = state.copyWith(serverUrl: url);
  }

  Future<void> setDisplayName(String name) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('display_name', name);
    state = state.copyWith(displayName: name);
  }

  Future<void> setDarkMode(bool dark) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('is_dark_mode', dark);
    state = state.copyWith(isDarkMode: dark);
  }
}

final configProvider = StateNotifierProvider<ConfigNotifier, AppConfig>((ref) {
  return ConfigNotifier();
});
```

- [ ] **Step 2: Implement app theme**

Create `app/lib/core/theme/app_theme.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppTheme {
  static const _primaryColor = Color(0xFF1565C0);
  static const _accentColor = Color(0xFF00BCD4);
  static const _errorColor = Color(0xFFF44336);
  static const _warningColor = Color(0xFFFFC107);
  static const _successColor = Color(0xFF4CAF50);

  static Color get warningColor => _warningColor;
  static Color get successColor => _successColor;
  static Color get accentColor => _accentColor;

  static ThemeData get darkTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: ColorScheme.dark(
        primary: _primaryColor,
        secondary: _accentColor,
        error: _errorColor,
        surface: const Color(0xFF1E1E1E),
      ),
      scaffoldBackgroundColor: const Color(0xFF121212),
      textTheme: GoogleFonts.interTextTheme(ThemeData.dark().textTheme),
      floatingActionButtonTheme: const FloatingActionButtonThemeData(
        backgroundColor: _errorColor,
        foregroundColor: Colors.white,
      ),
      inputDecorationTheme: InputDecorationTheme(
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
        filled: true,
        fillColor: const Color(0xFF2A2A2A),
      ),
      cardTheme: CardTheme(
        color: const Color(0xFF1E1E1E),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        elevation: 2,
      ),
    );
  }

  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: ColorScheme.light(
        primary: _primaryColor,
        secondary: _accentColor,
        error: _errorColor,
      ),
      textTheme: GoogleFonts.interTextTheme(ThemeData.light().textTheme),
      inputDecorationTheme: InputDecorationTheme(
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
        filled: true,
      ),
      cardTheme: CardTheme(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        elevation: 2,
      ),
    );
  }
}
```

- [ ] **Step 3: Verify build**

```bash
cd app && flutter analyze
```

- [ ] **Step 4: Commit**

```bash
git add app/lib/core/providers/config_provider.dart app/lib/core/theme/app_theme.dart
git commit -m "feat: add config provider and Material 3 dark/light theme"
```

---

### Task 6: Auth Provider & Token Management

**Files:**
- Create: `app/lib/core/providers/auth_provider.dart`
- Create: `app/test/core/providers/auth_provider_test.dart`

- [ ] **Step 1: Write auth provider tests**

Create `app/test/core/providers/auth_provider_test.dart`:
```dart
import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';
import 'package:nobla_agent/core/network/websocket_client.dart';
import 'package:nobla_agent/core/providers/auth_provider.dart';

class FakeWebSocketClient extends WebSocketClient {
  final sentMessages = <String>[];
  final _fakeMessageController = StreamController<String>.broadcast();

  @override
  Stream<String> get messageStream => _fakeMessageController.stream;
  @override
  ConnectionStatus get currentStatus => ConnectionStatus.connected;
  @override
  void send(String message) => sentMessages.add(message);

  void respondToLast(Map<String, dynamic> result) {
    final sent = jsonDecode(sentMessages.last);
    _fakeMessageController.add(jsonEncode({
      'jsonrpc': '2.0',
      'id': sent['id'],
      'result': result,
    }));
  }

  @override
  void dispose() => _fakeMessageController.close();
}

void main() {
  late FakeWebSocketClient fakeWs;
  late JsonRpcClient rpc;
  late AuthNotifier auth;

  setUp(() {
    fakeWs = FakeWebSocketClient();
    rpc = JsonRpcClient(fakeWs);
    auth = AuthNotifier(rpc);
  });

  tearDown(() {
    rpc.dispose();
    fakeWs.dispose();
  });

  group('AuthNotifier', () {
    test('initial state is unauthenticated', () {
      expect(auth.state, isA<Unauthenticated>());
    });

    test('register sends system.register and updates state', () async {
      final future = auth.register('Test User', 'mypassphrase123');
      await Future.delayed(const Duration(milliseconds: 10));

      final sent = jsonDecode(fakeWs.sentMessages.last);
      expect(sent['method'], 'system.register');
      expect(sent['params']['display_name'], 'Test User');
      expect(sent['params']['passphrase'], 'mypassphrase123');

      fakeWs.respondToLast({
        'user_id': 'u-123',
        'display_name': 'Test User',
        'access_token': 'at-xxx',
        'refresh_token': 'rt-xxx',
      });

      await future;
      expect(auth.state, isA<Authenticated>());
      final authed = auth.state as Authenticated;
      expect(authed.userId, 'u-123');
      expect(authed.displayName, 'Test User');
    });

    test('logout resets state to unauthenticated', () async {
      // First register
      final future = auth.register('Test', 'mypassphrase123');
      await Future.delayed(const Duration(milliseconds: 10));
      fakeWs.respondToLast({
        'user_id': 'u-123',
        'display_name': 'Test',
        'access_token': 'at-xxx',
        'refresh_token': 'rt-xxx',
      });
      await future;

      auth.logout();
      expect(auth.state, isA<Unauthenticated>());
    });
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd app && flutter test test/core/providers/auth_provider_test.dart
```
Expected: FAIL

- [ ] **Step 3: Implement auth provider**

Create `app/lib/core/providers/auth_provider.dart`:
```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';

// --- Auth State ---

sealed class AuthState {}

class Unauthenticated extends AuthState {}

class Authenticated extends AuthState {
  final String userId;
  final String displayName;
  final int tier;
  final String accessToken;
  final String refreshToken;

  Authenticated({
    required this.userId,
    required this.displayName,
    this.tier = 1,
    required this.accessToken,
    required this.refreshToken,
  });

  Authenticated copyWith({int? tier}) {
    return Authenticated(
      userId: userId,
      displayName: displayName,
      tier: tier ?? this.tier,
      accessToken: accessToken,
      refreshToken: refreshToken,
    );
  }
}

// --- Auth Notifier ---

class AuthNotifier extends StateNotifier<AuthState> {
  final JsonRpcClient _rpc;

  AuthNotifier(this._rpc) : super(Unauthenticated());

  Future<void> register(String displayName, String passphrase) async {
    final result = await _rpc.call('system.register', {
      'display_name': displayName,
      'passphrase': passphrase,
    });

    if (result.containsKey('error')) {
      throw Exception(result['error']);
    }

    state = Authenticated(
      userId: result['user_id'] as String,
      displayName: result['display_name'] as String,
      accessToken: result['access_token'] as String,
      refreshToken: result['refresh_token'] as String,
    );
  }

  Future<void> login(String passphrase) async {
    final result = await _rpc.call('system.authenticate', {
      'passphrase': passphrase,
    });

    if (result['authenticated'] != true) {
      throw Exception(result['message'] ?? 'Authentication failed');
    }

    state = Authenticated(
      userId: result['user_id'] as String,
      displayName: 'User',
      accessToken: result['access_token'] as String? ?? '',
      refreshToken: result['refresh_token'] as String? ?? '',
    );
  }

  Future<void> loginWithToken(String token) async {
    final result = await _rpc.call('system.authenticate', {
      'token': token,
    });

    if (result['authenticated'] != true) {
      throw Exception(result['message'] ?? 'Token auth failed');
    }

    state = Authenticated(
      userId: result['user_id'] as String,
      displayName: 'User',
      tier: result['tier'] as int? ?? 1,
      accessToken: token,
      refreshToken: '',
    );
  }

  Future<void> refreshToken() async {
    final current = state;
    if (current is! Authenticated) return;

    final result = await _rpc.call('system.refresh', {
      'refresh_token': current.refreshToken,
    });

    if (result.containsKey('error')) return;

    state = Authenticated(
      userId: current.userId,
      displayName: current.displayName,
      tier: current.tier,
      accessToken: result['access_token'] as String,
      refreshToken: result['refresh_token'] as String,
    );
  }

  Future<void> escalate(int tier, [String? passphrase]) async {
    final params = <String, dynamic>{'tier': tier};
    if (passphrase != null) params['passphrase'] = passphrase;

    final result = await _rpc.call('system.escalate', params);

    if (result.containsKey('error')) {
      throw Exception(result['error']);
    }

    final current = state;
    if (current is Authenticated) {
      state = current.copyWith(tier: result['tier'] as int);
    }
  }

  void logout() {
    state = Unauthenticated();
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd app && flutter test test/core/providers/auth_provider_test.dart
```
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add app/lib/core/providers/auth_provider.dart app/test/core/providers/auth_provider_test.dart
git commit -m "feat: add auth provider with register, login, token refresh, escalation"
```

---

### Task 7: Notification Provider & Kill Switch State

**Files:**
- Create: `app/lib/core/providers/notification_provider.dart`

- [ ] **Step 1: Implement notification provider**

Create `app/lib/core/providers/notification_provider.dart`:
```dart
import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';

// --- Kill Switch State ---

enum KillState { running, softKilling, killed }

class KillSwitchNotifier extends StateNotifier<KillState> {
  KillSwitchNotifier() : super(KillState.running);

  void updateFromNotification(Map<String, dynamic> params) {
    final stage = params['stage'] as String?;
    if (stage == 'soft') {
      state = KillState.softKilling;
    } else if (stage == 'hard') {
      state = KillState.killed;
    }
  }

  void updateFromHealthResponse(String killState) {
    switch (killState) {
      case 'running':
        state = KillState.running;
      case 'soft_killing':
        state = KillState.softKilling;
      case 'killed':
        state = KillState.killed;
    }
  }

  void setRunning() => state = KillState.running;
}

final killSwitchProvider =
    StateNotifierProvider<KillSwitchNotifier, KillState>((ref) {
  return KillSwitchNotifier();
});

// --- Budget Warning State ---

class BudgetWarning {
  final String period;
  final double limit;
  final double spent;

  const BudgetWarning({
    required this.period,
    required this.limit,
    required this.spent,
  });
}

final budgetWarningProvider = StateProvider<BudgetWarning?>((ref) => null);

// --- Notification Dispatcher ---

class NotificationDispatcher {
  final Ref _ref;
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
    }
  }

  void dispose() {
    _subscription?.cancel();
  }
}
```

- [ ] **Step 2: Verify build**

```bash
cd app && flutter analyze
```

- [ ] **Step 3: Commit**

```bash
git add app/lib/core/providers/notification_provider.dart
git commit -m "feat: add notification provider for kill switch and budget warnings"
```

---

### Task 8: GoRouter Navigation with Auth Guard

**Files:**
- Create: `app/lib/core/routing/app_router.dart`
- Modify: `app/lib/main.dart`

- [ ] **Step 1: Implement app router**

Create `app/lib/core/routing/app_router.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/providers/auth_provider.dart';
import 'package:nobla_agent/features/auth/screens/login_screen.dart';
import 'package:nobla_agent/features/auth/screens/register_screen.dart';
import 'package:nobla_agent/features/chat/screens/chat_screen.dart';
import 'package:nobla_agent/features/dashboard/screens/dashboard_screen.dart';
import 'package:nobla_agent/features/settings/screens/settings_screen.dart';
import 'package:nobla_agent/shared/widgets/kill_switch_fab.dart';

final _rootNavigatorKey = GlobalKey<NavigatorState>();
final _shellNavigatorKey = GlobalKey<NavigatorState>();

GoRouter createRouter(Ref ref, AuthState authState) {
  return GoRouter(
    navigatorKey: _rootNavigatorKey,
    initialLocation: '/home/chat',
    redirect: (context, state) {
      final isAuthenticated = authState is Authenticated;
      final isAuthRoute =
          state.matchedLocation == '/login' || state.matchedLocation == '/register';

      if (!isAuthenticated && !isAuthRoute) return '/login';
      if (isAuthenticated && isAuthRoute) return '/home/chat';
      return null;
    },
    routes: [
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: '/register',
        builder: (context, state) => const RegisterScreen(),
      ),
      ShellRoute(
        navigatorKey: _shellNavigatorKey,
        builder: (context, state, child) {
          return HomeShell(child: child);
        },
        routes: [
          GoRoute(
            path: '/home/chat',
            builder: (context, state) => const ChatScreen(),
          ),
          GoRoute(
            path: '/home/dashboard',
            builder: (context, state) => const DashboardScreen(),
          ),
          GoRoute(
            path: '/home/settings',
            builder: (context, state) => const SettingsScreen(),
          ),
        ],
      ),
    ],
  );
}

class HomeShell extends StatelessWidget {
  final Widget child;
  const HomeShell({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: child,
      floatingActionButton: const KillSwitchFab(),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _calculateIndex(GoRouterState.of(context).matchedLocation),
        onDestinationSelected: (index) {
          switch (index) {
            case 0: context.go('/home/chat');
            case 1: context.go('/home/dashboard');
            case 2: context.go('/home/settings');
          }
        },
        destinations: const [
          NavigationDestination(icon: Icon(Icons.chat_bubble_outline), selectedIcon: Icon(Icons.chat_bubble), label: 'Chat'),
          NavigationDestination(icon: Icon(Icons.dashboard_outlined), selectedIcon: Icon(Icons.dashboard), label: 'Dashboard'),
          NavigationDestination(icon: Icon(Icons.settings_outlined), selectedIcon: Icon(Icons.settings), label: 'Settings'),
        ],
      ),
    );
  }

  int _calculateIndex(String location) {
    if (location.startsWith('/home/dashboard')) return 1;
    if (location.startsWith('/home/settings')) return 2;
    return 0;
  }
}
```

- [ ] **Step 2: Create stub screens (will be fleshed out in later tasks)**

Create `app/lib/features/auth/screens/login_screen.dart`:
```dart
import 'package:flutter/material.dart';

class LoginScreen extends StatelessWidget {
  const LoginScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(child: Text('Login - TODO')),
    );
  }
}
```

Create `app/lib/features/auth/screens/register_screen.dart`:
```dart
import 'package:flutter/material.dart';

class RegisterScreen extends StatelessWidget {
  const RegisterScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(child: Text('Register - TODO')),
    );
  }
}
```

Create `app/lib/features/chat/screens/chat_screen.dart`:
```dart
import 'package:flutter/material.dart';

class ChatScreen extends StatelessWidget {
  const ChatScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const Center(child: Text('Chat - TODO'));
  }
}
```

Create `app/lib/features/dashboard/screens/dashboard_screen.dart`:
```dart
import 'package:flutter/material.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const Center(child: Text('Dashboard - TODO'));
  }
}
```

Create `app/lib/features/settings/screens/settings_screen.dart`:
```dart
import 'package:flutter/material.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const Center(child: Text('Settings - TODO'));
  }
}
```

Create `app/lib/shared/widgets/kill_switch_fab.dart`:
```dart
import 'package:flutter/material.dart';

class KillSwitchFab extends StatelessWidget {
  const KillSwitchFab({super.key});

  @override
  Widget build(BuildContext context) {
    return FloatingActionButton(
      onPressed: () {},
      child: const Icon(Icons.stop),
    );
  }
}
```

- [ ] **Step 3: Update main.dart**

Replace `app/lib/main.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/providers/auth_provider.dart';
import 'package:nobla_agent/core/providers/config_provider.dart';
import 'package:nobla_agent/core/routing/app_router.dart';
import 'package:nobla_agent/core/theme/app_theme.dart';
import 'package:nobla_agent/core/network/websocket_client.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';

// --- Global providers ---

final websocketProvider = Provider<WebSocketClient>((ref) {
  final client = WebSocketClient();
  ref.onDispose(() => client.dispose());
  return client;
});

final jsonRpcProvider = Provider<JsonRpcClient>((ref) {
  final ws = ref.watch(websocketProvider);
  final client = JsonRpcClient(ws);
  ref.onDispose(() => client.dispose());
  return client;
});

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  final rpc = ref.watch(jsonRpcProvider);
  return AuthNotifier(rpc);
});

// --- App ---

void main() {
  runApp(const ProviderScope(child: NoblaApp()));
}

class NoblaApp extends ConsumerWidget {
  const NoblaApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authProvider);
    final config = ref.watch(configProvider);
    final router = createRouter(ref, authState);

    return MaterialApp.router(
      title: 'Nobla Agent',
      debugShowCheckedModeBanner: false,
      theme: config.isDarkMode ? AppTheme.darkTheme : AppTheme.lightTheme,
      routerConfig: router,
    );
  }
}
```

- [ ] **Step 4: Verify build**

```bash
cd app && flutter analyze
```

- [ ] **Step 5: Commit**

```bash
git add app/lib/
git commit -m "feat: add GoRouter navigation with auth guard, stub screens, and home shell"
```

---

### Task 9: Auth Screens (Login & Register)

**Files:**
- Modify: `app/lib/features/auth/screens/login_screen.dart`
- Modify: `app/lib/features/auth/screens/register_screen.dart`
- Create: `app/lib/shared/widgets/connection_indicator.dart`
- Create: `app/test/features/auth/auth_screen_test.dart`

- [ ] **Step 1: Write auth screen widget tests**

Create `app/test/features/auth/auth_screen_test.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/auth/screens/login_screen.dart';
import 'package:nobla_agent/features/auth/screens/register_screen.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

void main() {
  group('LoginScreen', () {
    testWidgets('shows passphrase field and connect button', (tester) async {
      await tester.pumpWidget(
        const ProviderScope(
          child: MaterialApp(home: LoginScreen()),
        ),
      );

      expect(find.text('Passphrase'), findsOneWidget);
      expect(find.text('Connect'), findsOneWidget);
      expect(find.text('Register'), findsOneWidget);
    });

    testWidgets('shows error for empty passphrase', (tester) async {
      await tester.pumpWidget(
        const ProviderScope(
          child: MaterialApp(home: LoginScreen()),
        ),
      );

      await tester.tap(find.text('Connect'));
      await tester.pumpAndSettle();

      expect(find.text('Passphrase is required'), findsOneWidget);
    });
  });

  group('RegisterScreen', () {
    testWidgets('shows all registration fields', (tester) async {
      await tester.pumpWidget(
        const ProviderScope(
          child: MaterialApp(home: RegisterScreen()),
        ),
      );

      expect(find.text('Display Name'), findsOneWidget);
      expect(find.text('Passphrase'), findsOneWidget);
      expect(find.text('Confirm Passphrase'), findsOneWidget);
      expect(find.text('Create Account'), findsOneWidget);
    });

    testWidgets('validates passphrase mismatch', (tester) async {
      await tester.pumpWidget(
        const ProviderScope(
          child: MaterialApp(home: RegisterScreen()),
        ),
      );

      await tester.enterText(find.byType(TextFormField).at(0), 'TestUser');
      await tester.enterText(find.byType(TextFormField).at(1), 'password123');
      await tester.enterText(find.byType(TextFormField).at(2), 'different123');
      await tester.tap(find.text('Create Account'));
      await tester.pumpAndSettle();

      expect(find.text('Passphrases do not match'), findsOneWidget);
    });
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd app && flutter test test/features/auth/auth_screen_test.dart
```
Expected: FAIL

- [ ] **Step 3: Implement connection indicator widget**

Create `app/lib/shared/widgets/connection_indicator.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/network/websocket_client.dart';

class ConnectionIndicator extends ConsumerWidget {
  const ConnectionIndicator({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // For now, just show a static indicator
    // Will be connected to WebSocket status stream in integration
    return Container(
      width: 10,
      height: 10,
      decoration: const BoxDecoration(
        color: Colors.grey,
        shape: BoxShape.circle,
      ),
    );
  }
}
```

- [ ] **Step 4: Implement login screen**

Replace `app/lib/features/auth/screens/login_screen.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:nobla_agent/core/theme/app_theme.dart';
import 'package:nobla_agent/main.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _passphraseController = TextEditingController();
  bool _obscure = true;
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _passphraseController.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() { _loading = true; _error = null; });

    try {
      await ref.read(authProvider.notifier).login(
        _passphraseController.text,
      );
    } catch (e) {
      setState(() { _error = e.toString(); });
    } finally {
      if (mounted) setState(() { _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(32),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 400),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.smart_toy, size: 64,
                      color: Theme.of(context).colorScheme.primary),
                  const SizedBox(height: 16),
                  Text('Nobla Agent',
                      style: Theme.of(context).textTheme.headlineMedium),
                  const SizedBox(height: 8),
                  Text('Privacy-first AI assistant',
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: Theme.of(context).colorScheme.onSurface.withAlpha(153))),
                  const SizedBox(height: 48),
                  TextFormField(
                    controller: _passphraseController,
                    obscureText: _obscure,
                    decoration: InputDecoration(
                      labelText: 'Passphrase',
                      prefixIcon: const Icon(Icons.lock_outline),
                      suffixIcon: IconButton(
                        icon: Icon(_obscure ? Icons.visibility_off : Icons.visibility),
                        onPressed: () => setState(() => _obscure = !_obscure),
                      ),
                    ),
                    validator: (v) =>
                        (v == null || v.isEmpty) ? 'Passphrase is required' : null,
                    onFieldSubmitted: (_) => _login(),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                  ],
                  const SizedBox(height: 24),
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: FilledButton(
                      onPressed: _loading ? null : _login,
                      child: _loading
                          ? const SizedBox(width: 20, height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2))
                          : const Text('Connect'),
                    ),
                  ),
                  const SizedBox(height: 16),
                  TextButton(
                    onPressed: () => context.go('/register'),
                    child: const Text('Register'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
```

- [ ] **Step 5: Implement register screen**

Replace `app/lib/features/auth/screens/register_screen.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:nobla_agent/main.dart';

class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _passphraseController = TextEditingController();
  final _confirmController = TextEditingController();
  bool _obscure = true;
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _nameController.dispose();
    _passphraseController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  Future<void> _register() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() { _loading = true; _error = null; });

    try {
      await ref.read(authProvider.notifier).register(
        _nameController.text,
        _passphraseController.text,
      );
    } catch (e) {
      setState(() { _error = e.toString(); });
    } finally {
      if (mounted) setState(() { _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go('/login'),
        ),
        title: const Text('Create Account'),
      ),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(32),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 400),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextFormField(
                    controller: _nameController,
                    decoration: const InputDecoration(
                      labelText: 'Display Name',
                      prefixIcon: Icon(Icons.person_outline),
                    ),
                    validator: (v) =>
                        (v == null || v.isEmpty) ? 'Name is required' : null,
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _passphraseController,
                    obscureText: _obscure,
                    decoration: InputDecoration(
                      labelText: 'Passphrase',
                      prefixIcon: const Icon(Icons.lock_outline),
                      suffixIcon: IconButton(
                        icon: Icon(_obscure ? Icons.visibility_off : Icons.visibility),
                        onPressed: () => setState(() => _obscure = !_obscure),
                      ),
                    ),
                    validator: (v) {
                      if (v == null || v.isEmpty) return 'Passphrase is required';
                      if (v.length < 8) return 'Minimum 8 characters';
                      return null;
                    },
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _confirmController,
                    obscureText: _obscure,
                    decoration: const InputDecoration(
                      labelText: 'Confirm Passphrase',
                      prefixIcon: Icon(Icons.lock_outline),
                    ),
                    validator: (v) {
                      if (v != _passphraseController.text) {
                        return 'Passphrases do not match';
                      }
                      return null;
                    },
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                  ],
                  const SizedBox(height: 24),
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: FilledButton(
                      onPressed: _loading ? null : _register,
                      child: _loading
                          ? const SizedBox(width: 20, height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2))
                          : const Text('Create Account'),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
```

- [ ] **Step 6: Run tests**

```bash
cd app && flutter test test/features/auth/auth_screen_test.dart
```
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add app/lib/features/auth/ app/lib/shared/widgets/connection_indicator.dart app/test/features/auth/
git commit -m "feat: add login and register screens with form validation"
```

---

### Task 10: Chat Provider & Screen

**Files:**
- Create: `app/lib/features/chat/providers/chat_provider.dart`
- Modify: `app/lib/features/chat/screens/chat_screen.dart`
- Create: `app/lib/features/chat/widgets/message_bubble.dart`
- Create: `app/lib/features/chat/widgets/message_input.dart`
- Create: `app/lib/features/chat/widgets/tool_activity_indicator.dart`
- Create: `app/test/features/chat/chat_provider_test.dart`

- [ ] **Step 1: Write chat provider tests**

Create `app/test/features/chat/chat_provider_test.dart`:
```dart
import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';
import 'package:nobla_agent/core/network/websocket_client.dart';
import 'package:nobla_agent/features/chat/providers/chat_provider.dart';
import 'package:nobla_agent/shared/models/chat_message.dart';

class FakeWebSocketClient extends WebSocketClient {
  final sentMessages = <String>[];
  final _fakeMessageController = StreamController<String>.broadcast();
  @override
  Stream<String> get messageStream => _fakeMessageController.stream;
  @override
  ConnectionStatus get currentStatus => ConnectionStatus.connected;
  @override
  void send(String message) => sentMessages.add(message);
  void respondToLast(Map<String, dynamic> result) {
    final sent = jsonDecode(sentMessages.last);
    _fakeMessageController.add(jsonEncode({
      'jsonrpc': '2.0', 'id': sent['id'], 'result': result,
    }));
  }
  @override
  void dispose() => _fakeMessageController.close();
}

void main() {
  late FakeWebSocketClient fakeWs;
  late JsonRpcClient rpc;
  late ChatNotifier chat;

  setUp(() {
    fakeWs = FakeWebSocketClient();
    rpc = JsonRpcClient(fakeWs);
    chat = ChatNotifier(rpc);
  });

  tearDown(() {
    rpc.dispose();
    fakeWs.dispose();
  });

  group('ChatNotifier', () {
    test('initial state has no messages', () {
      expect(chat.state.messages, isEmpty);
      expect(chat.state.isLoading, false);
    });

    test('sendMessage adds user message and agent response', () async {
      final future = chat.sendMessage('Hello');
      await Future.delayed(const Duration(milliseconds: 10));

      // User message should be added immediately
      expect(chat.state.messages, hasLength(1));
      expect(chat.state.messages.first.isUser, true);
      expect(chat.state.messages.first.content, 'Hello');
      expect(chat.state.isLoading, true);

      // Simulate response
      fakeWs.respondToLast({
        'message': 'Hi there!',
        'model': 'gemini-2.0-flash',
        'tokens_used': 50,
        'cost_usd': 0.0,
        'conversation_id': null,
      });

      await future;

      expect(chat.state.messages, hasLength(2));
      expect(chat.state.messages[1].isUser, false);
      expect(chat.state.messages[1].content, 'Hi there!');
      expect(chat.state.isLoading, false);
    });
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd app && flutter test test/features/chat/chat_provider_test.dart
```

- [ ] **Step 3: Implement chat provider**

Create `app/lib/features/chat/providers/chat_provider.dart`:
```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';
import 'package:nobla_agent/shared/models/chat_message.dart';

class ChatState {
  final List<ChatMessage> messages;
  final bool isLoading;
  final String conversationId;

  const ChatState({
    this.messages = const [],
    this.isLoading = false,
    String? conversationId,
  }) : conversationId = conversationId ?? '';

  ChatState copyWith({
    List<ChatMessage>? messages,
    bool? isLoading,
  }) {
    return ChatState(
      messages: messages ?? this.messages,
      isLoading: isLoading ?? this.isLoading,
      conversationId: conversationId,
    );
  }
}

class ChatNotifier extends StateNotifier<ChatState> {
  final JsonRpcClient _rpc;

  ChatNotifier(this._rpc)
      : super(ChatState(conversationId: const Uuid().v4()));

  Future<void> sendMessage(String text) async {
    final userMsg = ChatMessage.user(text);
    state = state.copyWith(
      messages: [...state.messages, userMsg],
      isLoading: true,
    );

    try {
      final result = await _rpc.call('chat.send', {
        'message': text,
        'conversation_id': state.conversationId,
      });

      final agentMsg = ChatMessage.fromRpcResponse(result, isUser: false);

      // Update user message status to sent
      final updatedMessages = state.messages.map((m) {
        if (m.id == userMsg.id) return m.copyWith(status: MessageStatus.sent);
        return m;
      }).toList();

      state = state.copyWith(
        messages: [...updatedMessages, agentMsg],
        isLoading: false,
      );
    } catch (e) {
      // Mark user message as error
      final updatedMessages = state.messages.map((m) {
        if (m.id == userMsg.id) return m.copyWith(status: MessageStatus.error);
        return m;
      }).toList();

      state = state.copyWith(
        messages: updatedMessages,
        isLoading: false,
      );
    }
  }

  void clearChat() {
    state = ChatState(conversationId: const Uuid().v4());
  }
}
```

- [ ] **Step 4: Implement message bubble widget**

Create `app/lib/features/chat/widgets/message_bubble.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:nobla_agent/shared/models/chat_message.dart';

class MessageBubble extends StatelessWidget {
  final ChatMessage message;
  const MessageBubble({super.key, required this.message});

  @override
  Widget build(BuildContext context) {
    final isUser = message.isUser;
    final scheme = Theme.of(context).colorScheme;

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.8,
        ),
        margin: const EdgeInsets.symmetric(vertical: 4, horizontal: 12),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: isUser ? scheme.primary.withAlpha(51) : scheme.surface,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(16),
            topRight: const Radius.circular(16),
            bottomLeft: Radius.circular(isUser ? 16 : 4),
            bottomRight: Radius.circular(isUser ? 4 : 16),
          ),
          border: Border.all(
            color: isUser ? scheme.primary.withAlpha(76) : scheme.outline.withAlpha(51),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (isUser)
              Text(message.content, style: Theme.of(context).textTheme.bodyMedium)
            else
              MarkdownBody(
                data: message.content,
                selectable: true,
                styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)),
              ),
            const SizedBox(height: 4),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (message.model != null) ...[
                  Text(message.model!,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: scheme.onSurface.withAlpha(102))),
                  const SizedBox(width: 8),
                ],
                if (message.status == MessageStatus.sending)
                  SizedBox(width: 12, height: 12,
                      child: CircularProgressIndicator(strokeWidth: 1.5,
                          color: scheme.onSurface.withAlpha(102))),
                if (message.status == MessageStatus.error)
                  Icon(Icons.error_outline, size: 14, color: scheme.error),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 5: Implement tool activity indicator**

Create `app/lib/features/chat/widgets/tool_activity_indicator.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:shimmer/shimmer.dart';

class ToolActivityIndicator extends StatelessWidget {
  final String text;
  const ToolActivityIndicator({super.key, this.text = 'Thinking...'});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4, horizontal: 12),
        padding: const EdgeInsets.all(12),
        child: Shimmer.fromColors(
          baseColor: Theme.of(context).colorScheme.onSurface.withAlpha(102),
          highlightColor: Theme.of(context).colorScheme.primary,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(width: 16, height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2)),
              const SizedBox(width: 8),
              Text(text, style: Theme.of(context).textTheme.bodyMedium),
            ],
          ),
        ),
      ),
    );
  }
}
```

- [ ] **Step 6: Implement message input widget**

Create `app/lib/features/chat/widgets/message_input.dart`:
```dart
import 'package:flutter/material.dart';

class MessageInput extends StatefulWidget {
  final ValueChanged<String> onSend;
  final bool enabled;
  const MessageInput({super.key, required this.onSend, this.enabled = true});

  @override
  State<MessageInput> createState() => _MessageInputState();
}

class _MessageInputState extends State<MessageInput> {
  final _controller = TextEditingController();

  void _send() {
    final text = _controller.text.trim();
    if (text.isEmpty) return;
    widget.onSend(text);
    _controller.clear();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        border: Border(top: BorderSide(
            color: Theme.of(context).colorScheme.outline.withAlpha(51))),
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _controller,
              enabled: widget.enabled,
              decoration: const InputDecoration(
                hintText: 'Message...',
                border: InputBorder.none,
                filled: false,
              ),
              maxLines: null,
              textInputAction: TextInputAction.send,
              onSubmitted: (_) => _send(),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.send),
            onPressed: widget.enabled ? _send : null,
            color: Theme.of(context).colorScheme.primary,
          ),
        ],
      ),
    );
  }
}
```

- [ ] **Step 7: Implement chat screen**

Replace `app/lib/features/chat/screens/chat_screen.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';
import 'package:nobla_agent/core/providers/notification_provider.dart';
import 'package:nobla_agent/features/chat/providers/chat_provider.dart';
import 'package:nobla_agent/features/chat/widgets/message_bubble.dart';
import 'package:nobla_agent/features/chat/widgets/message_input.dart';
import 'package:nobla_agent/features/chat/widgets/tool_activity_indicator.dart';
import 'package:nobla_agent/main.dart';

final chatProvider = StateNotifierProvider<ChatNotifier, ChatState>((ref) {
  final rpc = ref.watch(jsonRpcProvider);
  return ChatNotifier(rpc);
});

class ChatScreen extends ConsumerWidget {
  const ChatScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final chat = ref.watch(chatProvider);
    final killState = ref.watch(killSwitchProvider);
    final isKilled = killState != KillState.running;

    return Column(
      children: [
        AppBar(
          title: const Text('Chat'),
          centerTitle: true,
          actions: [
            IconButton(
              icon: const Icon(Icons.delete_outline),
              onPressed: () => ref.read(chatProvider.notifier).clearChat(),
              tooltip: 'Clear chat',
            ),
          ],
        ),
        Expanded(
          child: chat.messages.isEmpty
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.chat_bubble_outline, size: 64,
                          color: Theme.of(context).colorScheme.onSurface.withAlpha(76)),
                      const SizedBox(height: 16),
                      Text('Start a conversation',
                          style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                              color: Theme.of(context).colorScheme.onSurface.withAlpha(102))),
                    ],
                  ),
                )
              : ListView.builder(
                  reverse: true,
                  padding: const EdgeInsets.only(bottom: 8, top: 8),
                  itemCount: chat.messages.length + (chat.isLoading ? 1 : 0),
                  itemBuilder: (context, index) {
                    if (chat.isLoading && index == 0) {
                      return const ToolActivityIndicator();
                    }
                    final msgIndex = chat.isLoading
                        ? chat.messages.length - index
                        : chat.messages.length - 1 - index;
                    if (msgIndex < 0 || msgIndex >= chat.messages.length) {
                      return const SizedBox.shrink();
                    }
                    return MessageBubble(message: chat.messages[msgIndex]);
                  },
                ),
        ),
        MessageInput(
          enabled: !chat.isLoading && !isKilled,
          onSend: (text) => ref.read(chatProvider.notifier).sendMessage(text),
        ),
      ],
    );
  }
}
```

- [ ] **Step 8: Run tests**

```bash
cd app && flutter test test/features/chat/chat_provider_test.dart
```
Expected: ALL PASS

- [ ] **Step 9: Verify full build**

```bash
cd app && flutter analyze
```

- [ ] **Step 10: Commit**

```bash
git add app/lib/features/chat/ app/test/features/chat/
git commit -m "feat: add chat screen with message bubbles, markdown, and tool indicator"
```

---

### Task 11: Dashboard Screen (Connection, Security Tier, Cost Cards)

**Files:**
- Modify: `app/lib/features/dashboard/screens/dashboard_screen.dart`
- Create: `app/lib/features/dashboard/widgets/connection_card.dart`
- Create: `app/lib/features/dashboard/widgets/security_tier_card.dart`
- Create: `app/lib/features/dashboard/widgets/cost_card.dart`

- [ ] **Step 1: Implement connection card**

Create `app/lib/features/dashboard/widgets/connection_card.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:nobla_agent/core/theme/app_theme.dart';

class ConnectionCard extends StatelessWidget {
  final String serverUrl;
  final bool isConnected;
  final String serverVersion;

  const ConnectionCard({
    super.key,
    required this.serverUrl,
    this.isConnected = false,
    this.serverVersion = 'Unknown',
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.cloud_outlined),
                const SizedBox(width: 8),
                Text('Connection', style: Theme.of(context).textTheme.titleMedium),
              ],
            ),
            const Divider(),
            Row(
              children: [
                Container(
                  width: 10, height: 10,
                  decoration: BoxDecoration(
                    color: isConnected ? AppTheme.successColor : Colors.red,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 8),
                Text(isConnected ? 'Connected' : 'Disconnected'),
              ],
            ),
            const SizedBox(height: 8),
            Text('Server: $serverUrl',
                style: Theme.of(context).textTheme.bodySmall),
            Text('Version: $serverVersion',
                style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 2: Implement security tier card**

Create `app/lib/features/dashboard/widgets/security_tier_card.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:nobla_agent/core/theme/app_theme.dart';

class SecurityTierCard extends StatelessWidget {
  final int currentTier;
  final ValueChanged<int> onTierChange;

  const SecurityTierCard({
    super.key,
    required this.currentTier,
    required this.onTierChange,
  });

  static const _tierData = {
    1: ('SAFE', Icons.shield, Colors.green),
    2: ('STANDARD', Icons.shield, Colors.blue),
    3: ('ELEVATED', Icons.shield, Colors.amber),
    4: ('ADMIN', Icons.shield, Colors.red),
  };

  @override
  Widget build(BuildContext context) {
    final (name, icon, color) = _tierData[currentTier] ?? ('UNKNOWN', Icons.help, Colors.grey);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: color),
                const SizedBox(width: 8),
                Text('Security Tier', style: Theme.of(context).textTheme.titleMedium),
              ],
            ),
            const Divider(),
            Row(
              children: [
                Text(name, style: Theme.of(context).textTheme.headlineSmall?.copyWith(color: color)),
                const Spacer(),
                DropdownButton<int>(
                  value: currentTier,
                  items: _tierData.entries.map((e) {
                    final (n, _, c) = e.value;
                    return DropdownMenuItem(value: e.key,
                      child: Text(n, style: TextStyle(color: c)));
                  }).toList(),
                  onChanged: (v) { if (v != null) onTierChange(v); },
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 3: Implement cost card**

Create `app/lib/features/dashboard/widgets/cost_card.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:nobla_agent/core/theme/app_theme.dart';

class CostCard extends StatelessWidget {
  final Map<String, dynamic> costData;

  const CostCard({super.key, required this.costData});

  @override
  Widget build(BuildContext context) {
    final limits = costData['limits'] as Map<String, dynamic>? ?? {};

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.attach_money),
                const SizedBox(width: 8),
                Text('Cost Tracking', style: Theme.of(context).textTheme.titleMedium),
              ],
            ),
            const Divider(),
            _buildBar(context, 'Session',
                (costData['session_usd'] as num?)?.toDouble() ?? 0,
                (limits['session'] as num?)?.toDouble() ?? 1),
            const SizedBox(height: 8),
            _buildBar(context, 'Daily',
                (costData['daily_usd'] as num?)?.toDouble() ?? 0,
                (limits['daily'] as num?)?.toDouble() ?? 5),
            const SizedBox(height: 8),
            _buildBar(context, 'Monthly',
                (costData['monthly_usd'] as num?)?.toDouble() ?? 0,
                (limits['monthly'] as num?)?.toDouble() ?? 50),
          ],
        ),
      ),
    );
  }

  Widget _buildBar(BuildContext context, String label, double spent, double limit) {
    final ratio = limit > 0 ? (spent / limit).clamp(0.0, 1.0) : 0.0;
    final color = ratio >= 1.0
        ? Colors.red
        : ratio >= 0.8
            ? AppTheme.warningColor
            : AppTheme.successColor;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: Theme.of(context).textTheme.bodyMedium),
            Text('\$${spent.toStringAsFixed(2)} / \$${limit.toStringAsFixed(2)}',
                style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
        const SizedBox(height: 4),
        LinearProgressIndicator(
          value: ratio,
          backgroundColor: Theme.of(context).colorScheme.outline.withAlpha(51),
          color: color,
        ),
      ],
    );
  }
}
```

- [ ] **Step 4: Implement dashboard screen**

Replace `app/lib/features/dashboard/screens/dashboard_screen.dart`:
```dart
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/providers/auth_provider.dart';
import 'package:nobla_agent/core/providers/notification_provider.dart';
import 'package:nobla_agent/features/dashboard/widgets/connection_card.dart';
import 'package:nobla_agent/features/dashboard/widgets/security_tier_card.dart';
import 'package:nobla_agent/features/dashboard/widgets/cost_card.dart';
import 'package:nobla_agent/main.dart';

final costDashboardProvider = StateProvider<Map<String, dynamic>>((ref) => {});

class DashboardScreen extends ConsumerStatefulWidget {
  const DashboardScreen({super.key});

  @override
  ConsumerState<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends ConsumerState<DashboardScreen> {
  Timer? _refreshTimer;

  @override
  void initState() {
    super.initState();
    _fetchCosts();
    _refreshTimer = Timer.periodic(const Duration(seconds: 30), (_) => _fetchCosts());
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    super.dispose();
  }

  Future<void> _fetchCosts() async {
    try {
      final result = await ref.read(jsonRpcProvider).call('system.costs');
      ref.read(costDashboardProvider.notifier).state = result;
    } catch (_) {}
  }

  Future<void> _onTierChange(int tier) async {
    final authState = ref.read(authProvider);
    if (authState is! Authenticated) return;

    // Escalation requires passphrase for tier 3+
    String? passphrase;
    if (tier > authState.tier && tier >= 3) {
      passphrase = await _showPassphraseDialog();
      if (passphrase == null) return;
    }

    try {
      await ref.read(authProvider.notifier).escalate(tier, passphrase);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Escalation failed: $e')),
        );
      }
    }
  }

  Future<String?> _showPassphraseDialog() async {
    final controller = TextEditingController();
    return showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Passphrase Required'),
        content: TextField(
          controller: controller,
          obscureText: true,
          decoration: const InputDecoration(labelText: 'Passphrase'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, controller.text),
            child: const Text('Confirm'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authProvider);
    final killState = ref.watch(killSwitchProvider);
    final costs = ref.watch(costDashboardProvider);
    final config = ref.watch(configProvider);
    final currentTier = (authState is Authenticated) ? authState.tier : 1;

    return CustomScrollView(
      slivers: [
        const SliverAppBar(title: Text('Dashboard'), centerTitle: true, floating: true),
        SliverPadding(
          padding: const EdgeInsets.all(16),
          sliver: SliverList(
            delegate: SliverChildListDelegate([
              ConnectionCard(
                serverUrl: config.serverUrl,
                isConnected: true, // TODO: wire to WebSocket status
                serverVersion: '0.1.0',
              ),
              const SizedBox(height: 12),
              SecurityTierCard(
                currentTier: currentTier,
                onTierChange: _onTierChange,
              ),
              const SizedBox(height: 12),
              // Kill switch status card
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    children: [
                      Icon(
                        killState == KillState.running ? Icons.check_circle : Icons.warning,
                        color: killState == KillState.running ? Colors.green : Colors.red,
                      ),
                      const SizedBox(width: 8),
                      Text('Kill Switch: ${killState.name}',
                          style: Theme.of(context).textTheme.titleMedium),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              CostCard(costData: costs),
            ]),
          ),
        ),
      ],
    );
  }
}
```

- [ ] **Step 5: Verify build**

```bash
cd app && flutter analyze
```

- [ ] **Step 6: Commit**

```bash
git add app/lib/features/dashboard/
git commit -m "feat: add dashboard with connection, security tier, cost cards"
```

---

### Task 12: Settings Screen

**Files:**
- Modify: `app/lib/features/settings/screens/settings_screen.dart`
- Create: `app/lib/features/settings/providers/settings_provider.dart`

- [ ] **Step 1: Implement settings screen**

Replace `app/lib/features/settings/screens/settings_screen.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/providers/config_provider.dart';
import 'package:nobla_agent/main.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  late TextEditingController _urlController;
  late TextEditingController _nameController;

  @override
  void initState() {
    super.initState();
    final config = ref.read(configProvider);
    _urlController = TextEditingController(text: config.serverUrl);
    _nameController = TextEditingController(text: config.displayName);
  }

  @override
  void dispose() {
    _urlController.dispose();
    _nameController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final config = ref.watch(configProvider);

    return CustomScrollView(
      slivers: [
        const SliverAppBar(title: Text('Settings'), centerTitle: true, floating: true),
        SliverPadding(
          padding: const EdgeInsets.all(16),
          sliver: SliverList(
            delegate: SliverChildListDelegate([
              // Server URL
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Server', style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _urlController,
                        decoration: const InputDecoration(
                          labelText: 'Server URL',
                          prefixIcon: Icon(Icons.dns_outlined),
                        ),
                        onSubmitted: (v) =>
                            ref.read(configProvider.notifier).setServerUrl(v),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),

              // Display Name
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Profile', style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _nameController,
                        decoration: const InputDecoration(
                          labelText: 'Display Name',
                          prefixIcon: Icon(Icons.person_outline),
                        ),
                        onSubmitted: (v) =>
                            ref.read(configProvider.notifier).setDisplayName(v),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),

              // Theme
              Card(
                child: SwitchListTile(
                  title: const Text('Dark Mode'),
                  secondary: const Icon(Icons.dark_mode),
                  value: config.isDarkMode,
                  onChanged: (v) =>
                      ref.read(configProvider.notifier).setDarkMode(v),
                ),
              ),
              const SizedBox(height: 12),

              // Logout
              Card(
                child: ListTile(
                  leading: const Icon(Icons.logout, color: Colors.red),
                  title: const Text('Logout', style: TextStyle(color: Colors.red)),
                  onTap: () => ref.read(authProvider.notifier).logout(),
                ),
              ),
              const SizedBox(height: 24),

              // About
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    children: [
                      Text('Nobla Agent v0.1.0',
                          style: Theme.of(context).textTheme.titleSmall),
                      const SizedBox(height: 4),
                      Text('Privacy-first AI super agent',
                          style: Theme.of(context).textTheme.bodySmall),
                      const SizedBox(height: 4),
                      Text('nabilnet.ai',
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: Theme.of(context).colorScheme.primary)),
                    ],
                  ),
                ),
              ),
            ]),
          ),
        ),
      ],
    );
  }
}
```

- [ ] **Step 2: Verify build**

```bash
cd app && flutter analyze
```

- [ ] **Step 3: Commit**

```bash
git add app/lib/features/settings/
git commit -m "feat: add settings screen with server URL, theme toggle, logout"
```

---

### Task 13: Kill Switch FAB (Full Implementation)

**Files:**
- Modify: `app/lib/shared/widgets/kill_switch_fab.dart`

- [ ] **Step 1: Implement full kill switch FAB**

Replace `app/lib/shared/widgets/kill_switch_fab.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/providers/notification_provider.dart';
import 'package:nobla_agent/main.dart';

class KillSwitchFab extends ConsumerWidget {
  const KillSwitchFab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final killState = ref.watch(killSwitchProvider);

    return switch (killState) {
      KillState.running => _RunningFab(ref: ref),
      KillState.softKilling => _SoftKillingFab(ref: ref),
      KillState.killed => _KilledFab(ref: ref),
    };
  }
}

class _RunningFab extends StatelessWidget {
  final WidgetRef ref;
  const _RunningFab({required this.ref});

  @override
  Widget build(BuildContext context) {
    return FloatingActionButton(
      backgroundColor: Colors.red,
      onPressed: () => _confirmKill(context),
      tooltip: 'Emergency Stop',
      child: const Icon(Icons.stop, color: Colors.white),
    );
  }

  void _confirmKill(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Emergency Stop'),
        content: const Text('Halt all agent operations?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () {
              Navigator.pop(ctx);
              ref.read(jsonRpcProvider).call('system.kill');
              ref.read(killSwitchProvider.notifier).updateFromNotification({'stage': 'soft'});
            },
            child: const Text('Kill'),
          ),
        ],
      ),
    );
  }
}

class _SoftKillingFab extends StatefulWidget {
  final WidgetRef ref;
  const _SoftKillingFab({required this.ref});

  @override
  State<_SoftKillingFab> createState() => _SoftKillingFabState();
}

class _SoftKillingFabState extends State<_SoftKillingFab>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return FloatingActionButton(
          backgroundColor: Color.lerp(Colors.amber, Colors.red, _controller.value),
          onPressed: () {
            // Second press = hard kill
            widget.ref.read(jsonRpcProvider).call('system.kill');
          },
          tooltip: 'Force Kill',
          child: const Icon(Icons.warning, color: Colors.white),
        );
      },
    );
  }
}

class _KilledFab extends StatelessWidget {
  final WidgetRef ref;
  const _KilledFab({required this.ref});

  @override
  Widget build(BuildContext context) {
    return FloatingActionButton(
      backgroundColor: Colors.green,
      onPressed: () => _confirmResume(context),
      tooltip: 'Resume',
      child: const Icon(Icons.play_arrow, color: Colors.white),
    );
  }

  void _confirmResume(BuildContext context) {
    final controller = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Resume Agent'),
        content: TextField(
          controller: controller,
          obscureText: true,
          decoration: const InputDecoration(labelText: 'Passphrase'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
            onPressed: () {
              Navigator.pop(ctx);
              ref.read(jsonRpcProvider).call('system.resume', {
                'passphrase': controller.text,
              });
              ref.read(killSwitchProvider.notifier).setRunning();
            },
            child: const Text('Resume'),
          ),
        ],
      ),
    );
  }
}
```

- [ ] **Step 2: Verify build**

```bash
cd app && flutter analyze
```

- [ ] **Step 3: Commit**

```bash
git add app/lib/shared/widgets/kill_switch_fab.dart
git commit -m "feat: add full kill switch FAB with confirm, pulse animation, resume"
```

---

### Task 14: Widget Tests

**Files:**
- Create: `app/test/features/chat/chat_screen_test.dart`
- Create: `app/test/features/dashboard/dashboard_screen_test.dart`

- [ ] **Step 1: Write chat screen widget test**

Create `app/test/features/chat/chat_screen_test.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/chat/widgets/message_bubble.dart';
import 'package:nobla_agent/features/chat/widgets/message_input.dart';
import 'package:nobla_agent/shared/models/chat_message.dart';

void main() {
  group('MessageBubble', () {
    testWidgets('renders user message on the right', (tester) async {
      final msg = ChatMessage.user('Hello');

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: MessageBubble(message: msg)),
      ));

      final align = tester.widget<Align>(find.byType(Align).first);
      expect(align.alignment, Alignment.centerRight);
      expect(find.text('Hello'), findsOneWidget);
    });

    testWidgets('renders agent message with markdown', (tester) async {
      final msg = ChatMessage(
        id: '1', content: '**Bold** text', isUser: false,
        timestamp: DateTime.now(),
      );

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: MessageBubble(message: msg)),
      ));

      final align = tester.widget<Align>(find.byType(Align).first);
      expect(align.alignment, Alignment.centerLeft);
    });
  });

  group('MessageInput', () {
    testWidgets('calls onSend with text and clears field', (tester) async {
      String? sent;
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: MessageInput(onSend: (t) => sent = t)),
      ));

      await tester.enterText(find.byType(TextField), 'Test message');
      await tester.tap(find.byIcon(Icons.send));
      await tester.pump();

      expect(sent, 'Test message');
    });

    testWidgets('disabled state prevents input', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: MessageInput(onSend: (_) {}, enabled: false)),
      ));

      final field = tester.widget<TextField>(find.byType(TextField));
      expect(field.enabled, false);
    });
  });
}
```

- [ ] **Step 2: Write dashboard widget test**

Create `app/test/features/dashboard/dashboard_screen_test.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/dashboard/widgets/connection_card.dart';
import 'package:nobla_agent/features/dashboard/widgets/security_tier_card.dart';
import 'package:nobla_agent/features/dashboard/widgets/cost_card.dart';

void main() {
  group('ConnectionCard', () {
    testWidgets('shows connected status', (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(body: ConnectionCard(
          serverUrl: 'ws://localhost:8000/ws',
          isConnected: true,
          serverVersion: '0.1.0',
        )),
      ));

      expect(find.text('Connected'), findsOneWidget);
      expect(find.text('Server: ws://localhost:8000/ws'), findsOneWidget);
    });
  });

  group('SecurityTierCard', () {
    testWidgets('displays current tier', (tester) async {
      int? changed;
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: SecurityTierCard(
          currentTier: 1,
          onTierChange: (t) => changed = t,
        )),
      ));

      expect(find.text('SAFE'), findsOneWidget);
    });
  });

  group('CostCard', () {
    testWidgets('shows cost progress bars', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: CostCard(costData: {
          'session_usd': 0.5,
          'daily_usd': 2.0,
          'monthly_usd': 10.0,
          'limits': {'session': 1.0, 'daily': 5.0, 'monthly': 50.0},
        })),
      ));

      expect(find.text('Session'), findsOneWidget);
      expect(find.text('Daily'), findsOneWidget);
      expect(find.text('Monthly'), findsOneWidget);
      expect(find.byType(LinearProgressIndicator), findsNWidgets(3));
    });
  });
}
```

- [ ] **Step 3: Run all tests**

```bash
cd app && flutter test
```
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add app/test/
git commit -m "test: add widget tests for chat, dashboard, and auth screens"
```

---

### Task 15: Final Integration — Wire Up WebSocket Connection

**Files:**
- Modify: `app/lib/main.dart`

- [ ] **Step 1: Update main.dart to connect WebSocket on auth and set up notifications**

Update `app/lib/main.dart` — add WebSocket auto-connect logic:

After the existing `authProvider` definition, add connection logic in the `NoblaApp` widget's build method. The `NoblaApp` should call `ref.listen(authProvider, ...)` to trigger WebSocket connection when auth state changes to Authenticated, and set up the notification dispatcher.

```dart
// Add to NoblaApp build method, before return MaterialApp.router:
ref.listen(authProvider, (prev, next) {
  if (next is Authenticated && prev is! Authenticated) {
    final ws = ref.read(websocketProvider);
    final config = ref.read(configProvider);
    ws.connect(config.serverUrl);

    // Set up notification dispatcher
    final rpc = ref.read(jsonRpcProvider);
    NotificationDispatcher(ref).listen(rpc);
  }
  if (next is Unauthenticated && prev is Authenticated) {
    ref.read(websocketProvider).disconnect();
  }
});
```

Add import for `NotificationDispatcher`:
```dart
import 'package:nobla_agent/core/providers/notification_provider.dart';
```

- [ ] **Step 2: Verify full build and run all tests**

```bash
cd app && flutter analyze && flutter test
```

- [ ] **Step 3: Verify web build works**

```bash
cd app && flutter build web
```

- [ ] **Step 4: Commit**

```bash
git add app/lib/main.dart
git commit -m "feat: wire WebSocket auto-connect on auth and notification dispatcher"
```

---

## Summary

| Task | Description | Tests |
|------|------------|-------|
| 1 | Flutter project scaffold | Build verification |
| 2 | Shared models (RpcError, ChatMessage, UserModel) | 6 unit tests |
| 3 | WebSocket client | 4 unit tests |
| 4 | JSON-RPC client | 4 unit tests |
| 5 | Config & theme providers | Build verification |
| 6 | Auth provider | 3 unit tests |
| 7 | Notification provider | Build verification |
| 8 | GoRouter navigation + stub screens | Build verification |
| 9 | Auth screens (login, register) | 4 widget tests |
| 10 | Chat provider + screen + widgets | 2 unit + build |
| 11 | Dashboard screen + cards | Build verification |
| 12 | Settings screen | Build verification |
| 13 | Kill switch FAB | Build verification |
| 14 | Widget tests | 7 widget tests |
| 15 | WebSocket integration wiring | Full build + web |

**Total: 15 tasks, ~30 tests, 15 commits**

## Acceptance Criteria

- [ ] `flutter analyze` passes with no errors
- [ ] `flutter test` passes all tests with 70%+ coverage
- [ ] `flutter build web` succeeds
- [ ] App connects to backend via WebSocket, authenticates, and sends/receives chat messages
- [ ] Kill switch FAB visible on all screens, triggers kill/resume flow
- [ ] Dashboard shows security tier, cost tracking, connection status
- [ ] Auth guard redirects unauthenticated users to login
- [ ] Dark theme is default, light theme toggle works

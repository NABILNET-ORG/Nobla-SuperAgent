# Phase 1C: Flutter Mobile App — Design Spec

**Date:** 2026-03-17
**Phase:** 1C of 7-phase roadmap
**Depends on:** Phase 1A (Backend Foundation), Phase 1B (Security & Auth)
**Platforms:** Android, iOS, Web (Flutter Web)

---

## 1. Overview

Build a Flutter 3.x cross-platform app (Android + iOS + Web) that connects to the Nobla backend via WebSocket JSON-RPC 2.0. The app provides authentication, real-time chat with rich message rendering, a security dashboard, cost monitoring, and an always-accessible kill switch.

**Approach:** Infrastructure-first (horizontal layers) — build WebSocket client, JSON-RPC protocol layer, and auth state first, then feature screens on top.

## 2. Project Structure

```
app/
├── lib/
│   ├── main.dart                        # Entry point, ProviderScope
│   ├── core/
│   │   ├── theme/
│   │   │   └── app_theme.dart           # Material 3 dark-first theme
│   │   ├── routing/
│   │   │   └── app_router.dart          # GoRouter with auth guard
│   │   ├── network/
│   │   │   ├── websocket_client.dart    # WebSocket connection manager
│   │   │   └── jsonrpc_client.dart      # JSON-RPC 2.0 protocol layer
│   │   └── providers/
│   │       ├── auth_provider.dart       # Auth state + token management
│   │       ├── config_provider.dart     # Server URL + app config
│   │       └── notification_provider.dart # Server-push notification dispatcher
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
│       │   └── chat_screen_test.dart
│       └── dashboard/
│           └── dashboard_screen_test.dart
├── web/
├── android/
├── ios/
└── pubspec.yaml
```

## 3. Core Infrastructure Layer

### 3.1 WebSocket Client (`websocket_client.dart`)

Manages the raw WebSocket connection lifecycle.

**Responsibilities:**
- Connect to `ws://<server>/ws` (or `wss://` for TLS)
- Auto-reconnect with exponential backoff: 1s → 2s → 4s → ... → max 30s
- Heartbeat ping every 30s to detect stale connections
- On reconnect, notify listeners so auth layer can re-authenticate
- Expose connection state as Riverpod stream

**Connection States:**
```dart
enum ConnectionStatus { disconnected, connecting, connected, error }
```

**Interface:**
```dart
class WebSocketClient {
  Stream<ConnectionStatus> get statusStream;
  ConnectionStatus get currentStatus;
  Future<void> connect(String url);
  void disconnect();
  void send(String message);
  Stream<String> get messageStream;
}
```

### 3.2 JSON-RPC Client (`jsonrpc_client.dart`)

Protocol layer on top of WebSocket, matching the backend's JSON-RPC 2.0 format.

**Responsibilities:**
- Auto-increment request IDs
- Match responses to pending `Completer<Map>` futures by ID
- Timeout per call (default 30s)
- Parse error codes into typed exceptions
- Deliver server-push notifications (messages without `id`) via separate stream

**Error Code Mapping:**
| Code | Exception | Backend Constant |
|------|-----------|-----------------|
| -32011 | `AuthRequiredException` | `AUTH_REQUIRED` |
| -32012 | `AuthFailedException` | `AUTH_FAILED` |
| -32013 | `TokenExpiredException` | `TOKEN_EXPIRED` |
| -32010 | `PermissionDeniedException` | `PERMISSION_DENIED` |
| -32020 | `BudgetExceededException` | `BUDGET_EXCEEDED` |
| -32030 | `ServerKilledException` | `SERVER_KILLED` |
| -32700 | `ParseErrorException` | `PARSE_ERROR` |
| -32601 | `MethodNotFoundException` | `METHOD_NOT_FOUND` |
| -32603 | `InternalErrorException` | `INTERNAL_ERROR` |

**Interface:**
```dart
class JsonRpcClient {
  Future<Map<String, dynamic>> call(String method, [Map<String, dynamic> params = const {}]);
  Stream<Map<String, dynamic>> get notificationStream;
}
```

### 3.2.1 Server-Push Notification Handling

The backend pushes notifications (JSON-RPC messages without `id`) for real-time events. A dedicated `NotificationProvider` subscribes to `notificationStream` and dispatches to feature providers:

| Notification Method | Consumer | Action |
|---|---|---|
| `system.killed` | Kill switch FAB | Update kill state immediately (no polling needed) |
| `system.budget_warning` | Cost card / toast | Show warning banner or snackbar with budget details |

The `NotificationProvider` is initialized at app startup and listens for the app's lifetime. It uses Riverpod `ref.read()` to update the appropriate feature providers when notifications arrive.

### 3.3 Auth Provider (`auth_provider.dart`)

Manages authentication state and token lifecycle.

**State:**
```dart
sealed class AuthState {}
class Unauthenticated extends AuthState {}
class Authenticated extends AuthState {
  final String userId;
  final String displayName;
  final int tier;
  final String accessToken;
  final String refreshToken;
}
```

**Token Storage:**
- Mobile: `flutter_secure_storage` (Keychain on iOS, EncryptedSharedPreferences on Android)
- Web: `flutter_secure_storage` with web adapter (uses `localStorage` under the hood — tokens are accessible to same-origin JS; acceptable for Phase 1 since the app is self-hosted and single-user; TLS mitigates network exposure)

**Auto-refresh:** Decodes JWT expiry, schedules refresh 5 minutes before expiration via `Timer`.

**Methods:**
- `register(String displayName, String passphrase)` → calls `system.register` with `{display_name, passphrase}`
- `login(String passphrase)` → calls `system.authenticate` with `{passphrase}` (Phase 1B is single-user, no username needed)
- `loginWithToken()` → calls `system.authenticate` with `{token}` (stored access token, for reconnect)
- `refreshToken()` → calls `system.refresh` with `{refresh_token}`
- `escalate(int tier, [String? passphrase])` → calls `system.escalate` with `{tier, passphrase?}`
- `logout()` → clears tokens, resets state

### 3.4 Config Provider (`config_provider.dart`)

**Persisted settings** (SharedPreferences):
- `serverUrl` — default `ws://localhost:8000/ws`
- `displayName` — user's chosen name
- `themeMode` — `dark` (default) / `light`

## 4. Feature Screens

### 4.1 Auth — Login & Registration

**Login Screen:**
- Passphrase field (obscured) — Phase 1B is single-user, no username needed
- "Connect" button → calls `system.authenticate` with `{passphrase}`
- "Register" text button → navigates to register screen
- Server URL shown as tappable subtitle (opens settings)
- Connection status indicator (green/red dot)
- Error display for invalid credentials, server unreachable
- Note: Username field will be added in Phase 5 (multi-user support)

**Register Screen:**
- Display name + passphrase + confirm passphrase
- Client-side validation: passphrase min 8 chars, confirmation match
- "Create Account" button → calls `system.register` with `{display_name, passphrase}`
- On success → auto-login → navigate to Chat tab

### 4.2 Chat — Real-time Messaging

**Chat Screen:**
- Reversed `ListView.builder` for message list
- User messages: right-aligned, accent color bubbles
- Agent messages: left-aligned, surface color bubbles with:
  - Markdown rendering (`flutter_markdown`)
  - Code blocks with syntax highlighting (`flutter_highlight`)
  - Tool activity indicator: shimmer animation with text ("Thinking...", "Searching...")
- Messages stored locally in provider state (not persisted across sessions — server-side persistence comes in Phase 2)

**Message Input Bar:**
- `TextField` with send `IconButton`
- Disabled when: disconnected, killed state, or awaiting response
- Send action calls `chat.send` via JSON-RPC

**Chat Provider:**
```dart
class ChatMessage {
  final String id;
  final String content;
  final bool isUser;
  final DateTime timestamp;
  final String? model;
  final int? tokensUsed;    // maps from backend's `tokens_used`
  final double? costUsd;     // maps from backend's `cost_usd`
  final MessageStatus status; // sending, sent, error

  factory ChatMessage.fromRpcResponse(Map<String, dynamic> json) {
    // Maps snake_case backend response to camelCase Dart fields
  }
}
```

**Conversation lifecycle:**
- On first message, a `conversationId` is generated client-side (UUID) and passed to every `chat.send` call
- The backend's `conversation.create` / `conversation.list` / `chat.history` methods exist in Phase 1A but are **deferred to Phase 2** for UI integration (conversation switching, history browsing)
- Phase 1C maintains a single active conversation per session

### 4.3 Dashboard — Status & Security

**Connection Card:**
- Server URL display
- Connection status with colored indicator
- Latency (measured from `system.health` round-trip)

**Security Tier Card:**
- Current tier displayed with icon and color coding:
  - SAFE (1) — green shield
  - STANDARD (2) — blue shield
  - ELEVATED (3) — amber shield
  - ADMIN (4) — red shield
- Tier selector: dropdown or segmented control
- Escalation: tapping a higher tier shows passphrase dialog, calls `system.escalate`
- De-escalation: immediate, no confirmation needed

**Cost Card:**
- Four progress bars: session / daily / weekly / monthly spend vs limits
- Maps from backend response: `session_usd`, `daily_usd`, `week_usd`, `monthly_usd`
- Color coding: green (<80%), amber (80-99%), red (>=100%)
- Numbers displayed as `$X.XX / $Y.YY`
- Auto-refreshes via `system.costs` every 30s
- Budget warnings from server-push notifications displayed as snackbar alerts

**System Status** (from `system.status`):
- Server version and current phase displayed in Connection Card
- Provider list shown when available (deferred detail until Phase 2 when provider management UI is built)

### 4.4 Settings

- **Server URL** — text field, validates URL format, reconnects on save
- **Display name** — text field
- **Theme** — toggle switch (dark/light)
- **About** — app version, "Powered by Nobla Agent", link to [NABILNET.AI](https://nabilnet.ai)

### 4.5 Kill Switch FAB

- **Always visible** — floating action button on all tabs (positioned bottom-right, above bottom nav)
- **Normal state (Running):** Red FAB with stop icon. Tap → confirmation dialog ("Emergency stop — halt all agent operations?") → calls `system.kill`
- **Soft Killing state:** Pulsing amber FAB with warning icon. Shows countdown text. Tap → immediate hard kill (second `system.kill` call)
- **Killed state:** Green FAB with play icon. Tap → passphrase confirmation dialog (backend requires passphrase re-entry for resume) → calls `system.resume` with `{passphrase}`
- State synced reactively via `system.killed` server-push notifications (no polling). Initial state fetched from `system.health` response's `kill_state` field on connect.

## 5. Navigation & Routing

**GoRouter** configuration with auth redirect guard:

```
/ → redirect based on auth state
/login → LoginScreen
/register → RegisterScreen
/home → ShellRoute (bottom nav)
  /home/chat → ChatScreen
  /home/dashboard → DashboardScreen
  /home/settings → SettingsScreen
```

**Auth guard:** If `AuthState` is `Unauthenticated`, redirect to `/login`. If `Authenticated`, redirect `/login` to `/home/chat`.

**Bottom Navigation:** 3 tabs — Chat (message icon), Dashboard (dashboard icon), Settings (gear icon).

## 6. Dependencies

```yaml
dependencies:
  flutter:
    sdk: flutter
  flutter_riverpod: ^2.5.0      # State management
  riverpod_annotation: ^2.3.0    # Code generation for providers
  go_router: ^14.0.0             # Navigation
  web_socket_channel: ^3.0.0     # WebSocket client
  flutter_secure_storage: ^9.2.0 # Secure token storage
  shared_preferences: ^2.3.0     # App config persistence
  flutter_markdown: ^0.7.0       # Markdown rendering
  flutter_highlight: ^0.7.0      # Code syntax highlighting
  google_fonts: ^6.2.0           # Typography
  shimmer: ^3.0.0                # Loading animations

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^4.0.0
  riverpod_generator: ^2.4.0
  build_runner: ^2.4.0
  mocktail: ^1.0.0               # Mocking for tests
```

## 7. Theme

**Material 3, dark-first:**
- Dark theme as default (easy on eyes for power users)
- Primary: deep blue (#1565C0)
- Accent: cyan (#00BCD4)
- Error/kill: red (#F44336)
- Warning: amber (#FFC107)
- Success: green (#4CAF50)
- Surface: dark gray (#1E1E1E)
- Background: near-black (#121212)

## 8. Testing Strategy

- **Unit tests:** JSON-RPC client (message parsing, error mapping, timeout), auth provider (state transitions, token refresh), chat provider (message lifecycle)
- **Widget tests:** Auth screens (form validation, error display), chat screen (message rendering, input states), dashboard (tier display, cost bars), kill switch FAB (state transitions)
- **Target:** 80%+ coverage on core/ layer, 70%+ on features/

---

# Phase 1D: End-to-End Integration & Deployment — Design Spec

**Date:** 2026-03-17
**Phase:** 1D of 7-phase roadmap
**Depends on:** Phase 1A, 1B, 1C

---

## 1. Overview

Wire up the full stack with Docker Compose, add integration tests that exercise the real WebSocket API, and set up GitHub Actions CI for automated quality gates.

## 2. Docker Compose

### 2.1 Services

```yaml
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      - DATABASE_URL=postgresql+asyncpg://nobla:nobla@postgres:5432/nobla
      - REDIS_URL=redis://redis:6379/0
      - JWT_SECRET=${JWT_SECRET:-dev-secret-change-me}
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: nobla
      POSTGRES_PASSWORD: nobla
      POSTGRES_DB: nobla
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U nobla"]
      interval: 5s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
```

### 2.2 Backend Dockerfile

```dockerfile
# Multi-stage build
FROM python:3.12-slim AS builder
WORKDIR /app
COPY backend/pyproject.toml backend/setup.cfg* ./
COPY backend/nobla/ ./nobla/
RUN pip install --no-cache-dir .

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY backend/nobla/ ./nobla/
RUN useradd -r nobla
USER nobla
EXPOSE 8000
HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "nobla.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 2.3 Environment

`.env.example` with all configurable values:
- `JWT_SECRET`, `DATABASE_URL`, `REDIS_URL`
- `DAILY_BUDGET`, `MONTHLY_BUDGET`, `SESSION_BUDGET`
- `DEFAULT_LLM_PROVIDER`, `OLLAMA_URL`

## 3. Integration Tests

### 3.1 Test Infrastructure

Located at `tests/integration/`. Uses `pytest-asyncio` with real WebSocket connections.

**Fixture:** Spins up backend (either via subprocess or assumes docker-compose is running). Tests connect to `ws://localhost:8000/ws`.

### 3.2 Test Scenarios

| Test | Description |
|------|-------------|
| `test_register_and_authenticate` | Register new user, disconnect, reconnect with token |
| `test_chat_send_receive` | Authenticate → send message → verify response structure |
| `test_permission_escalation` | Authenticate → escalate to STANDARD → execute code → de-escalate |
| `test_kill_switch_flow` | Authenticate → kill → verify requests rejected → resume → verify requests accepted |
| `test_cost_tracking` | Authenticate → send messages → verify cost dashboard reflects spend |
| `test_unauthenticated_rejection` | Send `chat.send` without auth → verify AUTH_REQUIRED error |
| `test_budget_exceeded` | Set low budget → send messages → verify BUDGET_EXCEEDED error |
| `test_unauthenticated_surface` | Verify `system.health`, `system.register`, `system.authenticate` all work without auth |
| `test_concurrent_connections` | Multiple WebSocket clients operating simultaneously |

### 3.3 Test Markers

```python
@pytest.mark.integration  # Requires running backend
@pytest.mark.slow          # Takes >5s
```

Run with: `pytest tests/integration/ -m integration -v`

## 4. GitHub Actions CI

### 4.1 Workflow: `.github/workflows/ci.yml`

**Triggers:** Push to `main`, pull requests to `main`.

**Backend Job:**
1. Set up Python 3.12
2. Install dependencies: `pip install -e ".[dev]"`
3. Lint: `ruff check backend/`
4. Type check: `mypy backend/nobla/` (optional, may skip if not configured yet)
5. Unit tests: `pytest tests/ -v --cov=nobla --ignore=tests/integration`
6. Coverage report upload

**Flutter Job:**
1. Set up Flutter (stable channel)
2. `flutter pub get` in `app/`
3. `flutter analyze`
4. `flutter test --coverage`
5. `flutter build web` (verify build succeeds)

**Integration Job** (runs after backend + flutter jobs):
1. Start services via `docker compose up -d`
2. Wait for health check
3. Run `pytest tests/integration/ -m integration -v`
4. Tear down

### 4.2 Caching

- Python: cache pip packages
- Flutter: cache pub packages
- Docker: cache layers via `docker/build-push-action`

## 5. File Limit Compliance

All source files will respect the 750-line hard limit. Expected file sizes:
- WebSocket client: ~120 lines
- JSON-RPC client: ~150 lines
- Auth provider: ~130 lines
- Chat provider: ~100 lines
- Each screen: ~150-250 lines
- Each widget: ~50-100 lines
- Docker compose: ~50 lines
- CI workflow: ~100 lines
- Integration tests: ~200 lines total across files

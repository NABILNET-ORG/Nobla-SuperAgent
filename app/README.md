# Nobla Agent — Flutter App

Mobile-first client for [Nobla Agent](https://github.com/NABILNET-ORG/Nobla-SuperAgent), built with Flutter 3.x and Riverpod state management.

## Features

- **Real-time chat** via WebSocket with the Nobla backend
- **Voice UI** with avatar animations and lip-sync playback
- **Security dashboard** with kill switch control
- **Tools UI** — screen mirror (pinch-to-zoom), filterable activity feed, tool catalog browser
- **Persona management** — browse, create, and switch AI personalities
- **Memory viewer** — explore conversation history and knowledge graph
- **Settings** — server connection, theme, security tier management
- **Auth** — JWT-based authentication with secure storage

## Architecture

```
app/lib/
├── core/           # Theme, routing (GoRouter), DI (Riverpod), network layer
├── features/
│   ├── auth/           # Login, registration, token management
│   ├── chat/           # Real-time WebSocket chat UI
│   ├── conversations/  # Conversation list and history
│   ├── dashboard/      # Home screen with security controls
│   ├── memory/         # Memory viewer and knowledge graph
│   ├── persona/        # Persona browser and management
│   ├── tools/          # Tool mirror, activity feed, catalog browser (Phase 4E)
│   └── settings/       # App and server configuration
└── shared/         # Shared widgets, utils, providers (tool activity)
```

## Setup

```bash
flutter pub get
flutter run -d <device-id>
```

## Testing

```bash
flutter test --coverage
flutter analyze
dart format lib/
```

## Key Dependencies

- `flutter_riverpod` — State management
- `web_socket_channel` — WebSocket communication
- `dio` — HTTP client
- `flutter_secure_storage` — Secure credential storage
- `just_audio` — Audio playback for TTS
- `record` — Audio recording for STT
- `rive` / `lottie` — Avatar animations
- `go_router` — Navigation
- `shimmer` — Loading placeholders

## Connection

The app connects to the Nobla backend via:
- **WebSocket** (`ws://host:8000/ws`) for real-time chat, voice streaming, tool approvals, and activity feed
- **HTTPS** (`https://host:8000/api/`) for auth, personas, settings

Configure the server URL in Settings.

---

Part of [Nobla Agent](https://github.com/NABILNET-ORG/Nobla-SuperAgent) by [NABILNET.AI](https://nabilnet.ai)

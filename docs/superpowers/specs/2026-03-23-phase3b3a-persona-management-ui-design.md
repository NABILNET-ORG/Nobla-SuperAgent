# Phase 3B-3a: Persona Management UI — Design Spec

**Date:** 2026-03-23
**Status:** Approved (2 review rounds, all issues resolved)
**Depends on:** Phase 3B-1 (persona engine), Phase 3B-2 (PersonaPlex TTS), Phase 1 (auth/gateway, Flutter app shell)

## Overview

Phase 3B-3a adds a Persona management tab and in-chat persona switching to the Flutter app. Users can browse presets, create custom personas, edit voice/TTS settings, set a default, and switch personas mid-conversation via the chat app bar.

This is the first of two Flutter sub-phases:
- **3B-3a** (this spec): Persona management UI + in-chat switching
- **3B-3b**: Voice interaction + avatar UI (recording, playback, Rive avatar, audio visualizer, emotion display)

**Scope:** Flutter only — no backend changes. All APIs consumed are already implemented in 3B-1 and 3B-2.

## Navigation Change

Bottom nav expands from 4 to 5 tabs:

```
Before: Chat | Dashboard | Memory | Settings
After:  Chat | Dashboard | Memory | Persona | Settings
```

New route: `/home/persona` (list), `/home/persona/:id` (detail/edit), `/home/persona/create` (new).

## File Layout

### New Files

```
app/lib/
├── features/
│   └── persona/
│       ├── providers/
│       │   ├── persona_list_provider.dart     # List all personas (REST)
│       │   ├── persona_detail_provider.dart   # Single persona CRUD (REST)
│       │   ├── persona_preference_provider.dart # User default preference (REST)
│       │   └── active_persona_provider.dart   # Resolved active persona for chat
│       ├── screens/
│       │   ├── persona_list_screen.dart       # Grid/list of all personas
│       │   ├── persona_edit_screen.dart       # Create + edit form (shared)
│       │   └── persona_detail_screen.dart     # Read-only detail with actions
│       └── widgets/
│           ├── persona_card.dart              # Card for list view
│           ├── persona_picker_sheet.dart      # Bottom sheet for chat switching
│           ├── rules_editor.dart              # Add/remove rules chips
│           ├── temperature_slider.dart        # Bias slider with labels
│           └── voice_config_section.dart      # TTS engine picker + voice prompt
├── shared/
│   └── models/
│       └── persona.dart                       # Persona + PersonaPreference models
```

### Modified Files

| File | Changes |
|------|---------|
| `core/routing/app_router.dart` | Add Persona tab route + detail/edit/create sub-routes |
| `core/network/api_client.dart` | New file — HTTP client (dio) for REST endpoints alongside existing WebSocket |
| `features/chat/screens/chat_screen.dart` | Add persona name in app bar with tap-to-switch |
| `features/chat/providers/chat_provider.dart` | Accept active persona context for RPC calls |
| `pubspec.yaml` | Add `dio` dependency |

### Estimated Scope

- New code: ~900-1100 lines across 13 new files
- Modified code: ~80-100 lines across 4 existing files
- Largest new file: `persona_edit_screen.dart` at ~200 lines (well under 750-line limit)

## New Dependencies

```yaml
dio: ^5.7.0              # HTTP client for persona REST API
```

**Removed:** `file_picker` and `path_provider` — voice prompt is a text input referencing server-side files, not a local file picker. These will be added in a future phase when a voice prompt upload endpoint exists.

**Why dio?** The existing app uses WebSocket (JSON-RPC) only. Persona CRUD is REST, and `dio` is the standard Flutter HTTP client with interceptors for auth headers. The alternative — tunneling REST-style calls over WebSocket — would add complexity to both gateway and client for no benefit.

## Data Models

### Persona (`shared/models/persona.dart`)

```dart
class Persona {
  final String id;
  final String name;
  final String personality;
  final String languageStyle;
  final String? background;
  final Map<String, dynamic>? voiceConfig;
  final List<String> rules;
  final double? temperatureBias;
  final int? maxResponseLength;
  final bool isBuiltin;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  // Factory from JSON (matches PersonaResponse schema from backend)
  factory Persona.fromJson(Map<String, dynamic> json);
  Map<String, dynamic> toJson();
}
```

### PersonaPreference

```dart
class PersonaPreference {
  final String? defaultPersonaId;

  factory PersonaPreference.fromJson(Map<String, dynamic> json);
}
```

## API Client

### New: `core/network/api_client.dart`

Thin dio wrapper with auth header injection. Reads server URL from `ConfigNotifier` and user ID from `AuthNotifier`.

**Auth note:** The backend persona routes authenticate via `X-User-Id` header (Phase 1 temporary auth), not Bearer tokens. The client must send the user's ID from `AuthNotifier.state.userId`, not the access token.

```dart
class ApiClient {
  final Dio _dio;

  ApiClient({required String baseUrl, required String Function() getUserId}) {
    _dio = Dio(BaseOptions(baseUrl: baseUrl));
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        options.headers['X-User-Id'] = getUserId();
        handler.next(options);
      },
    ));
  }

  // Persona endpoints
  Future<List<Persona>> listPersonas();
  Future<Persona> getPersona(String id);
  Future<Persona> createPersona(PersonaCreate body);
  Future<Persona> updatePersona(String id, PersonaUpdate body);
  Future<void> deletePersona(String id);
  Future<Persona> clonePersona(String id);

  // Preference endpoints
  Future<PersonaPreference> getPreference();
  Future<PersonaPreference> setPreference(String personaId);
}
```

Provided as a Riverpod provider: `apiClientProvider`.

## State Management

### Providers

| Provider | Type | Source | Purpose |
|----------|------|--------|---------|
| `apiClientProvider` | `Provider<ApiClient>` | dio + auth | HTTP client instance |
| `personaListProvider` | `StateNotifierProvider<PersonaListNotifier, AsyncValue<List<Persona>>>` | `GET /api/personas` | All personas for the list screen. Notifier exposes `refresh()`, `delete(id)`, `clone(id)` methods that mutate state and invalidate. |
| `personaDetailProvider(id)` | `StateNotifierProvider.family<PersonaDetailNotifier, AsyncValue<Persona>>` | `GET /api/personas/{id}` | Single persona with mutation methods: `update()`, `delete()`, `clone()`, `setAsDefault()`. On success, invalidates `personaListProvider` and `personaPreferenceProvider` as needed. **On delete:** navigate back first, then `ref.invalidate(personaDetailProvider(id))` to dispose the family entry — avoids a transient 404 re-fetch. |
| `personaPreferenceProvider` | `StateNotifierProvider<PersonaPreferenceNotifier, AsyncValue<PersonaPreference>>` | `GET/PUT /api/user/persona-preference` | User's default persona. Notifier exposes `setDefault(personaId)`. |
| `activePersonaProvider` | `Provider` | Derived | Session override ?? user default ?? first persona in list (presets always present) |

### Active Persona Resolution (Client-Side)

```
activePersonaProvider derives from:
  1. sessionPersonaOverride (in-memory, set via chat picker)
  2. personaPreferenceProvider.defaultPersonaId (from server)
  3. First persona in personaListProvider (presets are always first, Professional is index 0)

This mirrors the backend's 3-tier resolution but on the client side
for immediate UI updates without round-tripping. No hardcoded UUIDs —
the fallback uses the loaded persona list, which always contains presets.
```

### Session Override

When the user switches persona via the chat app bar picker:
1. `activePersonaProvider` updates immediately (optimistic UI)
2. If voice session is active: `voice.config(persona_id: newId)` RPC call
3. Next `chat.send` includes the active persona context
4. Override is ephemeral — cleared on app restart (matches backend behavior)

## Screens

### Persona List Screen (`/home/persona`)

- **Layout:** Vertical list of `PersonaCard` widgets
- **Each card shows:** Name, personality snippet (max 2 lines), "Builtin" badge if preset, "Default" badge if user's default, active indicator if currently selected in chat
- **Actions:**
  - Tap → navigate to detail screen
  - FAB (bottom-right) → navigate to create screen
- **Empty state:** Not possible — 3 presets always exist
- **Loading:** Shimmer placeholders (existing `shimmer` package)
- **Error:** Retry button with error message

### Persona Detail Screen (`/home/persona/:id`)

- **Layout:** Full-page read view of persona fields
- **Sections:**
  - Header: Name + builtin badge
  - Personality (full text)
  - Language style
  - Background (if set)
  - Rules (chip list, read-only)
  - Voice config summary (engine name, voice prompt filename)
  - Temperature bias (visual indicator: "more focused" ↔ "more creative")
  - Max response length (if set)
- **App bar actions:**
  - Edit button (navigates to edit screen) — hidden for builtins
  - Clone button (creates editable copy via `POST /api/personas/{id}/clone`)
  - Delete button (confirmation dialog) — hidden for builtins
  - "Set as Default" button (calls `PUT /api/user/persona-preference`)

### Persona Edit Screen (`/home/persona/create` or `/home/persona/:id/edit`)

Shared screen for create and edit. In edit mode, pre-fills from existing persona.

- **Form fields:**
  - Name: `TextFormField`, required, max 100 chars
  - Personality: `TextFormField`, required, max 1000 chars, multiline
  - Language style: `TextFormField`, required, max 500 chars
  - Background: `TextFormField`, optional, max 2000 chars, multiline
  - Rules: `RulesEditor` widget — chip list with add button, max 20, each max 500 chars
  - Temperature bias: `TemperatureSlider` — range -0.5 to +0.5, labeled "Focused" to "Creative", step 0.1
  - Max response length: Optional number input, 50-4096
  - Voice config: `VoiceConfigSection` — TTS engine dropdown (cosyvoice, fish_speech, personaplex), voice prompt file picker (.wav)
- **Validation:** Client-side matching backend rules, with `Form` + `GlobalKey<FormState>`
- **Save:** `POST /api/personas` (create) or `PUT /api/personas/{id}` (update)
- **On save success:** Navigate back to list, invalidate `personaListProvider`

### Voice Config Section Widget

```
┌─────────────────────────────────┐
│ Voice Settings                   │
│                                  │
│ TTS Engine:  [CosyVoice    ▼]  │
│                                  │
│ Voice Prompt: [Select .wav file] │
│ professional.wav  ✕              │
│                                  │
│ ℹ️ PersonaPlex requires a       │
│   running PersonaPlex server     │
└─────────────────────────────────┘
```

- Engine dropdown: Lists available engines. If PersonaPlex is not enabled on backend, show it greyed with tooltip "PersonaPlex server not configured."
- Voice prompt: `file_picker` to select a `.wav` file. On pick, the file is **copied to the app's documents directory** (`getApplicationDocumentsDirectory()/voice_prompts/`) to ensure a stable, platform-independent path. The resolved filename (not URI) is stored in `voice_config.voice_prompt`. Only visible when engine is `personaplex`.
- Engine availability is not checked at edit time — validated at voice session start.

**`voice_config` dict schema** (matches Phase 3B-2 PersonaPlex contract):

```json
{
  "engine": "personaplex",
  "voice_prompt": "professional.wav",
  "text_prompt": {
    "personality": "formal and authoritative",
    "style": "concise, structured"
  }
}
```

Keys: `engine` (string, required), `voice_prompt` (string, filename in voice_prompts dir, optional), `text_prompt` (object with `personality` and `style` strings, auto-populated from persona fields on save). When engine is not `personaplex`, only `engine` is stored (e.g., `{"engine": "cosyvoice"}`).

**Voice prompt transfer:** The `voice_prompt` filename refers to a file **pre-provisioned on the backend server** in `PersonaPlexSettings.voice_prompts_dir`. The Flutter client does not upload the file — it only references it by name. Users must place `.wav` files on the server manually (or via Docker volume mount). A `POST /api/voice-prompts` upload endpoint is deferred to a future phase. The file picker in the Flutter UI serves as a convenience for selecting which pre-provisioned voice to associate with a persona, and the picker should list filenames available on the server (via a future `GET /api/voice-prompts` endpoint). For Phase 3B-3a, the voice prompt field is a **plain text input** where the user types the filename — no file picker needed yet.

## Chat Integration

### App Bar Persona Indicator

```
┌──────────────────────────────────┐
│ ◀  Nobla · Professional ▾    ⋮  │
└──────────────────────────────────┘
```

- Persona name shown after "Nobla · " in the app bar title
- Down-arrow (▾) indicates tappable
- Tap opens `PersonaPickerSheet` (modal bottom sheet)

### Persona Picker Bottom Sheet

```
┌──────────────────────────────────┐
│ Switch Persona                    │
│                                   │
│ ● Professional          builtin  │
│ ○ Friendly              builtin  │
│ ○ Military              builtin  │
│ ○ My Custom Persona              │
│                                   │
│ [Manage Personas →]               │
└──────────────────────────────────┘
```

- Radio-style list of all personas
- Current active persona pre-selected
- Tap to switch — updates `activePersonaProvider`, sends `voice.config` if voice session active
- "Manage Personas →" link navigates to Persona tab
- Dismissible by swipe-down or tap outside

## Routing Changes

### Updated Routes

**Route declaration order matters.** In go_router 14.x, routes match top-down. `/home/persona/create` must be declared **before** `/home/persona/:id` — otherwise `create` is captured as an `:id` value.

```dart
// Existing
'/home/chat'
'/home/dashboard'
'/home/memory'
'/home/settings'

// New — ORDER MATTERS
'/home/persona'                    // Persona list (tab)
'/home/persona/create'             // Create new (BEFORE :id)
'/home/persona/:id'                // Persona detail
'/home/persona/:id/edit'           // Edit existing
```

### Bottom Nav Update

```dart
// In app_router.dart ShellRoute — insert at index 3 (before Settings)
NavigationDestination(
  icon: Icon(Icons.face_outlined),
  selectedIcon: Icon(Icons.face),
  label: 'Persona',
),
```

### `_calculateIndex` Update (Required)

The existing `HomeShell._calculateIndex` method hard-codes index lookups for 4 tabs. It must be updated to handle the new Persona tab at index 3, shifting Settings to index 4:

```dart
int _calculateIndex(String location) {
  if (location.startsWith('/home/dashboard')) return 1;
  if (location.startsWith('/home/memory')) return 2;
  if (location.startsWith('/home/persona')) return 3;  // NEW
  if (location.startsWith('/home/settings')) return 4;  // was 3
  return 0; // chat fallback
}
```

The `onDestinationSelected` switch must also be updated to add `case 3: context.go('/home/persona')` and shift Settings to `case 4`.

## Error Handling

| Scenario | UI Behavior |
|----------|-------------|
| Persona list fails to load | Error card with retry button, no shimmer |
| Create/update fails (validation) | Inline field errors from backend 422 response |
| Create fails (name conflict) | Snackbar: "A persona with this name already exists" |
| Delete fails (builtin) | Should never happen — delete button hidden for builtins |
| Clone fails | Snackbar with error message |
| Preference update fails | Snackbar with retry action |
| Network unreachable | All providers show error state with retry |

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| HTTP client | dio (new) alongside existing WebSocket | Persona CRUD is REST; tunneling over WebSocket adds unnecessary complexity |
| Persona tab vs Settings | Dedicated 5th tab | Persona is a first-class feature, not a configuration detail |
| Create + edit screen | Shared screen with mode flag | Same form fields, reduces code duplication |
| Persona switching in chat | App bar dropdown → bottom sheet | Discoverable, always accessible, no extra navigation |
| Client-side resolution | Mirror backend's 3-tier chain | Immediate UI updates without round-tripping to server |
| Voice prompt reference | Text input (server-side filename) | File upload endpoint deferred; users pre-provision .wav files on server |
| Engine availability check | Deferred to voice session start | Edit screen can't know if PersonaPlex server is running |

## Deferred to Phase 3B-3b

- Voice recording UI (mic button, VAD modes, recording indicators)
- TTS audio playback (auto-play, per-message play buttons)
- Rive avatar with state machine (idle, listening, thinking, speaking, emotions)
- Programmatic audio visualizer (CustomPainter amplitude ring)
- Emotion detection display (badge/indicator on avatar)
- Avatar placement and sizing in chat screen
- `avatar_url` field on Persona model (DB migration + UI)
- Per-persona distinct avatar visuals

## Out of Scope

- Voice prompt recording (record your own voice for PersonaPlex) — requires `record` package, Phase 3B-3b
- Persona marketplace / sharing — Phase 6
- Persona import/export — future feature
- Animated transitions between persona switches — nice-to-have, not MVP

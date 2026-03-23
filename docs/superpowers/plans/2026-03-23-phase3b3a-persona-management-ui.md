# Phase 3B-3a: Persona Management UI — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Persona management tab and in-chat persona switching to the Flutter app, consuming the backend REST APIs from Phases 3B-1 and 3B-2.

**Architecture:** New `features/persona/` module with Riverpod StateNotifier providers consuming REST endpoints via a new dio-based `ApiClient`. The existing 4-tab bottom nav expands to 5 tabs. Chat screen app bar gains a persona switcher bottom sheet.

**Tech Stack:** Flutter 3.x, Riverpod (StateNotifier pattern), dio, go_router 14.x, Material 3

**Spec:** `docs/superpowers/specs/2026-03-23-phase3b3a-persona-management-ui-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `app/lib/shared/models/persona.dart` | `Persona` and `PersonaPreference` data models with JSON serialization |
| `app/lib/core/network/api_client.dart` | Dio HTTP client with `X-User-Id` header injection, persona REST methods |
| `app/lib/features/persona/providers/persona_list_provider.dart` | `PersonaListNotifier` — fetch, delete, clone personas |
| `app/lib/features/persona/providers/persona_preference_provider.dart` | `PersonaPreferenceNotifier` — get/set default persona |
| `app/lib/features/persona/providers/active_persona_provider.dart` | Derived provider: session override → user default → first in list |

**Spec deviation note:** The spec lists a `persona_detail_provider.dart` with a `StateNotifierProvider.family`. This plan intentionally omits it — the detail screen reads persona data from `personaListProvider` (in-list lookup by ID) which is simpler and avoids duplicating state. All mutations (delete, clone, set-default) are handled through `personaListProvider.notifier` and `personaPreferenceProvider.notifier` directly.
| `app/lib/features/persona/screens/persona_list_screen.dart` | Vertical list of persona cards with FAB for create |
| `app/lib/features/persona/screens/persona_detail_screen.dart` | Read-only detail view with edit/clone/delete/set-default actions |
| `app/lib/features/persona/screens/persona_edit_screen.dart` | Create + edit form (shared via mode flag) |
| `app/lib/features/persona/widgets/persona_card.dart` | Card widget for list view |
| `app/lib/features/persona/widgets/persona_picker_sheet.dart` | Bottom sheet for in-chat persona switching |
| `app/lib/features/persona/widgets/rules_editor.dart` | Chip list with add/remove for persona rules |
| `app/lib/features/persona/widgets/temperature_slider.dart` | Bias slider (-0.5 to +0.5) with "Focused"/"Creative" labels |
| `app/lib/features/persona/widgets/voice_config_section.dart` | TTS engine dropdown + voice prompt text input |
| `app/test/shared/models/persona_test.dart` | Unit tests for Persona model JSON serialization |
| `app/test/core/network/api_client_test.dart` | Unit tests for ApiClient (mocked dio) |
| `app/test/features/persona/providers/persona_list_provider_test.dart` | Unit tests for PersonaListNotifier |
| `app/test/features/persona/providers/active_persona_provider_test.dart` | Unit tests for active persona resolution |
| `app/test/features/persona/widgets/persona_picker_sheet_test.dart` | Widget test for persona picker bottom sheet |

### Modified Files

| File | Lines | Changes |
|------|-------|---------|
| `app/pubspec.yaml` | 21 | Add `dio: ^5.7.0` dependency |
| `app/lib/main.dart` | 11-27 | Add `apiClientProvider` |
| `app/lib/core/routing/app_router.dart` | 1-118 | Add persona routes, 5th nav tab, update `_calculateIndex` |
| `app/lib/features/chat/screens/chat_screen.dart` | 26-35 | Replace app bar title with persona indicator + tap handler |

---

## Task 1: Add dio dependency

**Files:**
- Modify: `app/pubspec.yaml`

- [ ] **Step 1: Add dio to pubspec.yaml**

In `app/pubspec.yaml`, add `dio` after the `uuid` entry (line 21):

```yaml
  uuid: ^4.5.1
  dio: ^5.7.0
```

- [ ] **Step 2: Run pub get**

Run: `cd app && flutter pub get`
Expected: "Got dependencies!" with no errors

- [ ] **Step 3: Commit**

```bash
git add app/pubspec.yaml app/pubspec.lock
git commit -m "chore: add dio HTTP client dependency"
```

---

## Task 2: Persona data model

**Files:**
- Create: `app/lib/shared/models/persona.dart`
- Test: `app/test/shared/models/persona_test.dart`

- [ ] **Step 1: Write the failing test**

Create `app/test/shared/models/persona_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/shared/models/persona.dart';

void main() {
  group('Persona', () {
    test('fromJson parses backend PersonaResponse correctly', () {
      final json = {
        'id': '00000000-0000-4000-a000-000000000001',
        'name': 'Professional',
        'personality': 'Expert assistant focused on clarity and efficiency',
        'language_style': 'formal, concise, structured',
        'background': 'Productivity-oriented AI assistant',
        'voice_config': {'engine': 'cosyvoice'},
        'rules': ['Use bullet points for lists', 'Cite sources when available'],
        'temperature_bias': 0.0,
        'max_response_length': 1024,
        'is_builtin': true,
        'created_at': null,
        'updated_at': null,
      };

      final persona = Persona.fromJson(json);

      expect(persona.id, '00000000-0000-4000-a000-000000000001');
      expect(persona.name, 'Professional');
      expect(persona.personality, 'Expert assistant focused on clarity and efficiency');
      expect(persona.languageStyle, 'formal, concise, structured');
      expect(persona.background, 'Productivity-oriented AI assistant');
      expect(persona.voiceConfig, {'engine': 'cosyvoice'});
      expect(persona.rules, hasLength(2));
      expect(persona.temperatureBias, 0.0);
      expect(persona.maxResponseLength, 1024);
      expect(persona.isBuiltin, true);
      expect(persona.createdAt, isNull);
      expect(persona.updatedAt, isNull);
    });

    test('fromJson handles nulls for optional fields', () {
      final json = {
        'id': 'abc-123',
        'name': 'Custom',
        'personality': 'Friendly helper',
        'language_style': 'casual',
        'background': null,
        'voice_config': null,
        'rules': <String>[],
        'temperature_bias': null,
        'max_response_length': null,
        'is_builtin': false,
        'created_at': '2026-03-23T10:00:00',
        'updated_at': '2026-03-23T11:00:00',
      };

      final persona = Persona.fromJson(json);

      expect(persona.background, isNull);
      expect(persona.voiceConfig, isNull);
      expect(persona.rules, isEmpty);
      expect(persona.temperatureBias, isNull);
      expect(persona.maxResponseLength, isNull);
      expect(persona.isBuiltin, false);
      expect(persona.createdAt, isNotNull);
    });

    test('toJson produces correct keys for backend PersonaCreate', () {
      final persona = Persona(
        id: 'test-id',
        name: 'Test',
        personality: 'Test persona',
        languageStyle: 'casual',
        rules: ['Be nice'],
        isBuiltin: false,
      );

      final json = persona.toJson();

      expect(json['name'], 'Test');
      expect(json['personality'], 'Test persona');
      expect(json['language_style'], 'casual');
      expect(json['rules'], ['Be nice']);
      // id and is_builtin should NOT be in toJson (server assigns these)
      expect(json.containsKey('id'), false);
      expect(json.containsKey('is_builtin'), false);
    });
  });

  group('PersonaPreference', () {
    test('fromJson parses default_persona_id', () {
      final json = {'default_persona_id': 'some-uuid'};
      final pref = PersonaPreference.fromJson(json);
      expect(pref.defaultPersonaId, 'some-uuid');
    });

    test('fromJson handles null default', () {
      final json = {'default_persona_id': null};
      final pref = PersonaPreference.fromJson(json);
      expect(pref.defaultPersonaId, isNull);
    });
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && flutter test test/shared/models/persona_test.dart`
Expected: FAIL — `persona.dart` doesn't exist yet

- [ ] **Step 3: Write the model**

Create `app/lib/shared/models/persona.dart`:

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

  const Persona({
    required this.id,
    required this.name,
    required this.personality,
    required this.languageStyle,
    this.background,
    this.voiceConfig,
    this.rules = const [],
    this.temperatureBias,
    this.maxResponseLength,
    this.isBuiltin = false,
    this.createdAt,
    this.updatedAt,
  });

  factory Persona.fromJson(Map<String, dynamic> json) {
    return Persona(
      id: json['id'] as String,
      name: json['name'] as String,
      personality: json['personality'] as String,
      languageStyle: json['language_style'] as String,
      background: json['background'] as String?,
      voiceConfig: json['voice_config'] as Map<String, dynamic>?,
      rules: (json['rules'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          const [],
      temperatureBias: (json['temperature_bias'] as num?)?.toDouble(),
      maxResponseLength: json['max_response_length'] as int?,
      isBuiltin: json['is_builtin'] as bool? ?? false,
      createdAt: json['created_at'] != null
          ? DateTime.parse(json['created_at'] as String)
          : null,
      updatedAt: json['updated_at'] != null
          ? DateTime.parse(json['updated_at'] as String)
          : null,
    );
  }

  /// Produces JSON for create/update requests (excludes server-assigned fields).
  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'personality': personality,
      'language_style': languageStyle,
      if (background != null) 'background': background,
      if (voiceConfig != null) 'voice_config': voiceConfig,
      'rules': rules,
      if (temperatureBias != null) 'temperature_bias': temperatureBias,
      if (maxResponseLength != null) 'max_response_length': maxResponseLength,
    };
  }

  Persona copyWith({
    String? name,
    String? personality,
    String? languageStyle,
    String? background,
    Map<String, dynamic>? voiceConfig,
    List<String>? rules,
    double? temperatureBias,
    int? maxResponseLength,
  }) {
    return Persona(
      id: id,
      name: name ?? this.name,
      personality: personality ?? this.personality,
      languageStyle: languageStyle ?? this.languageStyle,
      background: background ?? this.background,
      voiceConfig: voiceConfig ?? this.voiceConfig,
      rules: rules ?? this.rules,
      temperatureBias: temperatureBias ?? this.temperatureBias,
      maxResponseLength: maxResponseLength ?? this.maxResponseLength,
      isBuiltin: isBuiltin,
      createdAt: createdAt,
      updatedAt: updatedAt,
    );
  }
}

class PersonaPreference {
  final String? defaultPersonaId;

  const PersonaPreference({this.defaultPersonaId});

  factory PersonaPreference.fromJson(Map<String, dynamic> json) {
    return PersonaPreference(
      defaultPersonaId: json['default_persona_id'] as String?,
    );
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && flutter test test/shared/models/persona_test.dart`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/lib/shared/models/persona.dart app/test/shared/models/persona_test.dart
git commit -m "feat(persona): add Persona and PersonaPreference data models"
```

---

## Task 3: API client

**Files:**
- Create: `app/lib/core/network/api_client.dart`
- Modify: `app/lib/main.dart` (add provider)
- Test: `app/test/core/network/api_client_test.dart`

- [ ] **Step 1: Write the failing test**

Create `app/test/core/network/api_client_test.dart`:

```dart
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:nobla_agent/core/network/api_client.dart';
import 'package:nobla_agent/shared/models/persona.dart';

class MockDio extends Mock implements Dio {}

void main() {
  late MockDio mockDio;
  late ApiClient client;

  setUp(() {
    mockDio = MockDio();
    client = ApiClient.withDio(mockDio);
  });

  group('listPersonas', () {
    test('returns list of Persona from GET /api/personas', () async {
      when(() => mockDio.get('/api/personas')).thenAnswer(
        (_) async => Response(
          data: [
            {
              'id': 'p1',
              'name': 'Professional',
              'personality': 'Expert',
              'language_style': 'formal',
              'background': null,
              'voice_config': null,
              'rules': <String>[],
              'temperature_bias': null,
              'max_response_length': null,
              'is_builtin': true,
              'created_at': null,
              'updated_at': null,
            }
          ],
          statusCode: 200,
          requestOptions: RequestOptions(path: '/api/personas'),
        ),
      );

      final personas = await client.listPersonas();

      expect(personas, hasLength(1));
      expect(personas.first.name, 'Professional');
      expect(personas.first.isBuiltin, true);
      verify(() => mockDio.get('/api/personas')).called(1);
    });
  });

  group('deletePersona', () {
    test('calls DELETE /api/personas/{id}', () async {
      when(() => mockDio.delete('/api/personas/p1')).thenAnswer(
        (_) async => Response(
          statusCode: 204,
          requestOptions: RequestOptions(path: '/api/personas/p1'),
        ),
      );

      await client.deletePersona('p1');

      verify(() => mockDio.delete('/api/personas/p1')).called(1);
    });
  });

  group('clonePersona', () {
    test('calls POST /api/personas/{id}/clone', () async {
      when(() => mockDio.post('/api/personas/p1/clone')).thenAnswer(
        (_) async => Response(
          data: {
            'id': 'p2',
            'name': 'Professional (Copy)',
            'personality': 'Expert',
            'language_style': 'formal',
            'background': null,
            'voice_config': null,
            'rules': <String>[],
            'temperature_bias': null,
            'max_response_length': null,
            'is_builtin': false,
            'created_at': '2026-03-23T10:00:00',
            'updated_at': '2026-03-23T10:00:00',
          },
          statusCode: 201,
          requestOptions: RequestOptions(path: '/api/personas/p1/clone'),
        ),
      );

      final cloned = await client.clonePersona('p1');

      expect(cloned.name, 'Professional (Copy)');
      expect(cloned.isBuiltin, false);
    });
  });

  group('setPreference', () {
    test('calls PUT /api/user/persona-preference', () async {
      when(() => mockDio.put(
            '/api/user/persona-preference',
            data: {'default_persona_id': 'p1'},
          )).thenAnswer(
        (_) async => Response(
          data: {'default_persona_id': 'p1'},
          statusCode: 200,
          requestOptions:
              RequestOptions(path: '/api/user/persona-preference'),
        ),
      );

      final pref = await client.setPreference('p1');

      expect(pref.defaultPersonaId, 'p1');
    });
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && flutter test test/core/network/api_client_test.dart`
Expected: FAIL — `api_client.dart` doesn't exist

- [ ] **Step 3: Write the API client**

Create `app/lib/core/network/api_client.dart`:

```dart
import 'package:dio/dio.dart';
import 'package:nobla_agent/shared/models/persona.dart';

class ApiClient {
  final Dio _dio;

  /// Production constructor — creates Dio with base URL and auth interceptor.
  ApiClient({
    required String baseUrl,
    required String Function() getUserId,
  }) : _dio = Dio(BaseOptions(baseUrl: baseUrl)) {
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        options.headers['X-User-Id'] = getUserId();
        handler.next(options);
      },
    ));
  }

  /// Test constructor — accepts a pre-configured Dio instance.
  ApiClient.withDio(this._dio);

  // -- Persona CRUD --

  Future<List<Persona>> listPersonas() async {
    final response = await _dio.get('/api/personas');
    final list = response.data as List<dynamic>;
    return list
        .map((e) => Persona.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Persona> getPersona(String id) async {
    final response = await _dio.get('/api/personas/$id');
    return Persona.fromJson(response.data as Map<String, dynamic>);
  }

  Future<Persona> createPersona(Map<String, dynamic> body) async {
    final response = await _dio.post('/api/personas', data: body);
    return Persona.fromJson(response.data as Map<String, dynamic>);
  }

  Future<Persona> updatePersona(String id, Map<String, dynamic> body) async {
    final response = await _dio.put('/api/personas/$id', data: body);
    return Persona.fromJson(response.data as Map<String, dynamic>);
  }

  Future<void> deletePersona(String id) async {
    await _dio.delete('/api/personas/$id');
  }

  Future<Persona> clonePersona(String id) async {
    final response = await _dio.post('/api/personas/$id/clone');
    return Persona.fromJson(response.data as Map<String, dynamic>);
  }

  // -- User Preference --

  Future<PersonaPreference> getPreference() async {
    final response = await _dio.get('/api/user/persona-preference');
    return PersonaPreference.fromJson(
        response.data as Map<String, dynamic>);
  }

  Future<PersonaPreference> setPreference(String personaId) async {
    final response = await _dio.put(
      '/api/user/persona-preference',
      data: {'default_persona_id': personaId},
    );
    return PersonaPreference.fromJson(
        response.data as Map<String, dynamic>);
  }
}
```

- [ ] **Step 4: Add apiClientProvider to main.dart**

In `app/lib/main.dart`, add the import and provider after `authProvider` (line 27):

```dart
import 'package:nobla_agent/core/network/api_client.dart';

final apiClientProvider = Provider<ApiClient>((ref) {
  final config = ref.watch(configProvider);
  final authState = ref.watch(authProvider);
  return ApiClient(
    baseUrl: config.serverUrl.replaceFirst('ws://', 'http://').replaceFirst('wss://', 'https://'),
    getUserId: () {
      final s = ref.read(authProvider);
      return s is Authenticated ? s.userId : '';
    },
  );
});
```

Note: The server URL in config is the WebSocket URL (e.g., `ws://localhost:8000`). The `replaceFirst` converts it to the HTTP equivalent for REST calls. Both WebSocket and REST share the same host/port on the FastAPI backend.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd app && flutter test test/core/network/api_client_test.dart`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/lib/core/network/api_client.dart app/lib/main.dart app/test/core/network/api_client_test.dart
git commit -m "feat(persona): add ApiClient with dio for persona REST endpoints"
```

---

## Task 4: Persona list provider

**Files:**
- Create: `app/lib/features/persona/providers/persona_list_provider.dart`
- Test: `app/test/features/persona/providers/persona_list_provider_test.dart`

- [ ] **Step 1: Write the failing test**

Create `app/test/features/persona/providers/persona_list_provider_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mocktail/mocktail.dart';
import 'package:nobla_agent/core/network/api_client.dart';
import 'package:nobla_agent/shared/models/persona.dart';
import 'package:nobla_agent/features/persona/providers/persona_list_provider.dart';

class MockApiClient extends Mock implements ApiClient {}

final _professional = Persona.fromJson({
  'id': 'p1',
  'name': 'Professional',
  'personality': 'Expert',
  'language_style': 'formal',
  'background': null,
  'voice_config': null,
  'rules': <String>[],
  'temperature_bias': null,
  'max_response_length': null,
  'is_builtin': true,
  'created_at': null,
  'updated_at': null,
});

void main() {
  late MockApiClient mockApi;

  setUp(() {
    mockApi = MockApiClient();
  });

  test('loadPersonas fetches from API and sets data state', () async {
    when(() => mockApi.listPersonas())
        .thenAnswer((_) async => [_professional]);

    final notifier = PersonaListNotifier(mockApi);
    await notifier.loadPersonas();

    expect(notifier.state.value, hasLength(1));
    expect(notifier.state.value!.first.name, 'Professional');
  });

  test('deletePersona removes from list and calls API', () async {
    when(() => mockApi.listPersonas())
        .thenAnswer((_) async => [_professional]);
    when(() => mockApi.deletePersona('p1')).thenAnswer((_) async {});

    final notifier = PersonaListNotifier(mockApi);
    await notifier.loadPersonas();
    await notifier.deletePersona('p1');

    expect(notifier.state.value, isEmpty);
    verify(() => mockApi.deletePersona('p1')).called(1);
  });

  test('clonePersona adds cloned persona to list', () async {
    final cloned = Persona.fromJson({
      'id': 'p2',
      'name': 'Professional (Copy)',
      'personality': 'Expert',
      'language_style': 'formal',
      'background': null,
      'voice_config': null,
      'rules': <String>[],
      'temperature_bias': null,
      'max_response_length': null,
      'is_builtin': false,
      'created_at': '2026-03-23T10:00:00',
      'updated_at': '2026-03-23T10:00:00',
    });

    when(() => mockApi.listPersonas())
        .thenAnswer((_) async => [_professional]);
    when(() => mockApi.clonePersona('p1')).thenAnswer((_) async => cloned);

    final notifier = PersonaListNotifier(mockApi);
    await notifier.loadPersonas();
    final result = await notifier.clonePersona('p1');

    expect(notifier.state.value, hasLength(2));
    expect(result.name, 'Professional (Copy)');
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && flutter test test/features/persona/providers/persona_list_provider_test.dart`
Expected: FAIL — file doesn't exist

- [ ] **Step 3: Write the provider**

Create `app/lib/features/persona/providers/persona_list_provider.dart`:

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/network/api_client.dart';
import 'package:nobla_agent/shared/models/persona.dart';
import 'package:nobla_agent/main.dart';

class PersonaListNotifier extends StateNotifier<AsyncValue<List<Persona>>> {
  final ApiClient _api;

  PersonaListNotifier(this._api) : super(const AsyncValue.loading());

  Future<void> loadPersonas() async {
    state = const AsyncValue.loading();
    try {
      final personas = await _api.listPersonas();
      state = AsyncValue.data(personas);
    } catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }

  Future<void> deletePersona(String id) async {
    await _api.deletePersona(id);
    final current = state.value ?? [];
    state = AsyncValue.data(
      current.where((p) => p.id != id).toList(),
    );
  }

  Future<Persona> clonePersona(String id) async {
    final cloned = await _api.clonePersona(id);
    final current = state.value ?? [];
    state = AsyncValue.data([...current, cloned]);
    return cloned;
  }

  Future<void> refresh() async {
    await loadPersonas();
  }
}

final personaListProvider =
    StateNotifierProvider<PersonaListNotifier, AsyncValue<List<Persona>>>(
  (ref) {
    final api = ref.watch(apiClientProvider);
    final notifier = PersonaListNotifier(api);
    notifier.loadPersonas();
    return notifier;
  },
);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd app && flutter test test/features/persona/providers/persona_list_provider_test.dart`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/lib/features/persona/providers/persona_list_provider.dart app/test/features/persona/providers/persona_list_provider_test.dart
git commit -m "feat(persona): add PersonaListNotifier with fetch, delete, clone"
```

---

## Task 5: Persona preference + active persona providers

**Files:**
- Create: `app/lib/features/persona/providers/persona_preference_provider.dart`
- Create: `app/lib/features/persona/providers/active_persona_provider.dart`
- Test: `app/test/features/persona/providers/active_persona_provider_test.dart`

- [ ] **Step 1: Write the failing test**

Create `app/test/features/persona/providers/active_persona_provider_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/persona/providers/active_persona_provider.dart';
import 'package:nobla_agent/shared/models/persona.dart';

final _professional = Persona(
  id: 'p1',
  name: 'Professional',
  personality: 'Expert',
  languageStyle: 'formal',
  isBuiltin: true,
);

final _friendly = Persona(
  id: 'p2',
  name: 'Friendly',
  personality: 'Warm',
  languageStyle: 'casual',
  isBuiltin: true,
);

void main() {
  test('resolveActivePersona returns session override when set', () {
    final result = resolveActivePersona(
      sessionOverrideId: 'p2',
      defaultPersonaId: 'p1',
      personas: [_professional, _friendly],
    );
    expect(result.id, 'p2');
  });

  test('resolveActivePersona falls back to user default', () {
    final result = resolveActivePersona(
      sessionOverrideId: null,
      defaultPersonaId: 'p2',
      personas: [_professional, _friendly],
    );
    expect(result.id, 'p2');
  });

  test('resolveActivePersona falls back to first persona when no default', () {
    final result = resolveActivePersona(
      sessionOverrideId: null,
      defaultPersonaId: null,
      personas: [_professional, _friendly],
    );
    expect(result.id, 'p1');
  });

  test('null override with null default uses first persona', () {
    final result = resolveActivePersona(
      sessionOverrideId: null,
      defaultPersonaId: null,
      personas: [_professional, _friendly],
    );
    expect(result.name, 'Professional');
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && flutter test test/features/persona/providers/active_persona_provider_test.dart`
Expected: FAIL — files don't exist

- [ ] **Step 3: Write the preference provider**

Create `app/lib/features/persona/providers/persona_preference_provider.dart`:

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/network/api_client.dart';
import 'package:nobla_agent/shared/models/persona.dart';
import 'package:nobla_agent/main.dart';

class PersonaPreferenceNotifier
    extends StateNotifier<AsyncValue<PersonaPreference>> {
  final ApiClient _api;

  PersonaPreferenceNotifier(this._api)
      : super(const AsyncValue.loading());

  Future<void> load() async {
    state = const AsyncValue.loading();
    try {
      final pref = await _api.getPreference();
      state = AsyncValue.data(pref);
    } catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }

  Future<void> setDefault(String personaId) async {
    try {
      final pref = await _api.setPreference(personaId);
      state = AsyncValue.data(pref);
    } catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }
}

final personaPreferenceProvider = StateNotifierProvider<
    PersonaPreferenceNotifier, AsyncValue<PersonaPreference>>(
  (ref) {
    final api = ref.watch(apiClientProvider);
    final notifier = PersonaPreferenceNotifier(api);
    notifier.load();
    return notifier;
  },
);
```

- [ ] **Step 4: Write the active persona provider**

Create `app/lib/features/persona/providers/active_persona_provider.dart`:

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/shared/models/persona.dart';
import 'package:nobla_agent/features/persona/providers/persona_list_provider.dart';
import 'package:nobla_agent/features/persona/providers/persona_preference_provider.dart';

/// Pure function for testability — no Riverpod dependency.
Persona resolveActivePersona({
  required String? sessionOverrideId,
  required String? defaultPersonaId,
  required List<Persona> personas,
}) {
  // 1. Session override
  if (sessionOverrideId != null) {
    final match = personas.where((p) => p.id == sessionOverrideId);
    if (match.isNotEmpty) return match.first;
  }

  // 2. User default
  if (defaultPersonaId != null) {
    final match = personas.where((p) => p.id == defaultPersonaId);
    if (match.isNotEmpty) return match.first;
  }

  // 3. First persona in list (Professional is always index 0)
  return personas.first;
}

/// In-memory session override — StateProvider so watchers react to changes.
final sessionOverrideProvider = StateProvider<String?>((ref) => null);

final activePersonaProvider = Provider<Persona?>((ref) {
  final personasAsync = ref.watch(personaListProvider);
  final prefAsync = ref.watch(personaPreferenceProvider);
  final overrideId = ref.watch(sessionOverrideProvider);

  final personas = personasAsync.valueOrNull;
  final pref = prefAsync.valueOrNull;

  if (personas == null || personas.isEmpty) return null;

  return resolveActivePersona(
    sessionOverrideId: overrideId,
    defaultPersonaId: pref?.defaultPersonaId,
    personas: personas,
  );
});
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd app && flutter test test/features/persona/providers/active_persona_provider_test.dart`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/lib/features/persona/providers/persona_preference_provider.dart app/lib/features/persona/providers/active_persona_provider.dart app/test/features/persona/providers/active_persona_provider_test.dart
git commit -m "feat(persona): add preference provider and active persona resolution"
```

---

## Task 6: Persona card widget

**Files:**
- Create: `app/lib/features/persona/widgets/persona_card.dart`

- [ ] **Step 1: Write the widget**

Create `app/lib/features/persona/widgets/persona_card.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:nobla_agent/shared/models/persona.dart';

class PersonaCard extends StatelessWidget {
  final Persona persona;
  final bool isDefault;
  final bool isActive;
  final VoidCallback onTap;

  const PersonaCard({
    super.key,
    required this.persona,
    this.isDefault = false,
    this.isActive = false,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      elevation: isActive ? 2 : 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: isActive
            ? BorderSide(color: theme.colorScheme.primary, width: 2)
            : BorderSide(color: theme.colorScheme.outlineVariant),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      persona.name,
                      style: theme.textTheme.titleMedium,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (persona.isBuiltin)
                    Chip(
                      label: const Text('Builtin'),
                      labelStyle: theme.textTheme.labelSmall,
                      padding: EdgeInsets.zero,
                      visualDensity: VisualDensity.compact,
                    ),
                  if (isDefault) ...[
                    const SizedBox(width: 4),
                    Icon(Icons.star, size: 18, color: theme.colorScheme.primary),
                  ],
                ],
              ),
              const SizedBox(height: 8),
              Text(
                persona.personality,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.onSurface.withAlpha(178),
                ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 4),
              Text(
                persona.languageStyle,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurface.withAlpha(128),
                  fontStyle: FontStyle.italic,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
```

- [ ] **Step 2: Verify no compile errors**

Run: `cd app && flutter analyze lib/features/persona/widgets/persona_card.dart`
Expected: No issues found

- [ ] **Step 3: Commit**

```bash
git add app/lib/features/persona/widgets/persona_card.dart
git commit -m "feat(persona): add PersonaCard widget"
```

---

## Task 7: Reusable form widgets (rules editor, temperature slider, voice config)

**Files:**
- Create: `app/lib/features/persona/widgets/rules_editor.dart`
- Create: `app/lib/features/persona/widgets/temperature_slider.dart`
- Create: `app/lib/features/persona/widgets/voice_config_section.dart`

- [ ] **Step 1: Write RulesEditor**

Create `app/lib/features/persona/widgets/rules_editor.dart`:

```dart
import 'package:flutter/material.dart';

class RulesEditor extends StatelessWidget {
  final List<String> rules;
  final ValueChanged<List<String>> onChanged;
  final int maxRules;
  final int maxRuleLength;

  const RulesEditor({
    super.key,
    required this.rules,
    required this.onChanged,
    this.maxRules = 20,
    this.maxRuleLength = 500,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Rules', style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 4,
          children: [
            for (int i = 0; i < rules.length; i++)
              InputChip(
                label: Text(
                  rules[i],
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                onDeleted: () {
                  final updated = List<String>.from(rules)..removeAt(i);
                  onChanged(updated);
                },
              ),
            if (rules.length < maxRules)
              ActionChip(
                avatar: const Icon(Icons.add, size: 18),
                label: const Text('Add rule'),
                onPressed: () => _showAddDialog(context),
              ),
          ],
        ),
      ],
    );
  }

  void _showAddDialog(BuildContext context) {
    final controller = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Add Rule'),
        content: TextField(
          controller: controller,
          maxLength: maxRuleLength,
          decoration: const InputDecoration(hintText: 'Enter a rule...'),
          autofocus: true,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () {
              final text = controller.text.trim();
              if (text.isNotEmpty) {
                onChanged([...rules, text]);
              }
              Navigator.pop(ctx);
            },
            child: const Text('Add'),
          ),
        ],
      ),
    );
  }
}
```

- [ ] **Step 2: Write TemperatureSlider**

Create `app/lib/features/persona/widgets/temperature_slider.dart`:

```dart
import 'package:flutter/material.dart';

class TemperatureSlider extends StatelessWidget {
  final double? value;
  final ValueChanged<double?> onChanged;

  const TemperatureSlider({
    super.key,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final currentValue = value ?? 0.0;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text('Temperature Bias', style: theme.textTheme.titleSmall),
            const Spacer(),
            Text(
              currentValue == 0.0
                  ? 'Neutral'
                  : currentValue > 0
                      ? '+${currentValue.toStringAsFixed(1)} Creative'
                      : '${currentValue.toStringAsFixed(1)} Focused',
              style: theme.textTheme.bodySmall,
            ),
          ],
        ),
        Slider(
          value: currentValue,
          min: -0.5,
          max: 0.5,
          divisions: 10,
          label: currentValue.toStringAsFixed(1),
          onChanged: (v) => onChanged(v == 0.0 ? null : v),
        ),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Focused', style: theme.textTheme.labelSmall),
            Text('Creative', style: theme.textTheme.labelSmall),
          ],
        ),
      ],
    );
  }
}
```

- [ ] **Step 3: Write VoiceConfigSection**

Create `app/lib/features/persona/widgets/voice_config_section.dart`:

```dart
import 'package:flutter/material.dart';

class VoiceConfigSection extends StatelessWidget {
  final Map<String, dynamic>? voiceConfig;
  final ValueChanged<Map<String, dynamic>?> onChanged;

  const VoiceConfigSection({
    super.key,
    required this.voiceConfig,
    required this.onChanged,
  });

  static const _engines = ['cosyvoice', 'fish_speech', 'personaplex'];

  String get _currentEngine =>
      (voiceConfig?['engine'] as String?) ?? 'cosyvoice';

  String get _voicePrompt =>
      (voiceConfig?['voice_prompt'] as String?) ?? '';

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isPersonaPlex = _currentEngine == 'personaplex';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Voice Settings', style: theme.textTheme.titleSmall),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          value: _currentEngine,
          decoration: const InputDecoration(
            labelText: 'TTS Engine',
            border: OutlineInputBorder(),
          ),
          items: _engines
              .map((e) => DropdownMenuItem(value: e, child: Text(e)))
              .toList(),
          onChanged: (engine) {
            if (engine == null) return;
            final updated = Map<String, dynamic>.from(voiceConfig ?? {});
            updated['engine'] = engine;
            if (engine != 'personaplex') {
              updated.remove('voice_prompt');
              updated.remove('text_prompt');
            }
            onChanged(updated);
          },
        ),
        if (isPersonaPlex) ...[
          const SizedBox(height: 12),
          TextFormField(
            initialValue: _voicePrompt,
            decoration: const InputDecoration(
              labelText: 'Voice Prompt Filename',
              hintText: 'e.g., professional.wav',
              helperText: 'Pre-provisioned .wav file on the server',
              border: OutlineInputBorder(),
            ),
            onChanged: (value) {
              final updated = Map<String, dynamic>.from(voiceConfig ?? {});
              if (value.trim().isEmpty) {
                updated.remove('voice_prompt');
              } else {
                updated['voice_prompt'] = value.trim();
              }
              onChanged(updated);
            },
          ),
          const SizedBox(height: 8),
          Card(
            color: theme.colorScheme.surfaceContainerHighest,
            child: const Padding(
              padding: EdgeInsets.all(12),
              child: Row(
                children: [
                  Icon(Icons.info_outline, size: 18),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'PersonaPlex requires a running PersonaPlex server.',
                      style: TextStyle(fontSize: 12),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }
}
```

- [ ] **Step 4: Verify no compile errors**

Run: `cd app && flutter analyze lib/features/persona/widgets/`
Expected: No issues found

- [ ] **Step 5: Commit**

```bash
git add app/lib/features/persona/widgets/rules_editor.dart app/lib/features/persona/widgets/temperature_slider.dart app/lib/features/persona/widgets/voice_config_section.dart
git commit -m "feat(persona): add RulesEditor, TemperatureSlider, VoiceConfigSection widgets"
```

---

## Task 8: Persona screens (list, detail, edit)

**Files:**
- Create: `app/lib/features/persona/screens/persona_list_screen.dart`
- Create: `app/lib/features/persona/screens/persona_detail_screen.dart`
- Create: `app/lib/features/persona/screens/persona_edit_screen.dart`

- [ ] **Step 1: Write PersonaListScreen**

Create `app/lib/features/persona/screens/persona_list_screen.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shimmer/shimmer.dart';
import 'package:nobla_agent/features/persona/providers/persona_list_provider.dart';
import 'package:nobla_agent/features/persona/providers/persona_preference_provider.dart';
import 'package:nobla_agent/features/persona/providers/active_persona_provider.dart';
import 'package:nobla_agent/features/persona/widgets/persona_card.dart';

class PersonaListScreen extends ConsumerWidget {
  const PersonaListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final personasAsync = ref.watch(personaListProvider);
    final prefAsync = ref.watch(personaPreferenceProvider);
    final activePersona = ref.watch(activePersonaProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Personas'), centerTitle: true),
      floatingActionButton: FloatingActionButton(
        onPressed: () => context.go('/home/persona/create'),
        child: const Icon(Icons.add),
      ),
      body: personasAsync.when(
        loading: () => _buildShimmer(),
        error: (err, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('Failed to load personas',
                  style: Theme.of(context).textTheme.bodyLarge),
              const SizedBox(height: 8),
              FilledButton(
                onPressed: () =>
                    ref.read(personaListProvider.notifier).refresh(),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (personas) {
          final defaultId = prefAsync.valueOrNull?.defaultPersonaId;
          return ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: personas.length,
            itemBuilder: (context, index) {
              final persona = personas[index];
              return Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: PersonaCard(
                  persona: persona,
                  isDefault: persona.id == defaultId,
                  isActive: persona.id == activePersona?.id,
                  onTap: () => context.go('/home/persona/${persona.id}'),
                ),
              );
            },
          );
        },
      ),
    );
  }

  Widget _buildShimmer() {
    return Shimmer.fromColors(
      baseColor: Colors.grey.shade800,
      highlightColor: Colors.grey.shade600,
      child: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: 3,
        itemBuilder: (_, __) => Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Card(
            child: SizedBox(height: 100),
          ),
        ),
      ),
    );
  }
}
```

- [ ] **Step 2: Write PersonaDetailScreen**

Create `app/lib/features/persona/screens/persona_detail_screen.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:nobla_agent/features/persona/providers/persona_list_provider.dart';
import 'package:nobla_agent/features/persona/providers/persona_preference_provider.dart';

class PersonaDetailScreen extends ConsumerWidget {
  final String personaId;
  const PersonaDetailScreen({super.key, required this.personaId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final personasAsync = ref.watch(personaListProvider);
    final persona = personasAsync.valueOrNull
        ?.where((p) => p.id == personaId)
        .firstOrNull;

    if (persona == null) {
      return Scaffold(
        appBar: AppBar(),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Text(persona.name),
        actions: [
          if (!persona.isBuiltin)
            IconButton(
              icon: const Icon(Icons.edit),
              tooltip: 'Edit',
              onPressed: () =>
                  context.go('/home/persona/${persona.id}/edit'),
            ),
          IconButton(
            icon: const Icon(Icons.copy),
            tooltip: 'Clone',
            onPressed: () => _clone(context, ref),
          ),
          if (!persona.isBuiltin)
            IconButton(
              icon: const Icon(Icons.delete),
              tooltip: 'Delete',
              onPressed: () => _confirmDelete(context, ref),
            ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (persona.isBuiltin)
            Chip(label: const Text('Builtin Preset')),
          const SizedBox(height: 16),
          _section(theme, 'Personality', persona.personality),
          _section(theme, 'Language Style', persona.languageStyle),
          if (persona.background != null)
            _section(theme, 'Background', persona.background!),
          if (persona.rules.isNotEmpty) ...[
            Text('Rules', style: theme.textTheme.titleSmall),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children:
                  persona.rules.map((r) => Chip(label: Text(r))).toList(),
            ),
            const SizedBox(height: 16),
          ],
          if (persona.temperatureBias != null)
            _section(theme, 'Temperature Bias',
                '${persona.temperatureBias! > 0 ? "+" : ""}${persona.temperatureBias!.toStringAsFixed(1)}'),
          if (persona.maxResponseLength != null)
            _section(theme, 'Max Response Length',
                '${persona.maxResponseLength} tokens'),
          if (persona.voiceConfig != null) ...[
            Text('Voice Config', style: theme.textTheme.titleSmall),
            const SizedBox(height: 8),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Text(
                  'Engine: ${persona.voiceConfig!['engine'] ?? 'default'}'
                  '${persona.voiceConfig!['voice_prompt'] != null ? '\nVoice: ${persona.voiceConfig!['voice_prompt']}' : ''}',
                ),
              ),
            ),
            const SizedBox(height: 16),
          ],
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: () => _setAsDefault(context, ref),
            icon: const Icon(Icons.star),
            label: const Text('Set as Default'),
          ),
        ],
      ),
    );
  }

  Widget _section(ThemeData theme, String title, String content) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: theme.textTheme.titleSmall),
          const SizedBox(height: 4),
          Text(content, style: theme.textTheme.bodyMedium),
        ],
      ),
    );
  }

  Future<void> _clone(BuildContext context, WidgetRef ref) async {
    try {
      final cloned =
          await ref.read(personaListProvider.notifier).clonePersona(personaId);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Cloned as "${cloned.name}"')),
        );
        context.go('/home/persona/${cloned.id}');
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Clone failed: $e')),
        );
      }
    }
  }

  Future<void> _confirmDelete(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete Persona?'),
        content: const Text('This action cannot be undone.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Delete', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;

    try {
      context.go('/home/persona');
      await ref.read(personaListProvider.notifier).deletePersona(personaId);
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Delete failed: $e')),
        );
      }
    }
  }

  Future<void> _setAsDefault(BuildContext context, WidgetRef ref) async {
    try {
      await ref
          .read(personaPreferenceProvider.notifier)
          .setDefault(personaId);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Set as default persona')),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to set default: $e')),
        );
      }
    }
  }
}
```

- [ ] **Step 3: Write PersonaEditScreen**

Create `app/lib/features/persona/screens/persona_edit_screen.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:nobla_agent/features/persona/providers/persona_list_provider.dart';
import 'package:nobla_agent/features/persona/widgets/rules_editor.dart';
import 'package:nobla_agent/features/persona/widgets/temperature_slider.dart';
import 'package:nobla_agent/features/persona/widgets/voice_config_section.dart';
import 'package:nobla_agent/main.dart';
import 'package:nobla_agent/shared/models/persona.dart';

class PersonaEditScreen extends ConsumerStatefulWidget {
  final String? personaId; // null = create mode

  const PersonaEditScreen({super.key, this.personaId});

  @override
  ConsumerState<PersonaEditScreen> createState() => _PersonaEditScreenState();
}

class _PersonaEditScreenState extends ConsumerState<PersonaEditScreen> {
  final _formKey = GlobalKey<FormState>();
  late TextEditingController _nameCtl;
  late TextEditingController _personalityCtl;
  late TextEditingController _styleCtl;
  late TextEditingController _backgroundCtl;
  late TextEditingController _maxLengthCtl;
  List<String> _rules = [];
  double? _temperatureBias;
  Map<String, dynamic>? _voiceConfig;
  bool _saving = false;

  bool get _isEditMode => widget.personaId != null;

  @override
  void initState() {
    super.initState();
    _nameCtl = TextEditingController();
    _personalityCtl = TextEditingController();
    _styleCtl = TextEditingController();
    _backgroundCtl = TextEditingController();
    _maxLengthCtl = TextEditingController();

    if (_isEditMode) {
      // Pre-fill from existing persona in next frame
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final personas = ref.read(personaListProvider).valueOrNull ?? [];
        final existing = personas.where((p) => p.id == widget.personaId);
        if (existing.isNotEmpty) {
          final p = existing.first;
          _nameCtl.text = p.name;
          _personalityCtl.text = p.personality;
          _styleCtl.text = p.languageStyle;
          _backgroundCtl.text = p.background ?? '';
          _maxLengthCtl.text =
              p.maxResponseLength?.toString() ?? '';
          setState(() {
            _rules = List.from(p.rules);
            _temperatureBias = p.temperatureBias;
            _voiceConfig = p.voiceConfig != null
                ? Map.from(p.voiceConfig!)
                : null;
          });
        }
      });
    }
  }

  @override
  void dispose() {
    _nameCtl.dispose();
    _personalityCtl.dispose();
    _styleCtl.dispose();
    _backgroundCtl.dispose();
    _maxLengthCtl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_isEditMode ? 'Edit Persona' : 'Create Persona'),
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextFormField(
              controller: _nameCtl,
              decoration: const InputDecoration(
                labelText: 'Name *',
                border: OutlineInputBorder(),
              ),
              maxLength: 100,
              validator: (v) =>
                  (v == null || v.trim().isEmpty) ? 'Name is required' : null,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _personalityCtl,
              decoration: const InputDecoration(
                labelText: 'Personality *',
                border: OutlineInputBorder(),
              ),
              maxLength: 1000,
              maxLines: 3,
              validator: (v) => (v == null || v.trim().isEmpty)
                  ? 'Personality is required'
                  : null,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _styleCtl,
              decoration: const InputDecoration(
                labelText: 'Language Style *',
                border: OutlineInputBorder(),
              ),
              maxLength: 500,
              validator: (v) => (v == null || v.trim().isEmpty)
                  ? 'Language style is required'
                  : null,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _backgroundCtl,
              decoration: const InputDecoration(
                labelText: 'Background',
                border: OutlineInputBorder(),
              ),
              maxLength: 2000,
              maxLines: 3,
            ),
            const SizedBox(height: 24),
            RulesEditor(
              rules: _rules,
              onChanged: (r) => setState(() => _rules = r),
            ),
            const SizedBox(height: 24),
            TemperatureSlider(
              value: _temperatureBias,
              onChanged: (v) => setState(() => _temperatureBias = v),
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _maxLengthCtl,
              decoration: const InputDecoration(
                labelText: 'Max Response Length (tokens)',
                border: OutlineInputBorder(),
                hintText: '50-4096',
              ),
              keyboardType: TextInputType.number,
              validator: (v) {
                if (v == null || v.trim().isEmpty) return null;
                final n = int.tryParse(v.trim());
                if (n == null || n < 50 || n > 4096) {
                  return 'Must be 50-4096';
                }
                return null;
              },
            ),
            const SizedBox(height: 24),
            VoiceConfigSection(
              voiceConfig: _voiceConfig,
              onChanged: (v) => setState(() => _voiceConfig = v),
            ),
            const SizedBox(height: 32),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: _saving
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Text(_isEditMode ? 'Save' : 'Create'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);

    final body = <String, dynamic>{
      'name': _nameCtl.text.trim(),
      'personality': _personalityCtl.text.trim(),
      'language_style': _styleCtl.text.trim(),
      if (_backgroundCtl.text.trim().isNotEmpty)
        'background': _backgroundCtl.text.trim(),
      'rules': _rules,
      if (_temperatureBias != null) 'temperature_bias': _temperatureBias,
      if (_maxLengthCtl.text.trim().isNotEmpty)
        'max_response_length': int.parse(_maxLengthCtl.text.trim()),
      if (_voiceConfig != null) 'voice_config': _voiceConfig,
    };

    // Auto-populate text_prompt for PersonaPlex
    if (_voiceConfig?['engine'] == 'personaplex') {
      body['voice_config'] = {
        ...(_voiceConfig ?? {}),
        'text_prompt': {
          'personality': _personalityCtl.text.trim(),
          'style': _styleCtl.text.trim(),
        },
      };
    }

    try {
      final api = ref.read(apiClientProvider);
      if (_isEditMode) {
        await api.updatePersona(widget.personaId!, body);
      } else {
        await api.createPersona(body);
      }
      ref.read(personaListProvider.notifier).refresh();
      if (mounted) context.go('/home/persona');
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Save failed: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}
```

- [ ] **Step 4: Verify no compile errors**

Run: `cd app && flutter analyze lib/features/persona/screens/`
Expected: No issues found

- [ ] **Step 5: Commit**

```bash
git add app/lib/features/persona/screens/
git commit -m "feat(persona): add list, detail, and edit screens"
```

---

## Task 9: Routing — add Persona tab and routes

**Files:**
- Modify: `app/lib/core/routing/app_router.dart`

This task modifies the existing router to add the 5th tab and persona sub-routes.

- [ ] **Step 1: Add import for persona screens**

At the top of `app/lib/core/routing/app_router.dart`, add after line 9:

```dart
import 'package:nobla_agent/features/persona/screens/persona_list_screen.dart';
import 'package:nobla_agent/features/persona/screens/persona_detail_screen.dart';
import 'package:nobla_agent/features/persona/screens/persona_edit_screen.dart';
```

- [ ] **Step 2: Add persona routes inside ShellRoute**

In `app_router.dart`, inside the `ShellRoute.routes` list, add these routes **after** the `GoRoute` for `/home/memory` and **before** the `GoRoute` for `/home/settings`. **Order matters — `create` before `:id`:**

```dart
          GoRoute(
            path: '/home/persona',
            builder: (context, state) => const PersonaListScreen(),
          ),
          GoRoute(
            path: '/home/persona/create',
            builder: (context, state) => const PersonaEditScreen(),
          ),
          GoRoute(
            path: '/home/persona/:id',
            builder: (context, state) => PersonaDetailScreen(
              personaId: state.pathParameters['id']!,
            ),
          ),
          GoRoute(
            path: '/home/persona/:id/edit',
            builder: (context, state) => PersonaEditScreen(
              personaId: state.pathParameters['id'],
            ),
          ),
```

- [ ] **Step 3: Add Persona NavigationDestination**

In the `destinations` list (line 86), insert a new entry at index 3 (before Settings):

```dart
          NavigationDestination(
            icon: Icon(Icons.face_outlined),
            selectedIcon: Icon(Icons.face),
            label: 'Persona',
          ),
```

- [ ] **Step 4: Update `_calculateIndex`**

Replace the `_calculateIndex` method body (lines 112-117):

```dart
  int _calculateIndex(String location) {
    if (location.startsWith('/home/dashboard')) return 1;
    if (location.startsWith('/home/memory')) return 2;
    if (location.startsWith('/home/persona')) return 3;
    if (location.startsWith('/home/settings')) return 4;
    return 0;
  }
```

- [ ] **Step 5: Update `onDestinationSelected`**

Replace the switch block (lines 75-84):

```dart
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
              context.go('/home/settings');
          }
        },
```

- [ ] **Step 6: Verify no compile errors**

Run: `cd app && flutter analyze lib/core/routing/app_router.dart`
Expected: No issues found

- [ ] **Step 7: Commit**

```bash
git add app/lib/core/routing/app_router.dart
git commit -m "feat(persona): add 5th nav tab and persona routes"
```

---

## Task 10: Persona picker bottom sheet + chat integration

**Files:**
- Create: `app/lib/features/persona/widgets/persona_picker_sheet.dart`
- Modify: `app/lib/features/chat/screens/chat_screen.dart`
- Test: `app/test/features/persona/widgets/persona_picker_sheet_test.dart`

- [ ] **Step 1: Write PersonaPickerSheet**

Create `app/lib/features/persona/widgets/persona_picker_sheet.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:nobla_agent/features/persona/providers/active_persona_provider.dart';
import 'package:nobla_agent/features/persona/providers/persona_list_provider.dart';
import 'package:nobla_agent/shared/models/persona.dart';

class PersonaPickerSheet extends ConsumerWidget {
  const PersonaPickerSheet({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final personasAsync = ref.watch(personaListProvider);
    final activePersona = ref.watch(activePersonaProvider);
    final theme = Theme.of(context);

    return DraggableScrollableSheet(
      initialChildSize: 0.4,
      minChildSize: 0.25,
      maxChildSize: 0.6,
      expand: false,
      builder: (context, scrollController) {
        return Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text('Switch Persona',
                  style: theme.textTheme.titleMedium),
            ),
            Expanded(
              child: personasAsync.when(
                loading: () =>
                    const Center(child: CircularProgressIndicator()),
                error: (_, __) =>
                    const Center(child: Text('Failed to load personas')),
                data: (personas) => ListView.builder(
                  controller: scrollController,
                  itemCount: personas.length + 1, // +1 for "Manage" link
                  itemBuilder: (context, index) {
                    if (index == personas.length) {
                      return ListTile(
                        leading: const Icon(Icons.settings),
                        title: const Text('Manage Personas'),
                        trailing: const Icon(Icons.arrow_forward_ios,
                            size: 16),
                        onTap: () {
                          Navigator.pop(context);
                          context.go('/home/persona');
                        },
                      );
                    }
                    final persona = personas[index];
                    final isActive = persona.id == activePersona?.id;
                    return RadioListTile<String>(
                      value: persona.id,
                      groupValue: activePersona?.id,
                      title: Text(persona.name),
                      subtitle: persona.isBuiltin
                          ? const Text('builtin',
                              style: TextStyle(fontSize: 12))
                          : null,
                      onChanged: (id) {
                        if (id != null) {
                          ref.read(sessionOverrideProvider.notifier).state = id;
                          Navigator.pop(context);
                        }
                      },
                    );
                  },
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}
```

- [ ] **Step 2: Write widget test**

Create `app/test/features/persona/widgets/persona_picker_sheet_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:nobla_agent/core/network/api_client.dart';
import 'package:nobla_agent/features/persona/providers/persona_list_provider.dart';
import 'package:nobla_agent/features/persona/providers/persona_preference_provider.dart';
import 'package:nobla_agent/features/persona/widgets/persona_picker_sheet.dart';
import 'package:nobla_agent/shared/models/persona.dart';

class MockApiClient extends Mock implements ApiClient {}

void main() {
  final personas = [
    Persona(
      id: 'p1',
      name: 'Professional',
      personality: 'Expert',
      languageStyle: 'formal',
      isBuiltin: true,
    ),
    Persona(
      id: 'p2',
      name: 'Friendly',
      personality: 'Warm',
      languageStyle: 'casual',
      isBuiltin: true,
    ),
  ];

  testWidgets('shows all personas in radio list', (tester) async {
    final mockApi = MockApiClient();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          personaListProvider.overrideWith(
            (ref) {
              final notifier = PersonaListNotifier(mockApi);
              notifier.state = AsyncValue.data(personas);
              return notifier;
            },
          ),
          personaPreferenceProvider.overrideWith(
            (ref) {
              final notifier = PersonaPreferenceNotifier(mockApi);
              notifier.state =
                  const AsyncValue.data(PersonaPreference());
              return notifier;
            },
          ),
        ],
        child: MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) => ElevatedButton(
                onPressed: () => showModalBottomSheet(
                  context: context,
                  builder: (_) => const PersonaPickerSheet(),
                ),
                child: const Text('Open'),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();

    expect(find.text('Professional'), findsOneWidget);
    expect(find.text('Friendly'), findsOneWidget);
    expect(find.text('Manage Personas'), findsOneWidget);
  });
}
```

Note: This test verifies the widget renders correctly with overridden providers. The `_FakeApiClient` is a placeholder since the providers' state is overridden directly.

- [ ] **Step 3: Modify ChatScreen app bar**

In `app/lib/features/chat/screens/chat_screen.dart`, add the import at the top:

```dart
import 'package:nobla_agent/features/persona/providers/active_persona_provider.dart';
import 'package:nobla_agent/features/persona/widgets/persona_picker_sheet.dart';
```

Then replace the `AppBar` (lines 26-35) with:

```dart
        AppBar(
          title: GestureDetector(
            onTap: () => showModalBottomSheet(
              context: context,
              builder: (_) => const PersonaPickerSheet(),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'Nobla · ${ref.watch(activePersonaProvider)?.name ?? "Loading..."}',
                ),
                const SizedBox(width: 4),
                const Icon(Icons.arrow_drop_down, size: 20),
              ],
            ),
          ),
          centerTitle: true,
          actions: [
            IconButton(
              icon: const Icon(Icons.delete_outline),
              onPressed: () => ref.read(chatProvider.notifier).clearChat(),
              tooltip: 'Clear chat',
            ),
          ],
        ),
```

- [ ] **Step 4: Verify no compile errors**

Run: `cd app && flutter analyze lib/features/`
Expected: No issues found

- [ ] **Step 5: Commit**

```bash
git add app/lib/features/persona/widgets/persona_picker_sheet.dart app/lib/features/chat/screens/chat_screen.dart app/test/features/persona/widgets/persona_picker_sheet_test.dart
git commit -m "feat(persona): add picker bottom sheet and chat app bar integration"
```

---

## Task 11: Run all tests and verify

- [ ] **Step 1: Run all tests**

Run: `cd app && flutter test`
Expected: All tests PASS

- [ ] **Step 2: Run flutter analyze**

Run: `cd app && flutter analyze`
Expected: No issues found

- [ ] **Step 3: Run dart format**

Run: `cd app && dart format lib/ test/`
Expected: All files formatted

- [ ] **Step 4: Final commit if formatting changed anything**

```bash
git add -A
git commit -m "style: format persona feature code"
```

---

## Task 12: Integration smoke test (manual)

This task is a manual verification checklist — not automated.

- [ ] **Step 1: Start the backend**

Run: `cd backend && uvicorn nobla.main:app --reload --host 0.0.0.0 --port 8000`
Expected: Server starts without errors

- [ ] **Step 2: Run the Flutter app**

Run: `cd app && flutter run`
Expected: App launches with 5-tab bottom nav (Chat, Dashboard, Memory, Persona, Settings)

- [ ] **Step 3: Verify Persona tab**

- Navigate to Persona tab
- See 3 builtin presets (Professional, Friendly, Military)
- Tap Professional → detail screen shows all fields
- Tap Clone → creates "Professional (Copy)"
- Tap FAB → create screen, fill in fields, save → appears in list
- Edit the custom persona → changes persist
- Delete the custom persona → removed from list

- [ ] **Step 4: Verify chat persona switching**

- Navigate to Chat tab
- App bar shows "Nobla · Professional"
- Tap persona name → picker bottom sheet opens
- Select "Friendly" → app bar updates to "Nobla · Friendly"
- "Manage Personas →" navigates to Persona tab

- [ ] **Step 5: Verify set default**

- On detail screen, tap "Set as Default"
- Star icon appears on that persona's card in list
- Restart app → default persona is pre-selected in chat

---

## Dependency Graph

```
Task 1 (dio dep) ← Task 2 (models) ← Task 3 (API client) ← Task 4 (list provider)
                                                            ← Task 5 (pref + active providers)
Task 6 (card widget)         ← Task 8 (screens)
Task 7 (form widgets)        ← Task 8 (screens)
Task 4 + 5 + 8               ← Task 9 (routing)
Task 9                        ← Task 10 (picker + chat integration)
Task 10                       ← Task 11 (all tests)
Task 11                       ← Task 12 (smoke test)
```

**Parallelizable:** Tasks 6 and 7 can run in parallel with Tasks 4 and 5 (no dependencies between them).

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

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:nobla_agent/core/network/api_client.dart';

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
          requestOptions: RequestOptions(path: '/api/user/persona-preference'),
        ),
      );

      final pref = await client.setPreference('p1');

      expect(pref.defaultPersonaId, 'p1');
    });
  });
}

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

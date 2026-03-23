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

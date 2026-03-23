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
  assert(personas.isNotEmpty, 'resolveActivePersona requires a non-empty list');
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

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

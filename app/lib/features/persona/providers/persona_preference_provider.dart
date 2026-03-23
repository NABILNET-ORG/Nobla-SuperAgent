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

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';

class ProviderInfo {
  final String name;
  final String displayName;
  final bool connected;
  final String authType;
  final List<String> authMethods;
  final String model;

  const ProviderInfo({
    required this.name,
    required this.displayName,
    required this.connected,
    required this.authType,
    required this.authMethods,
    required this.model,
  });

  factory ProviderInfo.fromJson(Map<String, dynamic> json) {
    return ProviderInfo(
      name: json['name'] as String,
      displayName: json['display_name'] as String? ?? json['name'] as String,
      connected: json['connected'] as bool? ?? false,
      authType: json['auth_type'] as String? ?? 'none',
      authMethods:
          (json['auth_methods'] as List?)?.cast<String>() ?? ['api_key'],
      model: json['model'] as String? ?? '',
    );
  }
}

class ProviderSettingsState {
  final List<ProviderInfo> providers;
  final bool isLoading;
  final String? error;

  const ProviderSettingsState({
    this.providers = const [],
    this.isLoading = false,
    this.error,
  });

  ProviderSettingsState copyWith({
    List<ProviderInfo>? providers,
    bool? isLoading,
    String? error,
  }) {
    return ProviderSettingsState(
      providers: providers ?? this.providers,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}

class ProviderSettingsNotifier extends StateNotifier<ProviderSettingsState> {
  final JsonRpcClient _rpc;

  ProviderSettingsNotifier(this._rpc) : super(const ProviderSettingsState());

  Future<void> loadProviders() async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final result = await _rpc.call('provider.list');
      final list = (result['providers'] as List)
          .map((p) => ProviderInfo.fromJson(p as Map<String, dynamic>))
          .toList();
      state = state.copyWith(providers: list, isLoading: false);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<bool> connectApiKey(String provider, String apiKey) async {
    try {
      final result = await _rpc.call('provider.connect_apikey', {
        'provider': provider,
        'api_key': apiKey,
      });
      if (result['connected'] == true) {
        await loadProviders();
        return true;
      }
      return false;
    } catch (e) {
      return false;
    }
  }

  Future<void> disconnect(String provider) async {
    await _rpc.call('provider.disconnect', {'provider': provider});
    await loadProviders();
  }
}

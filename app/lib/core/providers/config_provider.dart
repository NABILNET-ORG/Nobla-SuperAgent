import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AppConfig {
  final String serverUrl;
  final String displayName;
  final bool isDarkMode;

  const AppConfig({
    this.serverUrl = 'ws://localhost:8000/ws',
    this.displayName = 'User',
    this.isDarkMode = true,
  });

  AppConfig copyWith(
      {String? serverUrl, String? displayName, bool? isDarkMode}) {
    return AppConfig(
      serverUrl: serverUrl ?? this.serverUrl,
      displayName: displayName ?? this.displayName,
      isDarkMode: isDarkMode ?? this.isDarkMode,
    );
  }
}

class ConfigNotifier extends StateNotifier<AppConfig> {
  ConfigNotifier() : super(const AppConfig());

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    state = AppConfig(
      serverUrl: prefs.getString('server_url') ?? 'ws://localhost:8000/ws',
      displayName: prefs.getString('display_name') ?? 'User',
      isDarkMode: prefs.getBool('is_dark_mode') ?? true,
    );
  }

  Future<void> setServerUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('server_url', url);
    state = state.copyWith(serverUrl: url);
  }

  Future<void> setDisplayName(String name) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('display_name', name);
    state = state.copyWith(displayName: name);
  }

  Future<void> setDarkMode(bool dark) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('is_dark_mode', dark);
    state = state.copyWith(isDarkMode: dark);
  }
}

final configProvider = StateNotifierProvider<ConfigNotifier, AppConfig>((ref) {
  return ConfigNotifier();
});

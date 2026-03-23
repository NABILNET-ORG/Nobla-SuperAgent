import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/providers/auth_provider.dart';
import 'package:nobla_agent/core/providers/config_provider.dart';
import 'package:nobla_agent/core/providers/notification_provider.dart';
import 'package:nobla_agent/core/routing/app_router.dart';
import 'package:nobla_agent/core/theme/app_theme.dart';
import 'package:nobla_agent/core/network/websocket_client.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';
import 'package:nobla_agent/core/network/api_client.dart';

final websocketProvider = Provider<WebSocketClient>((ref) {
  final client = WebSocketClient();
  ref.onDispose(() => client.dispose());
  return client;
});

final jsonRpcProvider = Provider<JsonRpcClient>((ref) {
  final ws = ref.watch(websocketProvider);
  final client = JsonRpcClient(ws);
  ref.onDispose(() => client.dispose());
  return client;
});

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  final rpc = ref.watch(jsonRpcProvider);
  return AuthNotifier(rpc);
});

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

void main() {
  runApp(const ProviderScope(child: NoblaApp()));
}

class NoblaApp extends ConsumerWidget {
  const NoblaApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authProvider);
    final config = ref.watch(configProvider);
    final router = createRouter(authState);

    ref.listen(authProvider, (prev, next) {
      if (next is Authenticated &&
          (prev == null || prev is Unauthenticated)) {
        final ws = ref.read(websocketProvider);
        final cfg = ref.read(configProvider);
        ws.connect(cfg.serverUrl);
        final rpc = ref.read(jsonRpcProvider);
        NotificationDispatcher(ref).listen(rpc);
      }
      if (next is Unauthenticated && prev is Authenticated) {
        ref.read(websocketProvider).disconnect();
      }
    });

    return MaterialApp.router(
      title: 'Nobla Agent',
      debugShowCheckedModeBanner: false,
      theme: config.isDarkMode ? AppTheme.darkTheme : AppTheme.lightTheme,
      routerConfig: router,
    );
  }
}

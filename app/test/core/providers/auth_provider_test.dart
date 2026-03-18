import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';
import 'package:nobla_agent/core/network/websocket_client.dart';
import 'package:nobla_agent/core/providers/auth_provider.dart';

class FakeWebSocketClient extends WebSocketClient {
  final sentMessages = <String>[];
  final _fakeMessageController = StreamController<String>.broadcast();
  @override
  Stream<String> get messageStream => _fakeMessageController.stream;
  @override
  ConnectionStatus get currentStatus => ConnectionStatus.connected;
  @override
  void send(String message) => sentMessages.add(message);
  void respondToLast(Map<String, dynamic> result) {
    final sent = jsonDecode(sentMessages.last);
    _fakeMessageController.add(jsonEncode({
      'jsonrpc': '2.0',
      'id': sent['id'],
      'result': result,
    }));
  }

  @override
  void dispose() => _fakeMessageController.close();
}

void main() {
  late FakeWebSocketClient fakeWs;
  late JsonRpcClient rpc;
  late AuthNotifier auth;

  setUp(() {
    fakeWs = FakeWebSocketClient();
    rpc = JsonRpcClient(fakeWs);
    auth = AuthNotifier(rpc);
  });

  tearDown(() {
    rpc.dispose();
    fakeWs.dispose();
  });

  group('AuthNotifier', () {
    test('initial state is unauthenticated', () {
      expect(auth.state, isA<Unauthenticated>());
    });

    test('register sends system.register and updates state', () async {
      final future = auth.register('Test User', 'mypassphrase123');
      await Future.delayed(const Duration(milliseconds: 10));
      final sent = jsonDecode(fakeWs.sentMessages.last);
      expect(sent['method'], 'system.register');
      expect(sent['params']['display_name'], 'Test User');
      expect(sent['params']['passphrase'], 'mypassphrase123');

      fakeWs.respondToLast({
        'user_id': 'u-123',
        'display_name': 'Test User',
        'access_token': 'at-xxx',
        'refresh_token': 'rt-xxx',
      });
      await future;
      expect(auth.state, isA<Authenticated>());
      final authed = auth.state as Authenticated;
      expect(authed.userId, 'u-123');
      expect(authed.displayName, 'Test User');
    });

    test('logout resets state to unauthenticated', () async {
      final future = auth.register('Test', 'mypassphrase123');
      await Future.delayed(const Duration(milliseconds: 10));
      fakeWs.respondToLast({
        'user_id': 'u-123',
        'display_name': 'Test',
        'access_token': 'at-xxx',
        'refresh_token': 'rt-xxx',
      });
      await future;
      auth.logout();
      expect(auth.state, isA<Unauthenticated>());
    });
  });
}

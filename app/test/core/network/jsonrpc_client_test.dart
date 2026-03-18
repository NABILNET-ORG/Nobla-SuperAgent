import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';
import 'package:nobla_agent/core/network/websocket_client.dart';
import 'package:nobla_agent/shared/models/rpc_error.dart';

class FakeWebSocketClient extends WebSocketClient {
  final sentMessages = <String>[];
  final _fakeMessageController = StreamController<String>.broadcast();

  @override
  Stream<String> get messageStream => _fakeMessageController.stream;
  @override
  ConnectionStatus get currentStatus => ConnectionStatus.connected;
  @override
  void send(String message) => sentMessages.add(message);

  void simulateResponse(String json) => _fakeMessageController.add(json);

  @override
  void dispose() => _fakeMessageController.close();
}

void main() {
  late FakeWebSocketClient fakeWs;
  late JsonRpcClient rpc;

  setUp(() {
    fakeWs = FakeWebSocketClient();
    rpc = JsonRpcClient(fakeWs);
  });

  tearDown(() {
    rpc.dispose();
    fakeWs.dispose();
  });

  group('JsonRpcClient', () {
    test('call sends properly formatted JSON-RPC request', () async {
      final future = rpc.call('system.health', {});
      await Future.delayed(const Duration(milliseconds: 10));
      expect(fakeWs.sentMessages, hasLength(1));
      final sent =
          jsonDecode(fakeWs.sentMessages.first) as Map<String, dynamic>;
      expect(sent['jsonrpc'], '2.0');
      expect(sent['method'], 'system.health');
      expect(sent['id'], isA<int>());

      fakeWs.simulateResponse(jsonEncode({
        'jsonrpc': '2.0',
        'id': sent['id'],
        'result': {'status': 'ok'},
      }));

      final result = await future;
      expect(result['status'], 'ok');
    });

    test('call throws RpcError on error response', () async {
      final future = rpc.call('chat.send', {'message': 'hi'});
      await Future.delayed(const Duration(milliseconds: 10));
      final sent = jsonDecode(fakeWs.sentMessages.first);

      fakeWs.simulateResponse(jsonEncode({
        'jsonrpc': '2.0',
        'id': sent['id'],
        'error': {'code': -32011, 'message': 'Auth required'},
      }));

      expect(() => future, throwsA(isA<RpcError>()));
    });

    test('notifications are delivered via notificationStream', () async {
      final notifications = <Map<String, dynamic>>[];
      rpc.notificationStream.listen(notifications.add);

      fakeWs.simulateResponse(jsonEncode({
        'jsonrpc': '2.0',
        'method': 'system.killed',
        'params': {'stage': 'soft'},
      }));

      await Future.delayed(const Duration(milliseconds: 10));
      expect(notifications, hasLength(1));
      expect(notifications.first['method'], 'system.killed');
    });

    test('auto-increments request IDs', () async {
      // Fire two calls and ignore their futures (they'll be cleaned up on dispose)
      unawaited(rpc.call('method1', {}).catchError((_) => <String, dynamic>{}));
      unawaited(rpc.call('method2', {}).catchError((_) => <String, dynamic>{}));
      await Future.delayed(const Duration(milliseconds: 10));
      final id1 = jsonDecode(fakeWs.sentMessages[0])['id'] as int;
      final id2 = jsonDecode(fakeWs.sentMessages[1])['id'] as int;
      expect(id2, id1 + 1);
    });
  });
}

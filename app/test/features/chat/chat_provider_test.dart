import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';
import 'package:nobla_agent/core/network/websocket_client.dart';
import 'package:nobla_agent/features/chat/providers/chat_provider.dart';

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
  late ChatNotifier chat;

  setUp(() {
    fakeWs = FakeWebSocketClient();
    rpc = JsonRpcClient(fakeWs);
    chat = ChatNotifier(rpc);
  });

  tearDown(() {
    rpc.dispose();
    fakeWs.dispose();
  });

  group('ChatNotifier', () {
    test('initial state has no messages', () {
      expect(chat.state.messages, isEmpty);
      expect(chat.state.isLoading, false);
    });

    test('sendMessage adds user message and agent response', () async {
      final future = chat.sendMessage('Hello');
      await Future.delayed(const Duration(milliseconds: 10));
      expect(chat.state.messages, hasLength(1));
      expect(chat.state.messages.first.isUser, true);
      expect(chat.state.isLoading, true);

      fakeWs.respondToLast({
        'message': 'Hi there!',
        'model': 'gemini-2.0-flash',
        'tokens_used': 50,
        'cost_usd': 0.0,
        'conversation_id': null,
      });
      await future;

      expect(chat.state.messages, hasLength(2));
      expect(chat.state.messages[1].isUser, false);
      expect(chat.state.messages[1].content, 'Hi there!');
      expect(chat.state.isLoading, false);
    });
  });
}

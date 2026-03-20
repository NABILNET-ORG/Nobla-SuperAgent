import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/shared/models/rpc_error.dart';
import 'package:nobla_agent/shared/models/chat_message.dart';

void main() {
  group('RpcError', () {
    test('fromJson parses standard error', () {
      final json = {
        'code': -32011,
        'message': 'Auth required',
        'data': {'method': 'chat.send'},
      };
      final error = RpcError.fromJson(json);
      expect(error.code, -32011);
      expect(error.message, 'Auth required');
      expect(error.data?['method'], 'chat.send');
    });

    test('isAuthRequired returns true for -32011', () {
      final error = RpcError(code: -32011, message: 'Auth required');
      expect(error.isAuthRequired, true);
      expect(error.isPermissionDenied, false);
    });

    test('isBudgetExceeded returns true for -32020', () {
      final error = RpcError(code: -32020, message: 'Budget exceeded');
      expect(error.isBudgetExceeded, true);
    });

    test('isServerKilled returns true for -32030', () {
      final error = RpcError(code: -32030, message: 'Server killed');
      expect(error.isServerKilled, true);
    });
  });

  group('ChatMessage', () {
    test('fromRpcResponse maps snake_case to camelCase', () {
      final json = {
        'message': 'Hello world',
        'model': 'gemini-2.0-flash',
        'tokens_used': 142,
        'cost_usd': 0.001,
        'conversation_id': 'conv-123',
      };
      final msg = ChatMessage.fromRpcResponse(json, isUser: false);
      expect(msg.content, 'Hello world');
      expect(msg.model, 'gemini-2.0-flash');
      expect(msg.tokensUsed, 142);
      expect(msg.costUsd, 0.001);
      expect(msg.isUser, false);
    });

    test('user message factory creates correct message', () {
      final msg = ChatMessage.user('Hello');
      expect(msg.isUser, true);
      expect(msg.content, 'Hello');
      expect(msg.status, MessageStatus.sending);
    });
  });
}

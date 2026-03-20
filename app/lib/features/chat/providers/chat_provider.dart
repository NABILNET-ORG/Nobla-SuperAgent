import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';
import 'package:nobla_agent/shared/models/chat_message.dart';

class ChatState {
  final List<ChatMessage> messages;
  final bool isLoading;
  final String conversationId;

  const ChatState({
    this.messages = const [],
    this.isLoading = false,
    String? conversationId,
  }) : conversationId = conversationId ?? '';

  ChatState copyWith({List<ChatMessage>? messages, bool? isLoading}) {
    return ChatState(
      messages: messages ?? this.messages,
      isLoading: isLoading ?? this.isLoading,
      conversationId: conversationId,
    );
  }
}

class ChatNotifier extends StateNotifier<ChatState> {
  final JsonRpcClient _rpc;
  StreamSubscription? _streamSub;

  ChatNotifier(this._rpc)
      : super(ChatState(conversationId: const Uuid().v4()));

  Future<void> sendMessage(String text) async {
    final userMsg = ChatMessage.user(text);
    state = state.copyWith(
        messages: [...state.messages, userMsg], isLoading: true);

    try {
      final result = await _rpc.call('chat.send', {
        'message': text,
        'conversation_id': state.conversationId,
      });
      final agentMsg = ChatMessage.fromRpcResponse(result, isUser: false);
      final updatedMessages = state.messages.map((m) {
        if (m.id == userMsg.id) return m.copyWith(status: MessageStatus.sent);
        return m;
      }).toList();
      state = state.copyWith(
          messages: [...updatedMessages, agentMsg], isLoading: false);
    } catch (e) {
      final updatedMessages = state.messages.map((m) {
        if (m.id == userMsg.id) return m.copyWith(status: MessageStatus.error);
        return m;
      }).toList();
      state = state.copyWith(messages: updatedMessages, isLoading: false);
    }
  }

  void clearChat() {
    _streamSub?.cancel();
    state = ChatState(conversationId: const Uuid().v4());
  }

  Future<void> sendMessageStreaming(String text) async {
    final userMsg = ChatMessage.user(text);
    state = state.copyWith(
        messages: [...state.messages, userMsg], isLoading: true);
    try {
      final result = await _rpc.call('chat.stream', {
        'message': text,
        'conversation_id': state.conversationId,
      });
      final model = result['model'] as String? ?? '';
      _streamSub = _rpc.notificationStream.listen((notification) {
        final method = notification['method'] as String?;
        final params =
            notification['params'] as Map<String, dynamic>? ?? {};
        switch (method) {
          case 'chat.stream.token':
            _appendStreamToken(params['content'] as String? ?? '');
          case 'chat.stream.end':
            _finalizeStream(model);
            _streamSub?.cancel();
          case 'chat.stream.error':
            state = state.copyWith(isLoading: false);
            _streamSub?.cancel();
        }
      });
    } catch (e) {
      state = state.copyWith(isLoading: false);
    }
  }

  void _appendStreamToken(String token) {
    final messages = List<ChatMessage>.from(state.messages);
    if (messages.isNotEmpty &&
        !messages.last.isUser &&
        messages.last.status == MessageStatus.sending) {
      final last = messages.removeLast();
      messages.add(last.copyWith(content: last.content + token));
    } else {
      messages.add(ChatMessage(
        id: const Uuid().v4(),
        content: token,
        isUser: false,
        timestamp: DateTime.now(),
        status: MessageStatus.sending,
      ));
    }
    state = state.copyWith(messages: messages);
  }

  void _finalizeStream(String model) {
    final messages = List<ChatMessage>.from(state.messages);
    if (messages.isNotEmpty && !messages.last.isUser) {
      final last = messages.removeLast();
      messages.add(last.copyWith(status: MessageStatus.sent));
    }
    state = state.copyWith(messages: messages, isLoading: false);
  }

  Future<void> cancelStream() async {
    _streamSub?.cancel();
    await _rpc.call('chat.stream.cancel', {
      'conversation_id': state.conversationId,
    });
    state = state.copyWith(isLoading: false);
  }
}

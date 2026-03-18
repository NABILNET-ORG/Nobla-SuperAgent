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
    state = ChatState(conversationId: const Uuid().v4());
  }
}

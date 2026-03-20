import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/network/jsonrpc_client.dart';
import '../../../shared/models/conversation.dart';

/// State for the conversation list.
class ConversationListState {
  final List<Conversation> conversations;
  final bool isLoading;
  final String? error;

  const ConversationListState({
    this.conversations = const [],
    this.isLoading = false,
    this.error,
  });

  ConversationListState copyWith({
    List<Conversation>? conversations,
    bool? isLoading,
    String? error,
  }) {
    return ConversationListState(
      conversations: conversations ?? this.conversations,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}

/// Manages conversation list state via JSON-RPC.
class ConversationListNotifier extends StateNotifier<ConversationListState> {
  final JsonRpcClient _rpc;

  ConversationListNotifier(this._rpc) : super(const ConversationListState());

  Future<void> load({int limit = 20, int offset = 0}) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final result = await _rpc.call('conversation.list', {
        'limit': limit,
        'offset': offset,
      });
      final list = (result['conversations'] as List<dynamic>)
          .map((c) => Conversation.fromJson(c as Map<String, dynamic>))
          .toList();
      state = state.copyWith(conversations: list, isLoading: false);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<Conversation?> create({String? title}) async {
    try {
      final result = await _rpc.call('conversation.create', {
        if (title != null) 'title': title,
      });
      final conv = Conversation(
        id: result['conversation_id'] as String,
        title: result['title'] as String? ?? 'New Conversation',
      );
      state = state.copyWith(
        conversations: [conv, ...state.conversations],
      );
      return conv;
    } catch (e) {
      state = state.copyWith(error: e.toString());
      return null;
    }
  }

  Future<void> archive(String conversationId) async {
    try {
      await _rpc.call('conversation.archive', {
        'conversation_id': conversationId,
      });
      state = state.copyWith(
        conversations: state.conversations
            .where((c) => c.id != conversationId)
            .toList(),
      );
    } catch (e) {
      state = state.copyWith(error: e.toString());
    }
  }

  Future<void> rename(String conversationId, String title) async {
    try {
      await _rpc.call('conversation.rename', {
        'conversation_id': conversationId,
        'title': title,
      });
      state = state.copyWith(
        conversations: state.conversations.map((c) {
          return c.id == conversationId ? c.copyWith(title: title) : c;
        }).toList(),
      );
    } catch (e) {
      state = state.copyWith(error: e.toString());
    }
  }

  Future<List<Conversation>> search(String query) async {
    try {
      final result = await _rpc.call('conversation.search', {
        'query': query,
      });
      return (result['results'] as List<dynamic>)
          .map((c) => Conversation.fromJson(c as Map<String, dynamic>))
          .toList();
    } catch (e) {
      return [];
    }
  }
}

/// Provider for the conversation list notifier.
final conversationListProvider =
    StateNotifierProvider<ConversationListNotifier, ConversationListState>(
  (ref) {
    final rpc = ref.watch(jsonRpcProvider);
    return ConversationListNotifier(rpc);
  },
);

/// Placeholder — actual provider is in main.dart
final jsonRpcProvider = Provider<JsonRpcClient>((ref) {
  throw UnimplementedError('jsonRpcProvider must be overridden');
});

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/providers/notification_provider.dart';
import 'package:nobla_agent/features/chat/providers/chat_provider.dart';
import 'package:nobla_agent/features/chat/widgets/message_bubble.dart';
import 'package:nobla_agent/features/chat/widgets/message_input.dart';
import 'package:nobla_agent/features/chat/widgets/tool_activity_indicator.dart';
import 'package:nobla_agent/features/persona/providers/active_persona_provider.dart';
import 'package:nobla_agent/features/persona/widgets/persona_picker_sheet.dart';
import 'package:nobla_agent/main.dart';

final chatProvider = StateNotifierProvider<ChatNotifier, ChatState>((ref) {
  final rpc = ref.watch(jsonRpcProvider);
  return ChatNotifier(rpc);
});

class ChatScreen extends ConsumerWidget {
  const ChatScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final chat = ref.watch(chatProvider);
    final killState = ref.watch(killSwitchProvider);
    final isKilled = killState != KillState.running;

    return Column(
      children: [
        AppBar(
          title: GestureDetector(
            onTap: () => showModalBottomSheet(
              context: context,
              builder: (_) => const PersonaPickerSheet(),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'Nobla \u00b7 ${ref.watch(activePersonaProvider)?.name ?? "Loading..."}',
                ),
                const SizedBox(width: 4),
                const Icon(Icons.arrow_drop_down, size: 20),
              ],
            ),
          ),
          centerTitle: true,
          actions: [
            IconButton(
              icon: const Icon(Icons.delete_outline),
              onPressed: () => ref.read(chatProvider.notifier).clearChat(),
              tooltip: 'Clear chat',
            ),
          ],
        ),
        Expanded(
          child: chat.messages.isEmpty
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        Icons.chat_bubble_outline,
                        size: 64,
                        color: Theme.of(context)
                            .colorScheme
                            .onSurface
                            .withAlpha(76),
                      ),
                      const SizedBox(height: 16),
                      Text(
                        'Start a conversation',
                        style: Theme.of(context)
                            .textTheme
                            .bodyLarge
                            ?.copyWith(
                              color: Theme.of(context)
                                  .colorScheme
                                  .onSurface
                                  .withAlpha(102),
                            ),
                      ),
                    ],
                  ),
                )
              : ListView.builder(
                  reverse: true,
                  padding:
                      const EdgeInsets.only(bottom: 8, top: 8),
                  itemCount:
                      chat.messages.length + (chat.isLoading ? 1 : 0),
                  itemBuilder: (context, index) {
                    if (chat.isLoading && index == 0) {
                      return const ToolActivityIndicator();
                    }
                    final msgIndex = chat.isLoading
                        ? chat.messages.length - index
                        : chat.messages.length - 1 - index;
                    if (msgIndex < 0 ||
                        msgIndex >= chat.messages.length) {
                      return const SizedBox.shrink();
                    }
                    return MessageBubble(
                        message: chat.messages[msgIndex]);
                  },
                ),
        ),
        MessageInput(
          enabled: !chat.isLoading && !isKilled,
          onSend: (text) =>
              ref.read(chatProvider.notifier).sendMessage(text),
        ),
      ],
    );
  }
}

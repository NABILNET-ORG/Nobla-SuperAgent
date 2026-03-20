import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/conversation_provider.dart';
import '../widgets/conversation_tile.dart';

/// Sidebar drawer showing conversation history.
class ConversationDrawer extends ConsumerStatefulWidget {
  final void Function(String conversationId) onConversationSelected;

  const ConversationDrawer({
    super.key,
    required this.onConversationSelected,
  });

  @override
  ConsumerState<ConversationDrawer> createState() => _ConversationDrawerState();
}

class _ConversationDrawerState extends ConsumerState<ConversationDrawer> {
  @override
  void initState() {
    super.initState();
    // Load conversations when drawer opens
    Future.microtask(() {
      ref.read(conversationListProvider.notifier).load();
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(conversationListProvider);
    final theme = Theme.of(context);

    return Drawer(
      child: Column(
        children: [
          DrawerHeader(
            decoration: BoxDecoration(
              color: theme.colorScheme.primaryContainer,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Text(
                  'Conversations',
                  style: theme.textTheme.headlineSmall?.copyWith(
                    color: theme.colorScheme.onPrimaryContainer,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  '${state.conversations.length} conversations',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onPrimaryContainer.withValues(alpha: 0.7),
                  ),
                ),
              ],
            ),
          ),
          // New conversation button
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: FilledButton.icon(
              onPressed: _createConversation,
              icon: const Icon(Icons.add),
              label: const Text('New Conversation'),
              style: FilledButton.styleFrom(
                minimumSize: const Size.fromHeight(44),
              ),
            ),
          ),
          const Divider(),
          // Conversation list
          Expanded(
            child: state.isLoading
                ? const Center(child: CircularProgressIndicator())
                : state.conversations.isEmpty
                    ? const Center(
                        child: Text('No conversations yet'),
                      )
                    : ListView.builder(
                        itemCount: state.conversations.length,
                        itemBuilder: (context, index) {
                          final conv = state.conversations[index];
                          return ConversationTile(
                            conversation: conv,
                            onTap: () {
                              widget.onConversationSelected(conv.id);
                              Navigator.of(context).pop();
                            },
                            onArchive: () => _archiveConversation(conv.id),
                          );
                        },
                      ),
          ),
        ],
      ),
    );
  }

  Future<void> _createConversation() async {
    final conv =
        await ref.read(conversationListProvider.notifier).create();
    if (conv != null && mounted) {
      widget.onConversationSelected(conv.id);
      Navigator.of(context).pop();
    }
  }

  void _archiveConversation(String id) {
    ref.read(conversationListProvider.notifier).archive(id);
  }
}

import 'package:flutter/material.dart';
import '../../../shared/models/conversation.dart';

/// A single conversation item in the drawer list.
class ConversationTile extends StatelessWidget {
  final Conversation conversation;
  final VoidCallback onTap;
  final VoidCallback onArchive;

  const ConversationTile({
    super.key,
    required this.conversation,
    required this.onTap,
    required this.onArchive,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return ListTile(
      leading: CircleAvatar(
        backgroundColor: theme.colorScheme.secondaryContainer,
        child: Text(
          conversation.title.isNotEmpty
              ? conversation.title[0].toUpperCase()
              : '?',
          style: TextStyle(
            color: theme.colorScheme.onSecondaryContainer,
          ),
        ),
      ),
      title: Text(
        conversation.title,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: conversation.summary != null
          ? Text(
              conversation.summary!,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodySmall,
            )
          : Text(
              '${conversation.messageCount} messages',
              style: theme.textTheme.bodySmall,
            ),
      trailing: IconButton(
        icon: const Icon(Icons.delete_outline, size: 20),
        onPressed: onArchive,
        tooltip: 'Archive',
      ),
      onTap: onTap,
    );
  }
}

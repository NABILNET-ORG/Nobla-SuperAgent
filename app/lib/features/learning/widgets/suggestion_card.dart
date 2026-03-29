import 'package:flutter/material.dart';
import 'package:nobla_agent/features/learning/models/learning_models.dart';

class SuggestionCard extends StatelessWidget {
  final String title;
  final String description;
  final SuggestionType type;
  final VoidCallback onAccept;
  final VoidCallback onDismiss;
  final ValueChanged<int> onSnooze;

  const SuggestionCard({
    super.key,
    required this.title,
    required this.description,
    required this.type,
    required this.onAccept,
    required this.onDismiss,
    required this.onSnooze,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 4),
            Text(description, style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 8),
            Row(
              children: [
                TextButton(onPressed: onAccept, child: const Text('Accept')),
                PopupMenuButton<int>(
                  child: const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    child: Text('Snooze'),
                  ),
                  onSelected: onSnooze,
                  itemBuilder: (context) => [
                    const PopupMenuItem(value: 1, child: Text('1 day')),
                    const PopupMenuItem(value: 3, child: Text('3 days')),
                    const PopupMenuItem(value: 7, child: Text('7 days')),
                  ],
                ),
                TextButton(onPressed: onDismiss, child: const Text('Dismiss')),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:nobla_agent/features/learning/models/learning_models.dart';

class PatternCard extends StatelessWidget {
  final String description;
  final PatternStatus status;
  final double confidence;
  final VoidCallback onReview;
  final VoidCallback onDismiss;

  const PatternCard({
    super.key,
    required this.description,
    required this.status,
    required this.confidence,
    required this.onReview,
    required this.onDismiss,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.pattern, size: 20),
                const SizedBox(width: 8),
                Expanded(child: Text(description, style: Theme.of(context).textTheme.bodyMedium)),
                Chip(label: Text(status.name, style: const TextStyle(fontSize: 11))),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Text('${(confidence * 100).toInt()}% confidence',
                    style: Theme.of(context).textTheme.bodySmall),
                const Spacer(),
                TextButton(onPressed: onReview, child: const Text('Review')),
                TextButton(onPressed: onDismiss, child: const Text('Dismiss')),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

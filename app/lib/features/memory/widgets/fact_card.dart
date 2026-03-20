import 'package:flutter/material.dart';
import '../../../shared/models/memory_fact.dart';

/// Card displaying a single memory fact.
class FactCard extends StatelessWidget {
  final MemoryFact fact;

  const FactCard({super.key, required this.fact});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.secondaryContainer,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    fact.noteType,
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: theme.colorScheme.onSecondaryContainer,
                    ),
                  ),
                ),
                const Spacer(),
                if (fact.confidence != null)
                  Text(
                    '${(fact.confidence! * 100).round()}%',
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: Colors.grey,
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 8),
            Text(fact.content),
            if (fact.keywords.isNotEmpty) ...[
              const SizedBox(height: 8),
              Wrap(
                spacing: 4,
                children: fact.keywords
                    .take(5)
                    .map((k) => Chip(
                          label: Text(k),
                          visualDensity: VisualDensity.compact,
                          labelStyle: theme.textTheme.labelSmall,
                        ))
                    .toList(),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

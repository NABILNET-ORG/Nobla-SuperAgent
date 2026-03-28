import 'package:flutter/material.dart';

/// Small chip showing which part of the user's NL text generated a step.
///
/// Used in the NL Workflow Creator preview to build trust in parsing.
class NlSourceChip extends StatelessWidget {
  final String source;

  const NlSourceChip({super.key, required this.source});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      key: const ValueKey('nl_chip'),
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: theme.colorScheme.tertiaryContainer,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.format_quote,
              size: 10, color: theme.colorScheme.onTertiaryContainer),
          const SizedBox(width: 3),
          Flexible(
            child: Text(
              source,
              style: TextStyle(
                fontSize: 9,
                color: theme.colorScheme.onTertiaryContainer,
                fontStyle: FontStyle.italic,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}

import 'package:flutter/material.dart';

class StreamingMessage extends StatelessWidget {
  final String text;
  final String model;
  final bool isStreaming;
  final VoidCallback? onCancel;

  const StreamingMessage({
    super.key,
    required this.text,
    required this.model,
    required this.isStreaming,
    this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(12),
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (isStreaming)
            Row(
              children: [
                SizedBox(
                  width: 12,
                  height: 12,
                  child: CircularProgressIndicator(
                    strokeWidth: 1.5,
                    color: theme.colorScheme.primary,
                  ),
                ),
                const SizedBox(width: 8),
                Text(model, style: theme.textTheme.labelSmall),
                const Spacer(),
                if (onCancel != null)
                  IconButton(
                    icon: const Icon(Icons.stop_circle_outlined, size: 20),
                    onPressed: onCancel,
                    tooltip: 'Stop generating',
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                  ),
              ],
            ),
          if (isStreaming) const SizedBox(height: 8),
          Text(
            text.isEmpty && isStreaming ? '...' : text,
            style: theme.textTheme.bodyMedium,
          ),
        ],
      ),
    );
  }
}

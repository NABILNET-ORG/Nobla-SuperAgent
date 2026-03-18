import 'package:flutter/material.dart';
import 'package:shimmer/shimmer.dart';

class ToolActivityIndicator extends StatelessWidget {
  final String text;
  const ToolActivityIndicator({super.key, this.text = 'Thinking...'});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4, horizontal: 12),
        padding: const EdgeInsets.all(12),
        child: Shimmer.fromColors(
          baseColor:
              Theme.of(context).colorScheme.onSurface.withAlpha(102),
          highlightColor: Theme.of(context).colorScheme.primary,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
              const SizedBox(width: 8),
              Text(text, style: Theme.of(context).textTheme.bodyMedium),
            ],
          ),
        ),
      ),
    );
  }
}

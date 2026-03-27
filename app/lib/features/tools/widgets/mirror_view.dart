import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/features/tools/providers/tool_mirror_provider.dart';

/// Displays the latest screenshot with pinch-to-zoom and manual capture.
class MirrorView extends ConsumerWidget {
  const MirrorView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final mirror = ref.watch(toolMirrorProvider);

    return Column(
      children: [
        // Status bar
        _MirrorStatusBar(mirror: mirror, ref: ref),
        const Divider(height: 1),
        // Screenshot area
        Expanded(
          child: mirror.latestScreenshot != null
              ? InteractiveViewer(
                  minScale: 0.5,
                  maxScale: 4.0,
                  child: Center(
                    child: Stack(
                      alignment: Alignment.center,
                      children: [
                        Image.memory(
                          mirror.latestScreenshot!,
                          fit: BoxFit.contain,
                          gaplessPlayback: true,
                        ),
                        if (mirror.isCapturing)
                          Container(
                            color: Colors.black26,
                            child: const CircularProgressIndicator(),
                          ),
                      ],
                    ),
                  ),
                )
              : _MirrorPlaceholder(
                  error: mirror.error,
                  isCapturing: mirror.isCapturing,
                ),
        ),
      ],
    );
  }
}

class _MirrorStatusBar extends StatelessWidget {
  final MirrorState mirror;
  final WidgetRef ref;
  const _MirrorStatusBar({required this.mirror, required this.ref});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          // Subscription indicator
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              color: mirror.isSubscribed ? Colors.green : Colors.red,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 8),
          Text(
            mirror.isSubscribed ? 'Live' : 'Paused',
            style: theme.textTheme.labelMedium,
          ),
          if (mirror.lastUpdated != null) ...[
            const SizedBox(width: 8),
            Text(
              _formatLastUpdated(mirror.lastUpdated!),
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
          const Spacer(),
          // Capture button
          IconButton(
            icon: const Icon(Icons.camera_alt_outlined),
            tooltip: 'Capture Now',
            onPressed: mirror.isCapturing
                ? null
                : () => ref.read(toolMirrorProvider.notifier).captureNow(),
          ),
        ],
      ),
    );
  }

  String _formatLastUpdated(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inSeconds < 60) return 'Updated ${diff.inSeconds}s ago';
    if (diff.inMinutes < 60) return 'Updated ${diff.inMinutes}m ago';
    return 'Updated ${diff.inHours}h ago';
  }
}

class _MirrorPlaceholder extends StatelessWidget {
  final String? error;
  final bool isCapturing;
  const _MirrorPlaceholder({this.error, this.isCapturing = false});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (isCapturing) {
      return const Center(child: CircularProgressIndicator());
    }
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            error != null ? Icons.error_outline : Icons.screenshot_monitor,
            size: 48,
            color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.4),
          ),
          const SizedBox(height: 12),
          Text(
            error ?? 'No screenshots yet',
            style: theme.textTheme.bodyMedium?.copyWith(
              color:
                  theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.6),
            ),
            textAlign: TextAlign.center,
          ),
          if (error == null) ...[
            const SizedBox(height: 4),
            Text(
              'Activity will appear here when tools execute',
              style: theme.textTheme.bodySmall?.copyWith(
                color:
                    theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.4),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

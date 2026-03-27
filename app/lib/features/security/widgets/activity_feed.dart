import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/shared/providers/tool_activity_provider.dart';

/// Scrollable list showing real-time tool execution activity.
///
/// Displays entries from the shared [ToolActivityNotifier], most recent
/// first, capped at 200 entries (enforced by the notifier).
class ActivityFeed extends ConsumerWidget {
  const ActivityFeed({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final activities = ref.watch(toolActivityProvider);

    if (activities.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.history,
              size: 48,
              color: Theme.of(context)
                  .colorScheme
                  .onSurfaceVariant
                  .withValues(alpha: 0.4),
            ),
            const SizedBox(height: 12),
            Text(
              'No activity yet',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: Theme.of(context)
                        .colorScheme
                        .onSurfaceVariant
                        .withValues(alpha: 0.6),
                  ),
            ),
          ],
        ),
      );
    }

    return ListView.separated(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      itemCount: activities.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (context, index) => _ActivityTile(entry: activities[index]),
    );
  }
}

// ---------------------------------------------------------------------------
// Single activity row
// ---------------------------------------------------------------------------

class _ActivityTile extends StatelessWidget {
  final ActivityEntry entry;

  const _ActivityTile({required this.entry});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: _StatusIcon(status: entry.status),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Tool name + action
                Text(
                  entry.action.isNotEmpty
                      ? '${entry.toolName} \u2022 ${entry.action}'
                      : entry.toolName,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                if (entry.description.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(
                    entry.description,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: colorScheme.onSurfaceVariant,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
                const SizedBox(height: 4),
                // Execution time + relative timestamp
                Row(
                  children: [
                    if (entry.executionTimeMs != null) ...[
                      Text(
                        '${entry.executionTimeMs}ms',
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: colorScheme.onSurfaceVariant
                              .withValues(alpha: 0.7),
                        ),
                      ),
                      const SizedBox(width: 8),
                    ],
                    Text(
                      _formatRelativeTime(entry.timestamp),
                      style: theme.textTheme.labelSmall?.copyWith(
                        color:
                            colorScheme.onSurfaceVariant.withValues(alpha: 0.7),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Status icon
// ---------------------------------------------------------------------------

class _StatusIcon extends StatelessWidget {
  final ActivityStatus status;

  const _StatusIcon({required this.status});

  @override
  Widget build(BuildContext context) {
    return switch (status) {
      ActivityStatus.success => const Icon(
          Icons.check_circle,
          color: Colors.green,
          size: 20,
        ),
      ActivityStatus.pending => const SizedBox(
          width: 20,
          height: 20,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: Colors.amber,
          ),
        ),
      ActivityStatus.denied => const Icon(
          Icons.cancel,
          color: Colors.red,
          size: 20,
        ),
      ActivityStatus.failed => const Icon(
          Icons.error,
          color: Colors.red,
          size: 20,
        ),
    };
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Formats a [DateTime] as a human-readable relative time string.
///
/// Returns "Xs ago", "Xm ago", or "Xh ago" depending on elapsed time.
String _formatRelativeTime(DateTime timestamp) {
  final diff = DateTime.now().difference(timestamp);

  if (diff.inSeconds < 60) {
    final s = diff.inSeconds;
    return '${s}s ago';
  }
  if (diff.inMinutes < 60) {
    return '${diff.inMinutes}m ago';
  }
  return '${diff.inHours}h ago';
}

// ---------------------------------------------------------------------------
// WebSocket wiring guide
// ---------------------------------------------------------------------------

/// ## WebSocket Integration
///
/// In the WebSocket message handler (where incoming JSON-RPC messages are
/// dispatched), add the following branches to wire approval requests and
/// activity events into the provider:
///
/// ```dart
/// if (method == 'tool.approval_request') {
///   final request = ApprovalRequest.fromJson(params);
///   ref.read(approvalProvider.notifier).onApprovalRequest(request);
///   showApprovalSheet(context, request: request, provider: approvalProvider);
/// } else if (method == 'tool.activity') {
///   ref.read(approvalProvider.notifier).onActivity(
///     ActivityEntry.fromJson(params),
///   );
/// }
/// ```
///
/// Where `approvalProvider` is the [StateNotifierProvider] instance that owns
/// the [ApprovalNotifier] for the current session, and `context` is a valid
/// [BuildContext] for showing the approval bottom sheet.

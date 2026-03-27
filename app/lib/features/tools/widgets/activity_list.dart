import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/features/tools/providers/filtered_activity_provider.dart';
import 'package:nobla_agent/features/tools/widgets/activity_detail_sheet.dart';
import 'package:nobla_agent/features/tools/widgets/activity_filter_bar.dart';
import 'package:nobla_agent/features/tools/widgets/tool_category_section.dart';

/// Full activity feed tab with filter bar and scrollable list.
class ActivityListTab extends ConsumerWidget {
  const ActivityListTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final entries = ref.watch(filteredActivityProvider);
    final filter = ref.watch(activityFilterProvider);

    return Column(
      children: [
        const ActivityFilterBar(),
        const Divider(height: 1),
        Expanded(
          child: entries.isEmpty
              ? _EmptyState(hasFilter: filter.isActive)
              : ListView.separated(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  itemCount: entries.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, index) => _ActivityRow(
                    entry: entries[index],
                    onTap: () =>
                        showActivityDetailSheet(context, entries[index]),
                  ),
                ),
        ),
      ],
    );
  }
}

class _EmptyState extends StatelessWidget {
  final bool hasFilter;
  const _EmptyState({required this.hasFilter});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            hasFilter ? Icons.filter_list_off : Icons.history,
            size: 48,
            color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.4),
          ),
          const SizedBox(height: 12),
          Text(
            hasFilter ? 'No matches for current filters' : 'No activity yet',
            style: theme.textTheme.bodyMedium?.copyWith(
              color:
                  theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.6),
            ),
          ),
        ],
      ),
    );
  }
}

class _ActivityRow extends StatelessWidget {
  final ActivityEntry entry;
  final VoidCallback onTap;
  const _ActivityRow({required this.entry, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final (icon, color) = entry.category != null
        ? categoryStyle(entry.category!)
        : (Icons.build, Colors.grey);
    final statusColor = switch (entry.status) {
      ActivityStatus.success => Colors.green,
      ActivityStatus.failed => Colors.red,
      ActivityStatus.denied => Colors.orange,
      ActivityStatus.pending => Colors.grey,
    };

    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Row(
          children: [
            // Category icon + status dot
            Stack(
              children: [
                Icon(icon, color: color, size: 24),
                Positioned(
                  right: -2,
                  bottom: -2,
                  child: Container(
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(
                      color: statusColor,
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: theme.colorScheme.surface,
                        width: 1.5,
                      ),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(width: 12),
            // Content
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    entry.toolName,
                    style: theme.textTheme.bodyMedium
                        ?.copyWith(fontWeight: FontWeight.w600),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (entry.description.isNotEmpty) ...[
                    const SizedBox(height: 2),
                    Text(
                      entry.description,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ],
              ),
            ),
            // Trailing
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                if (entry.executionTimeMs != null)
                  Text(
                    '${entry.executionTimeMs}ms',
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant
                          .withValues(alpha: 0.7),
                    ),
                  ),
                Text(
                  _formatRelativeTime(entry.timestamp),
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant
                        .withValues(alpha: 0.7),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _formatRelativeTime(DateTime timestamp) {
    final diff = DateTime.now().difference(timestamp);
    if (diff.inSeconds < 60) return '${diff.inSeconds}s ago';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    return '${diff.inHours}h ago';
  }
}

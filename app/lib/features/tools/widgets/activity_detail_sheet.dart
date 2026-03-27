import 'package:flutter/material.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/features/tools/widgets/tool_category_section.dart';

/// Shows full details for a single activity entry.
void showActivityDetailSheet(BuildContext context, ActivityEntry entry) {
  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
    ),
    builder: (_) => _ActivityDetailContent(entry: entry),
  );
}

class _ActivityDetailContent extends StatelessWidget {
  final ActivityEntry entry;
  const _ActivityDetailContent({required this.entry});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final (icon, color) = entry.category != null
        ? categoryStyle(entry.category!)
        : (Icons.build, Colors.grey);

    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Drag handle
          Center(
            child: Container(
              width: 32,
              height: 4,
              decoration: BoxDecoration(
                color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.3),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Tool name + category chip
          Row(
            children: [
              Icon(icon, color: color, size: 20),
              const SizedBox(width: 8),
              Text(
                entry.toolName,
                style: theme.textTheme.titleMedium
                    ?.copyWith(fontWeight: FontWeight.w600),
              ),
              const Spacer(),
              _StatusBadge(status: entry.status),
            ],
          ),
          const SizedBox(height: 12),

          // Description
          if (entry.description.isNotEmpty)
            Text(entry.description, style: theme.textTheme.bodyMedium),
          const SizedBox(height: 12),

          // Metadata row
          Row(
            children: [
              if (entry.executionTimeMs != null) ...[
                Icon(Icons.timer_outlined,
                    size: 14, color: theme.colorScheme.onSurfaceVariant),
                const SizedBox(width: 4),
                Text('${entry.executionTimeMs}ms',
                    style: theme.textTheme.bodySmall),
                const SizedBox(width: 16),
              ],
              Icon(Icons.schedule,
                  size: 14, color: theme.colorScheme.onSurfaceVariant),
              const SizedBox(width: 4),
              Text(
                _formatAbsoluteTime(entry.timestamp),
                style: theme.textTheme.bodySmall,
              ),
            ],
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }

  String _formatAbsoluteTime(DateTime dt) {
    final months = [
      '', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
    ];
    final h = dt.hour > 12 ? dt.hour - 12 : (dt.hour == 0 ? 12 : dt.hour);
    final amPm = dt.hour >= 12 ? 'PM' : 'AM';
    final min = dt.minute.toString().padLeft(2, '0');
    final sec = dt.second.toString().padLeft(2, '0');
    return '${months[dt.month]} ${dt.day}, ${dt.year} at $h:$min:$sec $amPm';
  }
}

class _StatusBadge extends StatelessWidget {
  final ActivityStatus status;
  const _StatusBadge({required this.status});

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (status) {
      ActivityStatus.success => ('Success', Colors.green),
      ActivityStatus.failed => ('Failed', Colors.red),
      ActivityStatus.denied => ('Denied', Colors.orange),
      ActivityStatus.pending => ('Pending', Colors.grey),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        label,
        style: TextStyle(
            fontSize: 12, fontWeight: FontWeight.w600, color: color),
      ),
    );
  }
}

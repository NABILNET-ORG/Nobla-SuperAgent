import 'package:flutter/material.dart';
import 'package:nobla_agent/features/automation/models/workflow_models.dart';
import 'package:nobla_agent/features/automation/widgets/step_node_widget.dart';

/// Bottom sheet showing step details, inline edit, and quick actions.
class StepBottomSheet extends StatelessWidget {
  final WorkflowStep step;
  final StepExecutionResult? executionResult;
  final VoidCallback? onRetry;
  final VoidCallback? onSkip;
  final VoidCallback? onPause;

  const StepBottomSheet({
    super.key,
    required this.step,
    this.executionResult,
    this.onRetry,
    this.onSkip,
    this.onPause,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = stepTypeColor(step.type);

    return Container(
      key: const ValueKey('step_sheet'),
      padding: const EdgeInsets.all(16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Row(
            children: [
              Icon(stepTypeIcon(step.type), color: color, size: 24),
              const SizedBox(width: 8),
              Expanded(
                child: Text(step.name, style: theme.textTheme.titleMedium),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(step.type.label,
                    style: TextStyle(color: color, fontSize: 12)),
              ),
            ],
          ),
          const SizedBox(height: 12),

          // NL source attribution
          if (step.nlSource != null) ...[
            Container(
              key: const ValueKey('nl_source'),
              width: double.infinity,
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(6),
              ),
              child: Row(
                children: [
                  Icon(Icons.format_quote, size: 14,
                      color: theme.colorScheme.outline),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      step.nlSource!,
                      style: theme.textTheme.bodySmall?.copyWith(
                        fontStyle: FontStyle.italic,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 8),
          ],

          // Config summary
          if (step.config.isNotEmpty) ...[
            Text('Configuration',
                style: theme.textTheme.labelMedium
                    ?.copyWith(color: theme.colorScheme.outline)),
            const SizedBox(height: 4),
            ...step.config.entries.take(4).map((e) => Padding(
                  padding: const EdgeInsets.only(bottom: 2),
                  child: Row(
                    children: [
                      Text('${e.key}: ',
                          style: theme.textTheme.bodySmall
                              ?.copyWith(fontWeight: FontWeight.w600)),
                      Expanded(
                        child: Text('${e.value}',
                            style: theme.textTheme.bodySmall,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis),
                      ),
                    ],
                  ),
                )),
            const SizedBox(height: 8),
          ],

          // Dependencies
          if (step.dependsOn.isNotEmpty) ...[
            Text('Depends on: ${step.dependsOn.length} step(s)',
                style: theme.textTheme.bodySmall),
            const SizedBox(height: 4),
          ],

          // Error handling
          Text(
            'On error: ${step.errorHandling.name}',
            style: theme.textTheme.bodySmall
                ?.copyWith(color: theme.colorScheme.outline),
          ),
          const SizedBox(height: 12),

          // Execution result
          if (executionResult != null) ...[
            const Divider(),
            const SizedBox(height: 8),
            _ExecutionResultSection(result: executionResult!),
            const SizedBox(height: 12),
          ],

          // Quick actions
          if (_hasQuickActions) ...[
            const Divider(),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                if (onRetry != null)
                  _QuickAction(
                    key: const ValueKey('action_retry'),
                    icon: Icons.replay,
                    label: 'Retry',
                    color: Colors.blue,
                    onTap: onRetry!,
                  ),
                if (onSkip != null)
                  _QuickAction(
                    key: const ValueKey('action_skip'),
                    icon: Icons.skip_next,
                    label: 'Skip',
                    color: Colors.orange,
                    onTap: onSkip!,
                  ),
                if (onPause != null)
                  _QuickAction(
                    key: const ValueKey('action_pause'),
                    icon: Icons.pause,
                    label: 'Pause',
                    color: Colors.amber,
                    onTap: onPause!,
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  bool get _hasQuickActions =>
      onRetry != null || onSkip != null || onPause != null;
}

class _ExecutionResultSection extends StatelessWidget {
  final StepExecutionResult result;
  const _ExecutionResultSection({required this.result});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final statusColor = switch (result.status) {
      ExecutionStatus.completed => Colors.green,
      ExecutionStatus.failed => Colors.red,
      ExecutionStatus.running => Colors.blue,
      _ => Colors.grey,
    };

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text('Status: ', style: theme.textTheme.labelMedium),
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
              decoration: BoxDecoration(
                color: statusColor.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(result.status.label,
                  style: TextStyle(color: statusColor, fontSize: 11)),
            ),
          ],
        ),
        if (result.branchTaken != null)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text('Branch: ${result.branchTaken}',
                style: theme.textTheme.bodySmall),
          ),
        if (result.error != null)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text('Error: ${result.error}',
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: Colors.red)),
          ),
      ],
    );
  }
}

class _QuickAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  const _QuickAction({
    super.key,
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: color, size: 20),
            const SizedBox(height: 2),
            Text(label, style: TextStyle(color: color, fontSize: 10)),
          ],
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/automation/models/workflow_models.dart';
import 'package:nobla_agent/features/automation/providers/workflow_providers.dart';
import 'package:nobla_agent/features/automation/widgets/workflow_dag_view.dart';

/// Detail screen for a workflow — header, triggers, DAG, execution history.
class WorkflowDetailScreen extends ConsumerWidget {
  final String workflowId;

  const WorkflowDetailScreen({super.key, required this.workflowId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detailAsync = ref.watch(workflowDetailProvider(workflowId));

    return Scaffold(
      appBar: AppBar(title: const Text('Workflow')),
      body: detailAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Text('Error: $e', key: const ValueKey('error')),
        ),
        data: (wf) => _DetailBody(workflow: wf, workflowId: workflowId),
      ),
    );
  }
}

class _DetailBody extends ConsumerWidget {
  final WorkflowDefinition workflow;
  final String workflowId;

  const _DetailBody({required this.workflow, required this.workflowId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final execution = ref.watch(workflowExecutionProvider(workflowId));
    final execStates = <String, ExecutionStatus>{};
    final stepResults = <String, StepExecutionResult>{};

    if (execution != null) {
      for (final entry in execution.stepExecutions.entries) {
        execStates[entry.key] = entry.value.status;
        stepResults[entry.key] = entry.value;
      }
    }

    final layout = computeDagLayout(workflow.steps);

    return CustomScrollView(
      slivers: [
        // Header
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        workflow.name,
                        key: const ValueKey('wf_name'),
                        style: theme.textTheme.headlineSmall,
                      ),
                    ),
                    _VersionBadge(version: workflow.version),
                    const SizedBox(width: 8),
                    _StatusToggle(
                      status: workflow.status,
                      onToggle: () {
                        // Toggle pause/active — will wire to service
                      },
                    ),
                  ],
                ),
                if (workflow.description.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(workflow.description,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: theme.colorScheme.outline,
                      )),
                ],
              ],
            ),
          ),
        ),

        // Triggers section
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Triggers',
                    style: theme.textTheme.titleSmall,
                    key: const ValueKey('triggers_header')),
                const SizedBox(height: 6),
                if (workflow.triggers.isEmpty)
                  Text('No triggers configured',
                      style: theme.textTheme.bodySmall)
                else
                  ...workflow.triggers.map((t) => Card(
                        key: ValueKey('trigger_${t.triggerId}'),
                        margin: const EdgeInsets.only(bottom: 6),
                        child: ListTile(
                          dense: true,
                          leading: const Icon(Icons.bolt, size: 18),
                          title: Text(t.eventPattern,
                              style: theme.textTheme.bodyMedium),
                          subtitle: t.conditions.isNotEmpty
                              ? Text(
                                  '${t.conditions.length} condition(s)',
                                  style: theme.textTheme.bodySmall,
                                )
                              : null,
                          trailing: Icon(
                            t.active
                                ? Icons.check_circle
                                : Icons.cancel_outlined,
                            color: t.active ? Colors.green : Colors.grey,
                            size: 18,
                          ),
                        ),
                      )),
                const SizedBox(height: 12),
              ],
            ),
          ),
        ),

        // DAG visualization
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text('Steps',
                        style: theme.textTheme.titleSmall,
                        key: const ValueKey('steps_header')),
                    const Spacer(),
                    if (execution != null)
                      _ExecutionStatusChip(status: execution.status),
                  ],
                ),
                const SizedBox(height: 8),
                SizedBox(
                  height: (layout.height + 80).clamp(120, 400),
                  child: WorkflowDagView(
                    key: const ValueKey('detail_dag'),
                    steps: workflow.steps,
                    layout: layout,
                    executionStates: execStates,
                    stepResults: stepResults,
                  ),
                ),
                const SizedBox(height: 12),
              ],
            ),
          ),
        ),

        // Execution history header
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Text('Execution History',
                style: theme.textTheme.titleSmall,
                key: const ValueKey('history_header')),
          ),
        ),

        // Execution history list (placeholder — populated via provider)
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Text(
              'Trigger a run to see execution history here.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.outline,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _VersionBadge extends StatelessWidget {
  final int version;
  const _VersionBadge({required this.version});

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const ValueKey('version_badge'),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.secondaryContainer,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        'v$version',
        style: TextStyle(
          fontSize: 12,
          color: Theme.of(context).colorScheme.onSecondaryContainer,
        ),
      ),
    );
  }
}

class _StatusToggle extends StatelessWidget {
  final WorkflowStatus status;
  final VoidCallback onToggle;
  const _StatusToggle({required this.status, required this.onToggle});

  @override
  Widget build(BuildContext context) {
    final isActive = status == WorkflowStatus.active;
    return IconButton(
      key: const ValueKey('status_toggle'),
      icon: Icon(
        isActive ? Icons.pause_circle_outline : Icons.play_circle_outline,
        color: isActive ? Colors.orange : Colors.green,
      ),
      onPressed: onToggle,
      tooltip: isActive ? 'Pause' : 'Resume',
    );
  }
}

class _ExecutionStatusChip extends StatelessWidget {
  final ExecutionStatus status;
  const _ExecutionStatusChip({required this.status});

  @override
  Widget build(BuildContext context) {
    final color = switch (status) {
      ExecutionStatus.running => Colors.blue,
      ExecutionStatus.completed => Colors.green,
      ExecutionStatus.failed => Colors.red,
      _ => Colors.grey,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(status.label,
          style: TextStyle(color: color, fontSize: 11)),
    );
  }
}

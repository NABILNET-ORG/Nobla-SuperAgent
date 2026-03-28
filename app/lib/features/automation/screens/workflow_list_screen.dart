import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/automation/models/workflow_models.dart';
import 'package:nobla_agent/features/automation/providers/workflow_providers.dart';

/// Filter chip state for workflow list.
enum WorkflowFilter { all, active, paused, failed }

/// Displays the user's workflows as cards with filters and FAB.
class WorkflowListScreen extends ConsumerStatefulWidget {
  const WorkflowListScreen({super.key});

  @override
  ConsumerState<WorkflowListScreen> createState() => _WorkflowListScreenState();
}

class _WorkflowListScreenState extends ConsumerState<WorkflowListScreen> {
  WorkflowFilter _filter = WorkflowFilter.all;

  @override
  Widget build(BuildContext context) {
    final workflowsAsync = ref.watch(workflowListProvider);
    final theme = Theme.of(context);

    return Scaffold(
      body: Column(
        children: [
          // Filter chips
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Row(
              children: WorkflowFilter.values.map((f) {
                return Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: FilterChip(
                    key: ValueKey('filter_${f.name}'),
                    label: Text(f.name[0].toUpperCase() + f.name.substring(1)),
                    selected: _filter == f,
                    onSelected: (_) => setState(() => _filter = f),
                  ),
                );
              }).toList(),
            ),
          ),
          // Workflow list
          Expanded(
            child: workflowsAsync.when(
              loading: () => const Center(
                child: CircularProgressIndicator(key: ValueKey('loading')),
              ),
              error: (e, _) => Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.error_outline, size: 48, color: theme.colorScheme.error),
                    const SizedBox(height: 8),
                    Text('Failed to load workflows', style: theme.textTheme.bodyLarge),
                    const SizedBox(height: 8),
                    FilledButton.tonal(
                      onPressed: () => ref.invalidate(workflowListProvider),
                      child: const Text('Retry'),
                    ),
                  ],
                ),
              ),
              data: (workflows) {
                final filtered = _applyFilter(workflows);
                if (filtered.isEmpty) {
                  return Center(
                    key: const ValueKey('empty'),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.account_tree_outlined, size: 64,
                            color: theme.colorScheme.outline),
                        const SizedBox(height: 12),
                        Text(
                          _filter == WorkflowFilter.all
                              ? 'No workflows yet'
                              : 'No ${_filter.name} workflows',
                          style: theme.textTheme.titleMedium,
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Tap + to create one from natural language',
                          style: theme.textTheme.bodySmall,
                        ),
                      ],
                    ),
                  );
                }
                return RefreshIndicator(
                  onRefresh: () async => ref.invalidate(workflowListProvider),
                  child: ListView.builder(
                    key: const ValueKey('workflow_list'),
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    itemCount: filtered.length,
                    itemBuilder: (context, index) =>
                        WorkflowCard(workflow: filtered[index]),
                  ),
                );
              },
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        key: const ValueKey('create_fab'),
        onPressed: () => _showCreateDialog(context),
        child: const Icon(Icons.add),
      ),
    );
  }

  List<WorkflowDefinition> _applyFilter(List<WorkflowDefinition> workflows) {
    return switch (_filter) {
      WorkflowFilter.all => workflows,
      WorkflowFilter.active =>
        workflows.where((w) => w.status == WorkflowStatus.active).toList(),
      WorkflowFilter.paused =>
        workflows.where((w) => w.status == WorkflowStatus.paused).toList(),
      WorkflowFilter.failed => workflows,
    };
  }

  void _showCreateDialog(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => const WorkflowCreateSheet(),
    );
  }
}

/// Card displaying a workflow summary.
class WorkflowCard extends StatelessWidget {
  final WorkflowDefinition workflow;
  const WorkflowCard({super.key, required this.workflow});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      key: ValueKey('workflow_${workflow.workflowId}'),
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: _statusIcon(workflow.status),
        title: Text(workflow.name, maxLines: 1, overflow: TextOverflow.ellipsis),
        subtitle: Text(
          '${workflow.stepCount} steps \u2022 ${workflow.triggerCount} triggers \u2022 v${workflow.version}',
          style: theme.textTheme.bodySmall,
        ),
        trailing: _StatusBadge(status: workflow.status),
        onTap: () {
          // Navigate to detail — will be wired in Step 12
        },
      ),
    );
  }

  Widget _statusIcon(WorkflowStatus status) => switch (status) {
        WorkflowStatus.active =>
          const Icon(Icons.play_circle_outline, color: Colors.green),
        WorkflowStatus.paused =>
          const Icon(Icons.pause_circle_outline, color: Colors.orange),
        WorkflowStatus.archived =>
          const Icon(Icons.archive_outlined, color: Colors.grey),
      };
}

class _StatusBadge extends StatelessWidget {
  final WorkflowStatus status;
  const _StatusBadge({required this.status});

  @override
  Widget build(BuildContext context) {
    final (color, label) = switch (status) {
      WorkflowStatus.active => (Colors.green, 'Active'),
      WorkflowStatus.paused => (Colors.orange, 'Paused'),
      WorkflowStatus.archived => (Colors.grey, 'Archived'),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(label, style: TextStyle(color: color, fontSize: 12)),
    );
  }
}

/// Bottom sheet for creating a workflow via NL input.
class WorkflowCreateSheet extends StatefulWidget {
  const WorkflowCreateSheet({super.key});

  @override
  State<WorkflowCreateSheet> createState() => _WorkflowCreateSheetState();
}

class _WorkflowCreateSheetState extends State<WorkflowCreateSheet> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 16,
        right: 16,
        top: 16,
        bottom: MediaQuery.of(context).viewInsets.bottom + 16,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Create Workflow',
              style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          TextField(
            key: const ValueKey('nl_input'),
            controller: _controller,
            maxLines: 3,
            decoration: const InputDecoration(
              hintText: 'Describe your workflow in plain language...',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          FilledButton(
            key: const ValueKey('create_btn'),
            onPressed: _controller.text.trim().length >= 5
                ? () => Navigator.of(context).pop(_controller.text.trim())
                : null,
            child: const Text('Create'),
          ),
        ],
      ),
    );
  }
}

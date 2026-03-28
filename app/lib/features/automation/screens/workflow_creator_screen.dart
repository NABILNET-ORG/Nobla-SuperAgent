import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/automation/models/workflow_models.dart';
import 'package:nobla_agent/features/automation/widgets/workflow_dag_view.dart';
import 'package:nobla_agent/features/automation/widgets/nl_source_chip.dart';
import 'package:nobla_agent/features/automation/widgets/step_node_widget.dart';

/// Full-screen NL workflow creator with preview.
///
/// Flow: text input -> submit -> loading -> preview DAG with NL source chips
/// -> user reviews & confirms -> save.
class WorkflowCreatorScreen extends ConsumerStatefulWidget {
  final WorkflowDefinition? existingWorkflow;

  const WorkflowCreatorScreen({super.key, this.existingWorkflow});

  @override
  ConsumerState<WorkflowCreatorScreen> createState() =>
      _WorkflowCreatorScreenState();
}

class _WorkflowCreatorScreenState
    extends ConsumerState<WorkflowCreatorScreen> {
  final _controller = TextEditingController();
  WorkflowDefinition? _preview;
  bool _isLoading = false;
  _CreatorPhase _phase = _CreatorPhase.input;

  @override
  void initState() {
    super.initState();
    if (widget.existingWorkflow != null) {
      _controller.text = widget.existingWorkflow!.description;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_phase == _CreatorPhase.input
            ? 'Create Workflow'
            : 'Preview Workflow'),
        actions: [
          if (_phase == _CreatorPhase.preview)
            TextButton(
              key: const ValueKey('edit_btn'),
              onPressed: () => setState(() => _phase = _CreatorPhase.input),
              child: const Text('Edit'),
            ),
        ],
      ),
      body: switch (_phase) {
        _CreatorPhase.input => _InputPhase(
            controller: _controller,
            isLoading: _isLoading,
            onSubmit: _onSubmit,
          ),
        _CreatorPhase.preview => _PreviewPhase(
            workflow: _preview!,
            onConfirm: _onConfirm,
          ),
      },
    );
  }

  Future<void> _onSubmit() async {
    if (_controller.text.trim().length < 5) return;
    setState(() => _isLoading = true);

    try {
      // In real usage, this calls the backend API.
      // For now, create a local preview from the description.
      final wf = WorkflowDefinition(
        workflowId: 'preview',
        name: _controller.text.trim().split(' ').take(6).join(' '),
        description: _controller.text.trim(),
      );
      setState(() {
        _preview = wf;
        _phase = _CreatorPhase.preview;
        _isLoading = false;
      });
    } catch (e) {
      setState(() => _isLoading = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to parse: $e')),
        );
      }
    }
  }

  void _onConfirm() {
    Navigator.of(context).pop(_preview);
  }
}

enum _CreatorPhase { input, preview }

/// Text input phase — NL description entry.
class _InputPhase extends StatelessWidget {
  final TextEditingController controller;
  final bool isLoading;
  final VoidCallback onSubmit;

  const _InputPhase({
    required this.controller,
    required this.isLoading,
    required this.onSubmit,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Describe your workflow in plain language',
            style: theme.textTheme.titleMedium,
          ),
          const SizedBox(height: 4),
          Text(
            'Example: "When GitHub pushes to main, run tests, '
            'if they pass deploy to staging, then notify on Slack"',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.outline,
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            key: const ValueKey('creator_input'),
            controller: controller,
            maxLines: 5,
            decoration: const InputDecoration(
              hintText: 'Describe what should happen...',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          FilledButton.icon(
            key: const ValueKey('parse_btn'),
            onPressed: isLoading ? null : onSubmit,
            icon: isLoading
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.auto_awesome),
            label: Text(isLoading ? 'Parsing...' : 'Parse Workflow'),
          ),
        ],
      ),
    );
  }
}

/// Preview phase — shows parsed DAG with NL source chips.
class _PreviewPhase extends StatelessWidget {
  final WorkflowDefinition workflow;
  final VoidCallback onConfirm;

  const _PreviewPhase({
    required this.workflow,
    required this.onConfirm,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final layout = computeDagLayout(workflow.steps);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Workflow name
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: Text(workflow.name, style: theme.textTheme.titleLarge),
        ),

        // Triggers summary
        if (workflow.triggers.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Wrap(
              spacing: 6,
              children: workflow.triggers.map((t) => Chip(
                    key: ValueKey('trigger_${t.triggerId}'),
                    avatar: const Icon(Icons.bolt, size: 14),
                    label: Text(t.eventPattern, style: const TextStyle(fontSize: 12)),
                  )).toList(),
            ),
          ),

        const SizedBox(height: 8),

        // NL source chips for each step
        if (workflow.steps.any((s) => s.nlSource != null))
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Wrap(
              spacing: 6,
              runSpacing: 4,
              children: workflow.steps
                  .where((s) => s.nlSource != null)
                  .map((s) => NlSourceChip(
                        key: ValueKey('chip_${s.stepId}'),
                        source: s.nlSource!,
                      ))
                  .toList(),
            ),
          ),

        const SizedBox(height: 12),
        const Divider(height: 1),

        // DAG visualization
        Expanded(
          child: workflow.steps.isEmpty
              ? Center(
                  key: const ValueKey('no_steps'),
                  child: Text(
                    'No steps parsed — try a more detailed description',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.outline,
                    ),
                  ),
                )
              : Padding(
                  padding: const EdgeInsets.all(12),
                  child: WorkflowDagView(
                    key: const ValueKey('preview_dag'),
                    steps: workflow.steps,
                    layout: layout,
                  ),
                ),
        ),

        // Confirm button
        Padding(
          padding: const EdgeInsets.all(16),
          child: FilledButton.icon(
            key: const ValueKey('confirm_btn'),
            onPressed: onConfirm,
            icon: const Icon(Icons.check),
            label: const Text('Save Workflow'),
          ),
        ),
      ],
    );
  }
}

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/automation/models/workflow_models.dart';
import 'package:nobla_agent/main.dart' show jsonRpcProvider;

/// Fetches the workflow list for the current user.
///
/// Refresh with `ref.invalidate(workflowListProvider)`.
final workflowListProvider =
    FutureProvider<List<WorkflowDefinition>>((ref) async {
  final rpc = ref.watch(jsonRpcProvider);
  final result = await rpc.call('workflow.list', {});
  final items = result['workflows'] as List<dynamic>? ?? [];
  return items
      .map((w) => WorkflowDefinition.fromJson(w as Map<String, dynamic>))
      .toList();
});

/// Fetches full workflow detail including steps, triggers, and versions.
final workflowDetailProvider =
    FutureProvider.family<WorkflowDefinition, String>((ref, workflowId) async {
  final rpc = ref.watch(jsonRpcProvider);
  final result = await rpc.call('workflow.get', {'workflow_id': workflowId});
  return WorkflowDefinition.fromJson(result as Map<String, dynamic>);
});

/// Live execution state for a workflow — updated via WebSocket events.
final workflowExecutionProvider =
    StateNotifierProvider.family<WorkflowExecutionNotifier, WorkflowExecution?,
        String>(
  (ref, workflowId) => WorkflowExecutionNotifier(ref, workflowId),
);

/// Notifier that tracks a workflow's active execution.
class WorkflowExecutionNotifier extends StateNotifier<WorkflowExecution?> {
  final Ref _ref;
  final String workflowId;

  WorkflowExecutionNotifier(this._ref, this.workflowId) : super(null);

  /// Start a manual execution and track it.
  Future<void> triggerManually() async {
    final rpc = _ref.read(jsonRpcProvider);
    final result =
        await rpc.call('workflow.trigger', {'workflow_id': workflowId});
    state = WorkflowExecution.fromJson(result as Map<String, dynamic>);
  }

  /// Update from a WebSocket event payload.
  void updateFromEvent(Map<String, dynamic> data) {
    if (state == null) return;
    if (data['execution_id'] != state!.executionId) return;

    final status = ExecutionStatus.fromString(
        data['status'] as String? ?? state!.status.name);

    // Rebuild step executions if provided
    var stepExecs = state!.stepExecutions;
    if (data.containsKey('step_id')) {
      final stepId = data['step_id'] as String;
      final stepStatus = ExecutionStatus.fromString(
          data['step_status'] as String? ?? 'pending');
      stepExecs = Map.of(stepExecs);
      stepExecs[stepId] = StepExecutionResult(
        stepId: stepId,
        status: stepStatus,
        error: data['error'] as String?,
        branchTaken: data['branch_taken'] as String?,
      );
    }

    state = WorkflowExecution(
      executionId: state!.executionId,
      workflowId: state!.workflowId,
      workflowVersion: state!.workflowVersion,
      userId: state!.userId,
      status: status,
      startedAt: state!.startedAt,
      completedAt: data['completed_at'] as String? ?? state!.completedAt,
      stepCount: state!.stepCount,
      stepsCompleted: stepExecs.values
          .where((s) => s.status == ExecutionStatus.completed)
          .length,
      stepsFailed: stepExecs.values
          .where((s) => s.status == ExecutionStatus.failed)
          .length,
      stepExecutions: stepExecs,
    );
  }

  /// Set execution directly (e.g. from fetched history).
  void setExecution(WorkflowExecution ex) {
    state = ex;
  }

  void clear() {
    state = null;
  }
}

/// Computes the DAG layout for a workflow's steps.
final dagLayoutProvider =
    Provider.family<DagLayout, List<WorkflowStep>>((ref, steps) {
  return computeDagLayout(steps);
});

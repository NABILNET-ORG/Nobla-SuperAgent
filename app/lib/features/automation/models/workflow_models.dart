import 'package:flutter/foundation.dart';

/// Workflow lifecycle status.
enum WorkflowStatus {
  active,
  paused,
  archived;

  static WorkflowStatus fromString(String s) => switch (s) {
        'active' => WorkflowStatus.active,
        'paused' => WorkflowStatus.paused,
        'archived' => WorkflowStatus.archived,
        _ => WorkflowStatus.active,
      };

  String get label => switch (this) {
        WorkflowStatus.active => 'Active',
        WorkflowStatus.paused => 'Paused',
        WorkflowStatus.archived => 'Archived',
      };
}

/// Step type in a workflow DAG.
enum StepType {
  tool,
  agent,
  condition,
  webhook,
  delay,
  approval;

  static StepType fromString(String s) => switch (s) {
        'tool' => StepType.tool,
        'agent' => StepType.agent,
        'condition' => StepType.condition,
        'webhook' => StepType.webhook,
        'delay' => StepType.delay,
        'approval' => StepType.approval,
        _ => StepType.tool,
      };

  String get label => name[0].toUpperCase() + name.substring(1);
}

/// Error handling strategy per step.
enum ErrorHandling {
  fail,
  retry,
  continueOnError,
  skip;

  static ErrorHandling fromString(String s) => switch (s) {
        'fail' => ErrorHandling.fail,
        'retry' => ErrorHandling.retry,
        'continue' => ErrorHandling.continueOnError,
        'skip' => ErrorHandling.skip,
        _ => ErrorHandling.fail,
      };
}

/// Execution status for workflows and steps.
enum ExecutionStatus {
  pending,
  running,
  paused,
  completed,
  failed,
  skipped;

  static ExecutionStatus fromString(String s) => switch (s) {
        'pending' => ExecutionStatus.pending,
        'running' => ExecutionStatus.running,
        'paused' => ExecutionStatus.paused,
        'completed' => ExecutionStatus.completed,
        'failed' => ExecutionStatus.failed,
        'skipped' => ExecutionStatus.skipped,
        _ => ExecutionStatus.pending,
      };

  String get label => name[0].toUpperCase() + name.substring(1);
}

/// Condition operator for trigger payload matching.
enum ConditionOperator {
  eq,
  neq,
  gt,
  lt,
  gte,
  lte,
  contains,
  exists;

  static ConditionOperator fromString(String s) => switch (s) {
        'eq' => ConditionOperator.eq,
        'neq' => ConditionOperator.neq,
        'gt' => ConditionOperator.gt,
        'lt' => ConditionOperator.lt,
        'gte' => ConditionOperator.gte,
        'lte' => ConditionOperator.lte,
        'contains' => ConditionOperator.contains,
        'exists' => ConditionOperator.exists,
        _ => ConditionOperator.eq,
      };
}

/// A single trigger condition (payload filter).
@immutable
class TriggerCondition {
  final String fieldPath;
  final ConditionOperator operator;
  final dynamic value;

  const TriggerCondition({
    required this.fieldPath,
    required this.operator,
    this.value,
  });

  factory TriggerCondition.fromJson(Map<String, dynamic> json) {
    return TriggerCondition(
      fieldPath: json['field_path'] as String? ?? '',
      operator: ConditionOperator.fromString(json['operator'] as String? ?? 'eq'),
      value: json['value'],
    );
  }

  Map<String, dynamic> toJson() => {
        'field_path': fieldPath,
        'operator': operator.name,
        'value': value,
      };
}

/// Activation rule for a workflow.
@immutable
class WorkflowTrigger {
  final String triggerId;
  final String eventPattern;
  final List<TriggerCondition> conditions;
  final bool active;

  const WorkflowTrigger({
    required this.triggerId,
    required this.eventPattern,
    this.conditions = const [],
    this.active = true,
  });

  factory WorkflowTrigger.fromJson(Map<String, dynamic> json) {
    final condList = json['conditions'] as List<dynamic>? ?? [];
    return WorkflowTrigger(
      triggerId: json['trigger_id'] as String? ?? '',
      eventPattern: json['event_pattern'] as String? ?? '*',
      conditions: condList
          .map((c) => TriggerCondition.fromJson(c as Map<String, dynamic>))
          .toList(),
      active: json['active'] as bool? ?? true,
    );
  }
}

/// Single step in the workflow DAG.
@immutable
class WorkflowStep {
  final String stepId;
  final String name;
  final StepType type;
  final Map<String, dynamic> config;
  final List<String> dependsOn;
  final ErrorHandling errorHandling;
  final String? nlSource;

  const WorkflowStep({
    required this.stepId,
    required this.name,
    required this.type,
    this.config = const {},
    this.dependsOn = const [],
    this.errorHandling = ErrorHandling.fail,
    this.nlSource,
  });

  factory WorkflowStep.fromJson(Map<String, dynamic> json) {
    return WorkflowStep(
      stepId: json['step_id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      type: StepType.fromString(json['type'] as String? ?? 'tool'),
      config: json['config'] as Map<String, dynamic>? ?? {},
      dependsOn: (json['depends_on'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      errorHandling:
          ErrorHandling.fromString(json['error_handling'] as String? ?? 'fail'),
      nlSource: json['nl_source'] as String?,
    );
  }
}

/// Versioned workflow definition.
@immutable
class WorkflowDefinition {
  final String workflowId;
  final String name;
  final String description;
  final int version;
  final WorkflowStatus status;
  final int triggerCount;
  final int stepCount;
  final String createdAt;
  final String updatedAt;
  final List<WorkflowStep> steps;
  final List<WorkflowTrigger> triggers;
  final List<int> versions;

  const WorkflowDefinition({
    required this.workflowId,
    required this.name,
    this.description = '',
    this.version = 1,
    this.status = WorkflowStatus.active,
    this.triggerCount = 0,
    this.stepCount = 0,
    this.createdAt = '',
    this.updatedAt = '',
    this.steps = const [],
    this.triggers = const [],
    this.versions = const [],
  });

  factory WorkflowDefinition.fromJson(Map<String, dynamic> json) {
    return WorkflowDefinition(
      workflowId: json['workflow_id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      description: json['description'] as String? ?? '',
      version: json['version'] as int? ?? 1,
      status: WorkflowStatus.fromString(json['status'] as String? ?? 'active'),
      triggerCount: json['trigger_count'] as int? ?? 0,
      stepCount: json['step_count'] as int? ?? 0,
      createdAt: json['created_at'] as String? ?? '',
      updatedAt: json['updated_at'] as String? ?? '',
      steps: (json['steps'] as List<dynamic>?)
              ?.map((s) => WorkflowStep.fromJson(s as Map<String, dynamic>))
              .toList() ??
          [],
      triggers: (json['triggers'] as List<dynamic>?)
              ?.map((t) => WorkflowTrigger.fromJson(t as Map<String, dynamic>))
              .toList() ??
          [],
      versions: (json['versions'] as List<dynamic>?)
              ?.map((v) => v as int)
              .toList() ??
          [],
    );
  }
}

/// Per-step execution result.
@immutable
class StepExecutionResult {
  final String stepId;
  final ExecutionStatus status;
  final Map<String, dynamic> result;
  final String? error;
  final String? branchTaken;
  final String? startedAt;
  final String? completedAt;

  const StepExecutionResult({
    required this.stepId,
    required this.status,
    this.result = const {},
    this.error,
    this.branchTaken,
    this.startedAt,
    this.completedAt,
  });

  factory StepExecutionResult.fromJson(String stepId, Map<String, dynamic> json) {
    return StepExecutionResult(
      stepId: stepId,
      status: ExecutionStatus.fromString(json['status'] as String? ?? 'pending'),
      result: (json['result'] as Map?)?.cast<String, dynamic>() ?? {},
      error: json['error'] as String?,
      branchTaken: json['branch_taken'] as String?,
      startedAt: json['started_at'] as String?,
      completedAt: json['completed_at'] as String?,
    );
  }
}

/// Runtime instance of a workflow execution.
@immutable
class WorkflowExecution {
  final String executionId;
  final String workflowId;
  final int workflowVersion;
  final String userId;
  final ExecutionStatus status;
  final String? startedAt;
  final String? completedAt;
  final int stepCount;
  final int stepsCompleted;
  final int stepsFailed;
  final Map<String, StepExecutionResult> stepExecutions;

  const WorkflowExecution({
    required this.executionId,
    required this.workflowId,
    this.workflowVersion = 1,
    this.userId = '',
    this.status = ExecutionStatus.pending,
    this.startedAt,
    this.completedAt,
    this.stepCount = 0,
    this.stepsCompleted = 0,
    this.stepsFailed = 0,
    this.stepExecutions = const {},
  });

  factory WorkflowExecution.fromJson(Map<String, dynamic> json) {
    final stepsMap = json['step_executions'] as Map<String, dynamic>? ?? {};
    final parsed = stepsMap.map((k, v) =>
        MapEntry(k, StepExecutionResult.fromJson(k, v as Map<String, dynamic>)));
    return WorkflowExecution(
      executionId: json['execution_id'] as String? ?? '',
      workflowId: json['workflow_id'] as String? ?? '',
      workflowVersion: json['workflow_version'] as int? ?? 1,
      userId: json['user_id'] as String? ?? '',
      status: ExecutionStatus.fromString(json['status'] as String? ?? 'pending'),
      startedAt: json['started_at'] as String?,
      completedAt: json['completed_at'] as String?,
      stepCount: json['step_count'] as int? ?? 0,
      stepsCompleted: json['steps_completed'] as int? ?? 0,
      stepsFailed: json['steps_failed'] as int? ?? 0,
      stepExecutions: parsed,
    );
  }

  double get progressPercent {
    if (stepCount == 0) return 0;
    return (stepsCompleted + stepsFailed) / stepCount;
  }
}

/// Node position for DAG layout.
@immutable
class DagNode {
  final String stepId;
  final int tier;
  final int indexInTier;
  final double x;
  final double y;

  const DagNode({
    required this.stepId,
    required this.tier,
    required this.indexInTier,
    required this.x,
    required this.y,
  });
}

/// Computed DAG layout for a workflow.
@immutable
class DagLayout {
  final List<DagNode> nodes;
  final List<(String, String)> edges;
  final double width;
  final double height;

  const DagLayout({
    this.nodes = const [],
    this.edges = const [],
    this.width = 0,
    this.height = 0,
  });
}

/// Computes a simple left-to-right DAG layout from workflow steps.
DagLayout computeDagLayout(List<WorkflowStep> steps,
    {double nodeWidth = 140, double nodeHeight = 60, double hGap = 40, double vGap = 30}) {
  if (steps.isEmpty) return const DagLayout();

  final byId = {for (final s in steps) s.stepId: s};
  final inDegree = {for (final s in steps) s.stepId: 0};
  final dependents = {for (final s in steps) s.stepId: <String>[]};

  for (final s in steps) {
    for (final dep in s.dependsOn) {
      if (inDegree.containsKey(dep)) {
        inDegree[s.stepId] = (inDegree[s.stepId] ?? 0) + 1;
        dependents[dep]!.add(s.stepId);
      }
    }
  }

  // Kahn's algorithm for tiers
  final tiers = <List<String>>[];
  var ready = [for (final e in inDegree.entries) if (e.value == 0) e.key];
  while (ready.isNotEmpty) {
    tiers.add(List.of(ready));
    final nextReady = <String>[];
    for (final sid in ready) {
      for (final child in dependents[sid]!) {
        inDegree[child] = (inDegree[child] ?? 1) - 1;
        if (inDegree[child] == 0) nextReady.add(child);
      }
    }
    ready = nextReady;
  }

  // Position nodes
  final nodes = <DagNode>[];
  for (int t = 0; t < tiers.length; t++) {
    for (int i = 0; i < tiers[t].length; i++) {
      nodes.add(DagNode(
        stepId: tiers[t][i],
        tier: t,
        indexInTier: i,
        x: t * (nodeWidth + hGap),
        y: i * (nodeHeight + vGap),
      ));
    }
  }

  // Collect edges
  final edges = <(String, String)>[];
  for (final s in steps) {
    for (final dep in s.dependsOn) {
      edges.add((dep, s.stepId));
    }
  }

  final maxTier = tiers.length;
  final maxPerTier = tiers.fold(0, (m, t) => t.length > m ? t.length : m);

  return DagLayout(
    nodes: nodes,
    edges: edges,
    width: maxTier * (nodeWidth + hGap),
    height: maxPerTier * (nodeHeight + vGap),
  );
}

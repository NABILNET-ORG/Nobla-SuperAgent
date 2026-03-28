import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/automation/models/workflow_models.dart';

void main() {
  group('WorkflowStatus', () {
    test('fromString parses valid values', () {
      expect(WorkflowStatus.fromString('active'), WorkflowStatus.active);
      expect(WorkflowStatus.fromString('paused'), WorkflowStatus.paused);
      expect(WorkflowStatus.fromString('archived'), WorkflowStatus.archived);
    });

    test('fromString defaults to active', () {
      expect(WorkflowStatus.fromString('unknown'), WorkflowStatus.active);
    });

    test('label returns capitalized name', () {
      expect(WorkflowStatus.active.label, 'Active');
      expect(WorkflowStatus.paused.label, 'Paused');
    });
  });

  group('StepType', () {
    test('fromString parses all types', () {
      expect(StepType.fromString('tool'), StepType.tool);
      expect(StepType.fromString('agent'), StepType.agent);
      expect(StepType.fromString('condition'), StepType.condition);
      expect(StepType.fromString('webhook'), StepType.webhook);
      expect(StepType.fromString('delay'), StepType.delay);
      expect(StepType.fromString('approval'), StepType.approval);
    });

    test('fromString defaults to tool', () {
      expect(StepType.fromString('bogus'), StepType.tool);
    });
  });

  group('ExecutionStatus', () {
    test('fromString parses all values', () {
      expect(ExecutionStatus.fromString('pending'), ExecutionStatus.pending);
      expect(ExecutionStatus.fromString('running'), ExecutionStatus.running);
      expect(ExecutionStatus.fromString('completed'), ExecutionStatus.completed);
      expect(ExecutionStatus.fromString('failed'), ExecutionStatus.failed);
      expect(ExecutionStatus.fromString('skipped'), ExecutionStatus.skipped);
    });
  });

  group('ConditionOperator', () {
    test('fromString parses all operators', () {
      expect(ConditionOperator.fromString('eq'), ConditionOperator.eq);
      expect(ConditionOperator.fromString('neq'), ConditionOperator.neq);
      expect(ConditionOperator.fromString('gt'), ConditionOperator.gt);
      expect(ConditionOperator.fromString('contains'), ConditionOperator.contains);
      expect(ConditionOperator.fromString('exists'), ConditionOperator.exists);
    });
  });

  group('TriggerCondition', () {
    test('fromJson parses correctly', () {
      final c = TriggerCondition.fromJson({
        'field_path': 'payload.branch',
        'operator': 'eq',
        'value': 'main',
      });
      expect(c.fieldPath, 'payload.branch');
      expect(c.operator, ConditionOperator.eq);
      expect(c.value, 'main');
    });

    test('toJson roundtrip', () {
      final c = TriggerCondition(
        fieldPath: 'a.b',
        operator: ConditionOperator.gt,
        value: 10,
      );
      final json = c.toJson();
      expect(json['field_path'], 'a.b');
      expect(json['operator'], 'gt');
      expect(json['value'], 10);
    });
  });

  group('WorkflowTrigger', () {
    test('fromJson parses with conditions', () {
      final t = WorkflowTrigger.fromJson({
        'trigger_id': 't1',
        'event_pattern': 'webhook.github.*',
        'conditions': [
          {'field_path': 'payload.branch', 'operator': 'eq', 'value': 'main'},
        ],
        'active': true,
      });
      expect(t.triggerId, 't1');
      expect(t.eventPattern, 'webhook.github.*');
      expect(t.conditions.length, 1);
      expect(t.active, true);
    });

    test('fromJson handles missing conditions', () {
      final t = WorkflowTrigger.fromJson({'trigger_id': 't2'});
      expect(t.conditions, isEmpty);
    });
  });

  group('WorkflowStep', () {
    test('fromJson parses all fields', () {
      final s = WorkflowStep.fromJson({
        'step_id': 's1',
        'name': 'Run tests',
        'type': 'tool',
        'config': {'tool': 'code.run'},
        'depends_on': ['s0'],
        'error_handling': 'retry',
        'nl_source': 'run tests',
      });
      expect(s.stepId, 's1');
      expect(s.name, 'Run tests');
      expect(s.type, StepType.tool);
      expect(s.dependsOn, ['s0']);
      expect(s.errorHandling, ErrorHandling.retry);
      expect(s.nlSource, 'run tests');
    });

    test('fromJson handles defaults', () {
      final s = WorkflowStep.fromJson({});
      expect(s.type, StepType.tool);
      expect(s.dependsOn, isEmpty);
      expect(s.errorHandling, ErrorHandling.fail);
    });
  });

  group('WorkflowDefinition', () {
    test('fromJson parses list response', () {
      final wf = WorkflowDefinition.fromJson({
        'workflow_id': 'wf1',
        'name': 'CI Pipeline',
        'description': 'Run CI on push',
        'version': 3,
        'status': 'active',
        'trigger_count': 2,
        'step_count': 5,
        'created_at': '2026-03-28T10:00:00',
        'updated_at': '2026-03-28T11:00:00',
      });
      expect(wf.workflowId, 'wf1');
      expect(wf.name, 'CI Pipeline');
      expect(wf.version, 3);
      expect(wf.status, WorkflowStatus.active);
      expect(wf.triggerCount, 2);
      expect(wf.stepCount, 5);
    });

    test('fromJson parses detail with steps and triggers', () {
      final wf = WorkflowDefinition.fromJson({
        'workflow_id': 'wf1',
        'name': 'Test',
        'steps': [
          {'step_id': 's1', 'name': 'A', 'type': 'tool'},
          {'step_id': 's2', 'name': 'B', 'type': 'webhook', 'depends_on': ['s1']},
        ],
        'triggers': [
          {'trigger_id': 't1', 'event_pattern': 'manual.*'},
        ],
        'versions': [1, 2, 3],
      });
      expect(wf.steps.length, 2);
      expect(wf.triggers.length, 1);
      expect(wf.versions, [1, 2, 3]);
      expect(wf.steps[1].dependsOn, ['s1']);
    });
  });

  group('StepExecutionResult', () {
    test('fromJson parses all fields', () {
      final se = StepExecutionResult.fromJson('s1', {
        'status': 'completed',
        'result': {'exit_code': 0},
        'error': null,
        'branch_taken': 'pass',
        'started_at': '2026-03-28T10:00:00',
        'completed_at': '2026-03-28T10:00:05',
      });
      expect(se.stepId, 's1');
      expect(se.status, ExecutionStatus.completed);
      expect(se.result['exit_code'], 0);
      expect(se.branchTaken, 'pass');
    });
  });

  group('WorkflowExecution', () {
    test('fromJson parses basic fields', () {
      final ex = WorkflowExecution.fromJson({
        'execution_id': 'ex1',
        'workflow_id': 'wf1',
        'workflow_version': 2,
        'user_id': 'u1',
        'status': 'completed',
        'step_count': 3,
        'steps_completed': 2,
        'steps_failed': 1,
      });
      expect(ex.executionId, 'ex1');
      expect(ex.workflowVersion, 2);
      expect(ex.status, ExecutionStatus.completed);
      expect(ex.stepCount, 3);
    });

    test('fromJson parses step_executions map', () {
      final ex = WorkflowExecution.fromJson({
        'execution_id': 'ex1',
        'workflow_id': 'wf1',
        'status': 'completed',
        'step_executions': {
          's1': {'status': 'completed', 'result': {}},
          's2': {'status': 'failed', 'error': 'timeout'},
        },
      });
      expect(ex.stepExecutions.length, 2);
      expect(ex.stepExecutions['s2']!.error, 'timeout');
    });

    test('progressPercent computes correctly', () {
      final ex = WorkflowExecution(
        executionId: 'ex1',
        workflowId: 'wf1',
        stepCount: 4,
        stepsCompleted: 2,
        stepsFailed: 1,
      );
      expect(ex.progressPercent, 0.75);
    });

    test('progressPercent handles zero steps', () {
      const ex = WorkflowExecution(
        executionId: 'ex1',
        workflowId: 'wf1',
        stepCount: 0,
      );
      expect(ex.progressPercent, 0);
    });
  });

  group('computeDagLayout', () {
    test('empty steps returns empty layout', () {
      final layout = computeDagLayout([]);
      expect(layout.nodes, isEmpty);
      expect(layout.edges, isEmpty);
    });

    test('single step produces one node', () {
      final layout = computeDagLayout([
        const WorkflowStep(stepId: 's1', name: 'A', type: StepType.tool),
      ]);
      expect(layout.nodes.length, 1);
      expect(layout.nodes[0].tier, 0);
    });

    test('linear chain produces tiers', () {
      final layout = computeDagLayout([
        const WorkflowStep(stepId: 's1', name: 'A', type: StepType.tool),
        const WorkflowStep(
            stepId: 's2', name: 'B', type: StepType.tool, dependsOn: ['s1']),
        const WorkflowStep(
            stepId: 's3', name: 'C', type: StepType.tool, dependsOn: ['s2']),
      ]);
      expect(layout.nodes.length, 3);
      final tiers = layout.nodes.map((n) => n.tier).toList();
      expect(tiers, [0, 1, 2]);
    });

    test('parallel steps share tier', () {
      final layout = computeDagLayout([
        const WorkflowStep(stepId: 's1', name: 'A', type: StepType.tool),
        const WorkflowStep(stepId: 's2', name: 'B', type: StepType.tool),
      ]);
      expect(layout.nodes.length, 2);
      expect(layout.nodes[0].tier, 0);
      expect(layout.nodes[1].tier, 0);
    });

    test('diamond produces correct edges', () {
      final layout = computeDagLayout([
        const WorkflowStep(stepId: 's1', name: 'A', type: StepType.tool),
        const WorkflowStep(
            stepId: 's2', name: 'B', type: StepType.tool, dependsOn: ['s1']),
        const WorkflowStep(
            stepId: 's3', name: 'C', type: StepType.tool, dependsOn: ['s1']),
        const WorkflowStep(
            stepId: 's4',
            name: 'D',
            type: StepType.tool,
            dependsOn: ['s2', 's3']),
      ]);
      expect(layout.edges.length, 4);
      expect(layout.nodes.length, 4);
    });

    test('layout dimensions are positive', () {
      final layout = computeDagLayout([
        const WorkflowStep(stepId: 's1', name: 'A', type: StepType.tool),
        const WorkflowStep(
            stepId: 's2', name: 'B', type: StepType.tool, dependsOn: ['s1']),
      ]);
      expect(layout.width, greaterThan(0));
      expect(layout.height, greaterThan(0));
    });
  });
}

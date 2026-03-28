import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/automation/models/workflow_models.dart';
import 'package:nobla_agent/features/automation/providers/workflow_providers.dart';
import 'package:nobla_agent/features/automation/screens/workflow_creator_screen.dart';
import 'package:nobla_agent/features/automation/screens/workflow_detail_screen.dart';

Widget _wrap(Widget child, {List<Override> overrides = const []}) {
  return ProviderScope(
    overrides: overrides,
    child: MaterialApp(home: child),
  );
}

const _sampleWorkflow = WorkflowDefinition(
  workflowId: 'wf1',
  name: 'CI Pipeline',
  description: 'Run tests then deploy to staging',
  version: 3,
  status: WorkflowStatus.active,
  triggerCount: 1,
  stepCount: 2,
  steps: [
    WorkflowStep(
      stepId: 's1',
      name: 'Run tests',
      type: StepType.tool,
      nlSource: 'run tests',
    ),
    WorkflowStep(
      stepId: 's2',
      name: 'Deploy',
      type: StepType.webhook,
      dependsOn: ['s1'],
      nlSource: 'deploy to staging',
    ),
  ],
  triggers: [
    WorkflowTrigger(
      triggerId: 't1',
      eventPattern: 'webhook.github.*',
    ),
  ],
  versions: [1, 2, 3],
);

void main() {
  group('WorkflowCreatorScreen', () {
    testWidgets('shows input phase by default', (tester) async {
      await tester.pumpWidget(_wrap(
        const WorkflowCreatorScreen(),
      ));

      expect(find.text('Create Workflow'), findsOneWidget);
      expect(find.byKey(const ValueKey('creator_input')), findsOneWidget);
      expect(find.byKey(const ValueKey('parse_btn')), findsOneWidget);
    });

    testWidgets('shows example hint text', (tester) async {
      await tester.pumpWidget(_wrap(
        const WorkflowCreatorScreen(),
      ));

      expect(find.textContaining('Describe your workflow'), findsOneWidget);
      expect(find.textContaining('Example'), findsOneWidget);
    });

    testWidgets('pre-populates with existing workflow description',
        (tester) async {
      await tester.pumpWidget(_wrap(
        const WorkflowCreatorScreen(existingWorkflow: _sampleWorkflow),
      ));

      final textField = tester.widget<TextField>(
          find.byKey(const ValueKey('creator_input')));
      expect(textField.controller?.text, 'Run tests then deploy to staging');
    });

    testWidgets('parse button triggers submit', (tester) async {
      await tester.pumpWidget(_wrap(
        const WorkflowCreatorScreen(),
      ));

      await tester.enterText(
        find.byKey(const ValueKey('creator_input')),
        'run tests then deploy',
      );
      await tester.pump();

      await tester.tap(find.byKey(const ValueKey('parse_btn')));
      await tester.pumpAndSettle();

      // Should transition to preview phase
      expect(find.text('Preview Workflow'), findsOneWidget);
      expect(find.byKey(const ValueKey('confirm_btn')), findsOneWidget);
    });

    testWidgets('preview shows confirm button', (tester) async {
      await tester.pumpWidget(_wrap(
        const WorkflowCreatorScreen(),
      ));

      await tester.enterText(
        find.byKey(const ValueKey('creator_input')),
        'run tests then deploy',
      );
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('parse_btn')));
      await tester.pumpAndSettle();

      expect(find.text('Save Workflow'), findsOneWidget);
    });

    testWidgets('edit button returns to input phase', (tester) async {
      await tester.pumpWidget(_wrap(
        const WorkflowCreatorScreen(),
      ));

      await tester.enterText(
        find.byKey(const ValueKey('creator_input')),
        'run tests then deploy',
      );
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('parse_btn')));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const ValueKey('edit_btn')));
      await tester.pumpAndSettle();

      expect(find.text('Create Workflow'), findsOneWidget);
      expect(find.byKey(const ValueKey('creator_input')), findsOneWidget);
    });
  });

  group('WorkflowDetailScreen', () {
    testWidgets('shows workflow name and version', (tester) async {
      await tester.pumpWidget(_wrap(
        const WorkflowDetailScreen(workflowId: 'wf1'),
        overrides: [
          workflowDetailProvider('wf1')
              .overrideWith((_) async => _sampleWorkflow),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('wf_name')), findsOneWidget);
      expect(find.text('CI Pipeline'), findsOneWidget);
      expect(find.byKey(const ValueKey('version_badge')), findsOneWidget);
    });

    testWidgets('shows triggers section', (tester) async {
      await tester.pumpWidget(_wrap(
        const WorkflowDetailScreen(workflowId: 'wf1'),
        overrides: [
          workflowDetailProvider('wf1')
              .overrideWith((_) async => _sampleWorkflow),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('triggers_header')), findsOneWidget);
      expect(find.text('webhook.github.*'), findsOneWidget);
    });

    testWidgets('shows DAG visualization', (tester) async {
      await tester.pumpWidget(_wrap(
        const WorkflowDetailScreen(workflowId: 'wf1'),
        overrides: [
          workflowDetailProvider('wf1')
              .overrideWith((_) async => _sampleWorkflow),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('detail_dag')), findsOneWidget);
      expect(find.byKey(const ValueKey('steps_header')), findsOneWidget);
    });

    testWidgets('shows execution history header', (tester) async {
      await tester.pumpWidget(_wrap(
        const WorkflowDetailScreen(workflowId: 'wf1'),
        overrides: [
          workflowDetailProvider('wf1')
              .overrideWith((_) async => _sampleWorkflow),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('history_header')), findsOneWidget);
    });

    testWidgets('shows status toggle button', (tester) async {
      await tester.pumpWidget(_wrap(
        const WorkflowDetailScreen(workflowId: 'wf1'),
        overrides: [
          workflowDetailProvider('wf1')
              .overrideWith((_) async => _sampleWorkflow),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('status_toggle')), findsOneWidget);
    });

    testWidgets('shows description text', (tester) async {
      await tester.pumpWidget(_wrap(
        const WorkflowDetailScreen(workflowId: 'wf1'),
        overrides: [
          workflowDetailProvider('wf1')
              .overrideWith((_) async => _sampleWorkflow),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('Run tests then deploy to staging'), findsOneWidget);
    });

    testWidgets('shows error on load failure', (tester) async {
      await tester.pumpWidget(_wrap(
        const WorkflowDetailScreen(workflowId: 'wf1'),
        overrides: [
          workflowDetailProvider('wf1')
              .overrideWith((_) async => throw Exception('network')),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('error')), findsOneWidget);
    });
  });
}

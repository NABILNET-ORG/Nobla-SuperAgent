import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/automation/models/workflow_models.dart';
import 'package:nobla_agent/features/automation/widgets/step_node_widget.dart';
import 'package:nobla_agent/features/automation/widgets/step_bottom_sheet.dart';
import 'package:nobla_agent/features/automation/widgets/workflow_dag_view.dart';
import 'package:nobla_agent/features/automation/widgets/nl_source_chip.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  group('StepNodeWidget', () {
    testWidgets('displays step name and type', (tester) async {
      await tester.pumpWidget(_wrap(
        const StepNodeWidget(
          step: WorkflowStep(
            stepId: 's1',
            name: 'Run tests',
            type: StepType.tool,
          ),
        ),
      ));

      expect(find.text('Run tests'), findsOneWidget);
      expect(find.text('Tool'), findsOneWidget);
    });

    testWidgets('shows status dot when execution status provided',
        (tester) async {
      await tester.pumpWidget(_wrap(
        const StepNodeWidget(
          step: WorkflowStep(stepId: 's1', name: 'A', type: StepType.tool),
          executionStatus: ExecutionStatus.completed,
        ),
      ));

      expect(find.text('Done'), findsOneWidget);
    });

    testWidgets('shows failed status', (tester) async {
      await tester.pumpWidget(_wrap(
        const StepNodeWidget(
          step: WorkflowStep(stepId: 's1', name: 'A', type: StepType.tool),
          executionStatus: ExecutionStatus.failed,
        ),
      ));

      expect(find.text('Failed'), findsOneWidget);
    });

    testWidgets('is tappable', (tester) async {
      var tapped = false;
      await tester.pumpWidget(_wrap(
        StepNodeWidget(
          step: const WorkflowStep(
              stepId: 's1', name: 'Tap me', type: StepType.tool),
          onTap: () => tapped = true,
        ),
      ));

      await tester.tap(find.text('Tap me'));
      expect(tapped, isTrue);
    });

    testWidgets('skipped step has reduced opacity', (tester) async {
      await tester.pumpWidget(_wrap(
        const StepNodeWidget(
          step: WorkflowStep(stepId: 's1', name: 'A', type: StepType.tool),
          executionStatus: ExecutionStatus.skipped,
        ),
      ));

      final opacity = tester.widget<Opacity>(find.byType(Opacity));
      expect(opacity.opacity, 0.4);
    });

    testWidgets('running step shows pulsing wrapper', (tester) async {
      await tester.pumpWidget(_wrap(
        const StepNodeWidget(
          step: WorkflowStep(stepId: 's1', name: 'A', type: StepType.tool),
          executionStatus: ExecutionStatus.running,
        ),
      ));
      await tester.pump();

      expect(find.text('Running'), findsOneWidget);
    });

    testWidgets('each step type has a distinct icon', (tester) async {
      for (final type in StepType.values) {
        await tester.pumpWidget(_wrap(
          StepNodeWidget(
            step: WorkflowStep(stepId: 's', name: 'X', type: type),
          ),
        ));
        expect(find.byIcon(stepTypeIcon(type)), findsOneWidget);
      }
    });
  });

  group('stepTypeColor', () {
    test('returns distinct colors for each type', () {
      final colors = StepType.values.map(stepTypeColor).toSet();
      expect(colors.length, StepType.values.length);
    });
  });

  group('StepBottomSheet', () {
    testWidgets('shows step name and type', (tester) async {
      await tester.pumpWidget(_wrap(
        const StepBottomSheet(
          step: WorkflowStep(
            stepId: 's1',
            name: 'Deploy',
            type: StepType.webhook,
          ),
        ),
      ));

      expect(find.text('Deploy'), findsOneWidget);
      expect(find.text('Webhook'), findsOneWidget);
    });

    testWidgets('shows nl_source when present', (tester) async {
      await tester.pumpWidget(_wrap(
        const StepBottomSheet(
          step: WorkflowStep(
            stepId: 's1',
            name: 'A',
            type: StepType.tool,
            nlSource: 'run the tests',
          ),
        ),
      ));

      expect(find.byKey(const ValueKey('nl_source')), findsOneWidget);
      expect(find.text('run the tests'), findsOneWidget);
    });

    testWidgets('hides nl_source when null', (tester) async {
      await tester.pumpWidget(_wrap(
        const StepBottomSheet(
          step: WorkflowStep(stepId: 's1', name: 'A', type: StepType.tool),
        ),
      ));

      expect(find.byKey(const ValueKey('nl_source')), findsNothing);
    });

    testWidgets('shows quick actions when provided', (tester) async {
      await tester.pumpWidget(_wrap(
        StepBottomSheet(
          step: const WorkflowStep(
              stepId: 's1', name: 'A', type: StepType.tool),
          onRetry: () {},
          onSkip: () {},
        ),
      ));

      expect(find.byKey(const ValueKey('action_retry')), findsOneWidget);
      expect(find.byKey(const ValueKey('action_skip')), findsOneWidget);
    });

    testWidgets('hides quick actions when none provided', (tester) async {
      await tester.pumpWidget(_wrap(
        const StepBottomSheet(
          step: WorkflowStep(stepId: 's1', name: 'A', type: StepType.tool),
        ),
      ));

      expect(find.byKey(const ValueKey('action_retry')), findsNothing);
      expect(find.byKey(const ValueKey('action_skip')), findsNothing);
    });

    testWidgets('shows execution error', (tester) async {
      await tester.pumpWidget(_wrap(
        const StepBottomSheet(
          step: WorkflowStep(stepId: 's1', name: 'A', type: StepType.tool),
          executionResult: StepExecutionResult(
            stepId: 's1',
            status: ExecutionStatus.failed,
            error: 'Connection timeout',
          ),
        ),
      ));

      expect(find.textContaining('Connection timeout'), findsOneWidget);
    });
  });

  group('WorkflowDagView', () {
    testWidgets('shows empty state when no steps', (tester) async {
      await tester.pumpWidget(_wrap(
        const WorkflowDagView(
          steps: [],
          layout: DagLayout(),
        ),
      ));

      expect(find.byKey(const ValueKey('dag_empty')), findsOneWidget);
      expect(find.text('No steps defined'), findsOneWidget);
    });

    testWidgets('renders nodes for steps', (tester) async {
      const steps = [
        WorkflowStep(stepId: 's1', name: 'Step A', type: StepType.tool),
        WorkflowStep(
            stepId: 's2',
            name: 'Step B',
            type: StepType.webhook,
            dependsOn: ['s1']),
      ];
      final layout = computeDagLayout(steps);

      await tester.pumpWidget(_wrap(
        WorkflowDagView(steps: steps, layout: layout),
      ));

      expect(find.byKey(const ValueKey('node_s1')), findsOneWidget);
      expect(find.byKey(const ValueKey('node_s2')), findsOneWidget);
      expect(find.text('Step A'), findsOneWidget);
      expect(find.text('Step B'), findsOneWidget);
    });

    testWidgets('renders edge painter', (tester) async {
      const steps = [
        WorkflowStep(stepId: 's1', name: 'A', type: StepType.tool),
        WorkflowStep(
            stepId: 's2', name: 'B', type: StepType.tool, dependsOn: ['s1']),
      ];
      final layout = computeDagLayout(steps);

      await tester.pumpWidget(_wrap(
        WorkflowDagView(steps: steps, layout: layout),
      ));

      expect(find.byKey(const ValueKey('dag_edges')), findsOneWidget);
    });

    testWidgets('tapping node opens bottom sheet', (tester) async {
      const steps = [
        WorkflowStep(
          stepId: 's1',
          name: 'Tappable Step',
          type: StepType.tool,
          nlSource: 'run it',
        ),
      ];
      final layout = computeDagLayout(steps);

      await tester.pumpWidget(_wrap(
        WorkflowDagView(steps: steps, layout: layout),
      ));

      await tester.tap(find.text('Tappable Step'));
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('step_sheet')), findsOneWidget);
      expect(find.text('run it'), findsOneWidget);
    });
  });

  group('NlSourceChip', () {
    testWidgets('displays source text', (tester) async {
      await tester.pumpWidget(_wrap(
        const NlSourceChip(source: 'run tests'),
      ));

      expect(find.text('run tests'), findsOneWidget);
      expect(find.byKey(const ValueKey('nl_chip')), findsOneWidget);
    });

    testWidgets('shows quote icon', (tester) async {
      await tester.pumpWidget(_wrap(
        const NlSourceChip(source: 'deploy'),
      ));

      expect(find.byIcon(Icons.format_quote), findsOneWidget);
    });
  });
}

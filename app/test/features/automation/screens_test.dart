import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/automation/models/workflow_models.dart';
import 'package:nobla_agent/features/automation/models/webhook_models.dart';
import 'package:nobla_agent/features/automation/providers/workflow_providers.dart';
import 'package:nobla_agent/features/automation/providers/webhook_providers.dart';
import 'package:nobla_agent/features/automation/screens/automation_screen.dart';
import 'package:nobla_agent/features/automation/screens/workflow_list_screen.dart';
import 'package:nobla_agent/features/automation/screens/webhook_screen.dart';

// Helper to wrap widget with ProviderScope + MaterialApp.
Widget _wrap(Widget child, {List<Override> overrides = const []}) {
  return ProviderScope(
    overrides: overrides,
    child: MaterialApp(home: child),
  );
}

void main() {
  group('AutomationScreen', () {
    testWidgets('shows Workflows and Webhooks tabs', (tester) async {
      await tester.pumpWidget(_wrap(
        const AutomationScreen(),
        overrides: [
          workflowListProvider.overrideWith((_) async => []),
          webhookListProvider.overrideWith((_) async => []),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('Workflows'), findsOneWidget);
      expect(find.text('Webhooks'), findsOneWidget);
      expect(find.text('Automation'), findsOneWidget);
    });

    testWidgets('tabs are tappable', (tester) async {
      await tester.pumpWidget(_wrap(
        const AutomationScreen(),
        overrides: [
          workflowListProvider.overrideWith((_) async => []),
          webhookListProvider.overrideWith((_) async => []),
        ],
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Webhooks'));
      await tester.pumpAndSettle();
      // Should show webhook empty state
      expect(find.text('No webhooks registered'), findsOneWidget);
    });
  });

  group('WorkflowListScreen', () {
    testWidgets('shows empty state when no workflows', (tester) async {
      await tester.pumpWidget(_wrap(
        const Scaffold(body: WorkflowListScreen()),
        overrides: [
          workflowListProvider.overrideWith((_) async => []),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('No workflows yet'), findsOneWidget);
      expect(find.byKey(const ValueKey('create_fab')), findsOneWidget);
    });

    testWidgets('shows loading indicator', (tester) async {
      final completer = Completer<List<WorkflowDefinition>>();
      await tester.pumpWidget(_wrap(
        const Scaffold(body: WorkflowListScreen()),
        overrides: [
          workflowListProvider.overrideWith((_) => completer.future),
        ],
      ));
      await tester.pump();

      expect(find.byType(CircularProgressIndicator), findsOneWidget);

      // Complete to avoid pending timer
      completer.complete([]);
      await tester.pumpAndSettle();
    });

    testWidgets('shows workflow cards', (tester) async {
      await tester.pumpWidget(_wrap(
        const Scaffold(body: WorkflowListScreen()),
        overrides: [
          workflowListProvider.overrideWith((_) async => [
                const WorkflowDefinition(
                  workflowId: 'wf1',
                  name: 'CI Pipeline',
                  version: 2,
                  stepCount: 3,
                  triggerCount: 1,
                ),
                const WorkflowDefinition(
                  workflowId: 'wf2',
                  name: 'Deploy Flow',
                  status: WorkflowStatus.paused,
                ),
              ]),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('CI Pipeline'), findsOneWidget);
      expect(find.text('Deploy Flow'), findsOneWidget);
      // "Active" appears in both filter chip and status badge
      expect(find.byKey(const ValueKey('workflow_wf1')), findsOneWidget);
      expect(find.byKey(const ValueKey('workflow_wf2')), findsOneWidget);
    });

    testWidgets('filter chips are shown', (tester) async {
      await tester.pumpWidget(_wrap(
        const Scaffold(body: WorkflowListScreen()),
        overrides: [
          workflowListProvider.overrideWith((_) async => []),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('filter_all')), findsOneWidget);
      expect(find.byKey(const ValueKey('filter_active')), findsOneWidget);
      expect(find.byKey(const ValueKey('filter_paused')), findsOneWidget);
    });

    testWidgets('filter chips change filter', (tester) async {
      await tester.pumpWidget(_wrap(
        const Scaffold(body: WorkflowListScreen()),
        overrides: [
          workflowListProvider.overrideWith((_) async => [
                const WorkflowDefinition(
                  workflowId: 'wf1',
                  name: 'Active WF',
                  status: WorkflowStatus.active,
                ),
                const WorkflowDefinition(
                  workflowId: 'wf2',
                  name: 'Paused WF',
                  status: WorkflowStatus.paused,
                ),
              ]),
        ],
      ));
      await tester.pumpAndSettle();

      // Both visible initially
      expect(find.text('Active WF'), findsOneWidget);
      expect(find.text('Paused WF'), findsOneWidget);

      // Filter to paused
      await tester.tap(find.byKey(const ValueKey('filter_paused')));
      await tester.pumpAndSettle();
      expect(find.text('Active WF'), findsNothing);
      expect(find.text('Paused WF'), findsOneWidget);
    });

    testWidgets('FAB opens create sheet', (tester) async {
      await tester.pumpWidget(_wrap(
        const Scaffold(body: WorkflowListScreen()),
        overrides: [
          workflowListProvider.overrideWith((_) async => []),
        ],
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const ValueKey('create_fab')));
      await tester.pumpAndSettle();

      expect(find.text('Create Workflow'), findsOneWidget);
      expect(find.byKey(const ValueKey('nl_input')), findsOneWidget);
    });
  });

  group('WorkflowCard', () {
    testWidgets('shows step and trigger counts', (tester) async {
      await tester.pumpWidget(_wrap(
        const Scaffold(
          body: WorkflowCard(
            workflow: WorkflowDefinition(
              workflowId: 'wf1',
              name: 'Test WF',
              stepCount: 5,
              triggerCount: 2,
              version: 3,
            ),
          ),
        ),
      ));

      expect(find.textContaining('5 steps'), findsOneWidget);
      expect(find.textContaining('2 triggers'), findsOneWidget);
      expect(find.textContaining('v3'), findsOneWidget);
    });
  });

  group('WebhookScreen', () {
    testWidgets('shows empty state when no webhooks', (tester) async {
      await tester.pumpWidget(_wrap(
        const Scaffold(body: WebhookScreen()),
        overrides: [
          webhookListProvider.overrideWith((_) async => []),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('No webhooks registered'), findsOneWidget);
      expect(find.byKey(const ValueKey('register_fab')), findsOneWidget);
    });

    testWidgets('shows webhook cards', (tester) async {
      await tester.pumpWidget(_wrap(
        const Scaffold(body: WebhookScreen()),
        overrides: [
          webhookListProvider.overrideWith((_) async => [
                const WebhookEntry(
                  webhookId: 'wh1',
                  name: 'GitHub Push',
                  eventTypePrefix: 'github.push',
                ),
                const WebhookEntry(
                  webhookId: 'wh2',
                  name: 'Slack Notify',
                  direction: WebhookDirection.outbound,
                  eventTypePrefix: 'slack.notify',
                ),
              ]),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('GitHub Push'), findsOneWidget);
      expect(find.text('Slack Notify'), findsOneWidget);
    });

    testWidgets('FAB opens register sheet', (tester) async {
      await tester.pumpWidget(_wrap(
        const Scaffold(body: WebhookScreen()),
        overrides: [
          webhookListProvider.overrideWith((_) async => []),
        ],
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const ValueKey('register_fab')));
      await tester.pumpAndSettle();

      expect(find.text('Register Webhook'), findsOneWidget);
      expect(find.byKey(const ValueKey('name_input')), findsOneWidget);
      expect(find.byKey(const ValueKey('scheme_picker')), findsOneWidget);
    });
  });

  group('WebhookCard', () {
    testWidgets('shows direction icon and prefix', (tester) async {
      await tester.pumpWidget(_wrap(
        const Scaffold(
          body: WebhookCard(
            webhook: WebhookEntry(
              webhookId: 'wh1',
              name: 'GH Hook',
              eventTypePrefix: 'github.push',
              signatureScheme: 'hmac-sha256',
            ),
          ),
        ),
      ));

      expect(find.text('GH Hook'), findsOneWidget);
      expect(find.textContaining('github.push'), findsOneWidget);
      expect(find.textContaining('hmac-sha256'), findsOneWidget);
    });
  });
}

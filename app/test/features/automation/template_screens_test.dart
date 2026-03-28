import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/automation/models/template_models.dart';
import 'package:nobla_agent/features/automation/providers/template_providers.dart';
import 'package:nobla_agent/features/automation/screens/template_gallery_screen.dart';
import 'package:nobla_agent/features/automation/screens/workflow_import_screen.dart';

// Helper to wrap widget with ProviderScope + MaterialApp.
Widget _wrap(Widget child, {List<Override> overrides = const []}) {
  return ProviderScope(
    overrides: overrides,
    child: MaterialApp(home: child),
  );
}

const _sampleTemplates = [
  WorkflowTemplate(
    templateId: 'tmpl-1',
    name: 'GitHub CI Notifier',
    description: 'Notify on CI pass/fail',
    category: TemplateCategory.ciCd,
    tags: ['github', 'ci'],
    author: 'Nobla',
    stepCount: 4,
    triggerCount: 1,
    icon: 'github',
    bundled: true,
  ),
  WorkflowTemplate(
    templateId: 'tmpl-2',
    name: 'Data Pipeline',
    description: 'Fetch, transform, validate, store',
    category: TemplateCategory.dataPipeline,
    tags: ['data', 'pipeline'],
    author: 'Nobla',
    stepCount: 4,
    triggerCount: 1,
    icon: 'pipeline',
    bundled: true,
  ),
  WorkflowTemplate(
    templateId: 'tmpl-3',
    name: 'Webhook Relay',
    description: 'Forward webhooks',
    category: TemplateCategory.integration,
    tags: ['webhook', 'relay'],
    author: 'Nobla',
    stepCount: 3,
    triggerCount: 1,
    icon: 'relay',
    bundled: false,
  ),
];

void main() {
  group('TemplateGalleryScreen', () {
    testWidgets('shows template list', (tester) async {
      await tester.pumpWidget(_wrap(
        const TemplateGalleryScreen(),
        overrides: [
          templateListProvider
              .overrideWith((ref, filter) async => _sampleTemplates),
        ],
      ));
      await tester.pumpAndSettle();

      // First two cards visible, third may be off-screen in ListView
      expect(find.text('GitHub CI Notifier'), findsWidgets);
      expect(find.text('Data Pipeline'), findsWidgets);
      expect(find.byKey(const ValueKey('template_list')), findsOneWidget);
    });

    testWidgets('shows empty state when no templates', (tester) async {
      await tester.pumpWidget(_wrap(
        const TemplateGalleryScreen(),
        overrides: [
          templateListProvider.overrideWith((ref, filter) async => []),
        ],
      ));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('empty_state')), findsOneWidget);
    });

    testWidgets('shows error state with retry', (tester) async {
      await tester.pumpWidget(_wrap(
        const TemplateGalleryScreen(),
        overrides: [
          templateListProvider.overrideWith(
              (ref, filter) async => throw Exception('Network error')),
        ],
      ));
      await tester.pumpAndSettle();
      expect(find.text('Failed to load templates'), findsOneWidget);
      expect(find.byKey(const ValueKey('retry_btn')), findsOneWidget);
    });

    testWidgets('shows search field', (tester) async {
      await tester.pumpWidget(_wrap(
        const TemplateGalleryScreen(),
        overrides: [
          templateListProvider
              .overrideWith((ref, filter) async => _sampleTemplates),
        ],
      ));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('search_field')), findsOneWidget);
    });

    testWidgets('shows category filter chips', (tester) async {
      await tester.pumpWidget(_wrap(
        const TemplateGalleryScreen(),
        overrides: [
          templateListProvider
              .overrideWith((ref, filter) async => _sampleTemplates),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('cat_all')), findsOneWidget);
      expect(find.byKey(const ValueKey('cat_ci_cd')), findsOneWidget);
      expect(find.byKey(const ValueKey('cat_devops')), findsOneWidget);
    });

    testWidgets('tapping category chip updates selection', (tester) async {
      await tester.pumpWidget(_wrap(
        const TemplateGalleryScreen(),
        overrides: [
          templateListProvider
              .overrideWith((ref, filter) async => _sampleTemplates),
        ],
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const ValueKey('cat_ci_cd')));
      await tester.pumpAndSettle();
      // Widget should rebuild — no crash
      expect(find.byKey(const ValueKey('cat_ci_cd')), findsOneWidget);
    });

    testWidgets('shows built-in chip for bundled templates', (tester) async {
      await tester.pumpWidget(_wrap(
        const TemplateGalleryScreen(),
        overrides: [
          templateListProvider
              .overrideWith((ref, filter) async => _sampleTemplates),
        ],
      ));
      await tester.pumpAndSettle();
      expect(find.text('Built-in'), findsNWidgets(2)); // 2 bundled
    });

    testWidgets('shows step and trigger counts', (tester) async {
      await tester.pumpWidget(_wrap(
        const TemplateGalleryScreen(),
        overrides: [
          templateListProvider
              .overrideWith((ref, filter) async => _sampleTemplates),
        ],
      ));
      await tester.pumpAndSettle();
      // Visible cards show counts
      expect(find.text('4 steps'), findsWidgets);
      expect(find.text('1 triggers'), findsWidgets);
    });

    testWidgets('shows Use button for visible templates', (tester) async {
      await tester.pumpWidget(_wrap(
        const TemplateGalleryScreen(),
        overrides: [
          templateListProvider
              .overrideWith((ref, filter) async => _sampleTemplates),
        ],
      ));
      await tester.pumpAndSettle();
      expect(find.text('Use'), findsWidgets);
    });

    testWidgets('Use button opens instantiate dialog', (tester) async {
      await tester.pumpWidget(_wrap(
        const TemplateGalleryScreen(),
        overrides: [
          templateListProvider
              .overrideWith((ref, filter) async => _sampleTemplates),
        ],
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const ValueKey('use_tmpl-1')));
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('instantiate_dialog')), findsOneWidget);
      expect(find.byKey(const ValueKey('name_input')), findsOneWidget);
      expect(find.text('Cancel'), findsOneWidget);
      expect(find.byKey(const ValueKey('confirm_instantiate')), findsOneWidget);
    });

    testWidgets('instantiate dialog cancel closes it', (tester) async {
      await tester.pumpWidget(_wrap(
        const TemplateGalleryScreen(),
        overrides: [
          templateListProvider
              .overrideWith((ref, filter) async => _sampleTemplates),
        ],
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const ValueKey('use_tmpl-1')));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      expect(
          find.byKey(const ValueKey('instantiate_dialog')), findsNothing);
    });

    testWidgets('shows tags on template cards', (tester) async {
      await tester.pumpWidget(_wrap(
        const TemplateGalleryScreen(),
        overrides: [
          templateListProvider
              .overrideWith((ref, filter) async => _sampleTemplates),
        ],
      ));
      await tester.pumpAndSettle();
      expect(find.text('github'), findsOneWidget);
      expect(find.text('ci'), findsOneWidget);
    });

    testWidgets('appbar shows Template Gallery title', (tester) async {
      await tester.pumpWidget(_wrap(
        const TemplateGalleryScreen(),
        overrides: [
          templateListProvider
              .overrideWith((ref, filter) async => _sampleTemplates),
        ],
      ));
      await tester.pumpAndSettle();
      expect(find.text('Template Gallery'), findsOneWidget);
    });
  });

  group('WorkflowImportScreen', () {
    testWidgets('shows initial UI elements', (tester) async {
      await tester.pumpWidget(_wrap(const WorkflowImportScreen()));
      await tester.pumpAndSettle();

      expect(find.text('Import Workflow'), findsOneWidget);
      expect(find.text('Paste workflow JSON'), findsOneWidget);
      expect(find.byKey(const ValueKey('json_input')), findsOneWidget);
      expect(find.byKey(const ValueKey('paste_btn')), findsOneWidget);
    });

    testWidgets('shows parse error for invalid JSON', (tester) async {
      await tester.pumpWidget(_wrap(const WorkflowImportScreen()));
      await tester.pumpAndSettle();

      await tester.enterText(
          find.byKey(const ValueKey('json_input')), 'not json');
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('parse_error')), findsOneWidget);
      expect(find.text('Invalid JSON format'), findsOneWidget);
    });

    testWidgets('shows parse error for missing version', (tester) async {
      await tester.pumpWidget(_wrap(const WorkflowImportScreen()));
      await tester.pumpAndSettle();

      await tester.enterText(
          find.byKey(const ValueKey('json_input')), '{"name": "test"}');
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('parse_error')), findsOneWidget);
    });

    testWidgets('shows preview card for valid JSON', (tester) async {
      await tester.pumpWidget(_wrap(const WorkflowImportScreen()));
      await tester.pumpAndSettle();

      final validJson = jsonEncode({
        r'$nobla_version': '1.0',
        'workflow': {
          'name': 'Test WF',
          'description': 'A test',
          'steps': [
            {'ref_id': 'a', 'name': 'A'}
          ],
          'triggers': [
            {'event_pattern': 'manual.*'}
          ],
        },
      });
      await tester.enterText(
          find.byKey(const ValueKey('json_input')), validJson);
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('preview_card')), findsOneWidget);
      expect(find.text('Test WF'), findsOneWidget);
      expect(find.text('1'), findsWidgets); // step count or trigger count
      expect(find.byKey(const ValueKey('import_btn')), findsOneWidget);
      expect(find.byKey(const ValueKey('name_override')), findsOneWidget);
    });

    testWidgets('no preview or import button for empty input', (tester) async {
      await tester.pumpWidget(_wrap(const WorkflowImportScreen()));
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('preview_card')), findsNothing);
      expect(find.byKey(const ValueKey('import_btn')), findsNothing);
    });

    testWidgets('clears preview when input cleared', (tester) async {
      await tester.pumpWidget(_wrap(const WorkflowImportScreen()));
      await tester.pumpAndSettle();

      // Enter valid JSON
      final validJson = jsonEncode({
        r'$nobla_version': '1.0',
        'workflow': {'name': 'X', 'steps': [], 'triggers': []},
      });
      await tester.enterText(
          find.byKey(const ValueKey('json_input')), validJson);
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('preview_card')), findsOneWidget);

      // Clear input
      await tester.enterText(find.byKey(const ValueKey('json_input')), '');
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('preview_card')), findsNothing);
      expect(find.byKey(const ValueKey('parse_error')), findsNothing);
    });
  });

  group('WorkflowExportSheet', () {
    testWidgets('shows export data with copy button', (tester) async {
      await tester.pumpWidget(_wrap(
        Scaffold(
          body: const WorkflowExportSheet(workflowId: 'wf-1'),
        ),
        overrides: [
          workflowExportProvider.overrideWith((ref, id) async {
            return const WorkflowExportData(
              noblaVersion: '1.0',
              name: 'Exported',
              steps: [TemplateStep(refId: 'a', name: 'A')],
            );
          }),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('Export Workflow'), findsOneWidget);
      expect(find.byKey(const ValueKey('copy_btn')), findsOneWidget);
      expect(find.byKey(const ValueKey('json_output')), findsOneWidget);
    });

    testWidgets('shows error on export failure', (tester) async {
      await tester.pumpWidget(_wrap(
        Scaffold(
          body: const WorkflowExportSheet(workflowId: 'wf-1'),
        ),
        overrides: [
          workflowExportProvider.overrideWith(
              (ref, id) async => throw Exception('Not found')),
        ],
      ));
      await tester.pumpAndSettle();
      expect(find.textContaining('Export failed'), findsOneWidget);
    });
  });

  group('TemplateDetailSheet', () {
    testWidgets('shows detail with steps and triggers', (tester) async {
      await tester.pumpWidget(_wrap(
        Scaffold(
          body: TemplateDetailSheet(
            templateId: 't1',
            scrollController: ScrollController(),
          ),
        ),
        overrides: [
          templateDetailProvider.overrideWith((ref, id) async {
            return const WorkflowTemplateDetail(
              templateId: 't1',
              name: 'My Template',
              description: 'Does things',
              author: 'Nobla',
              version: '1.0.0',
              steps: [
                TemplateStep(refId: 's1', name: 'Step 1', type: 'tool'),
                TemplateStep(
                    refId: 's2',
                    name: 'Step 2',
                    type: 'condition',
                    description: 'Check result'),
              ],
              triggers: [
                TemplateTrigger(
                    eventPattern: 'webhook.*', description: 'On webhook'),
              ],
            );
          }),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('My Template'), findsOneWidget);
      expect(find.text('Does things'), findsOneWidget);
      expect(find.text('Steps'), findsOneWidget);
      expect(find.text('Step 1'), findsOneWidget);
      expect(find.text('Step 2'), findsOneWidget);
      expect(find.text('Triggers'), findsOneWidget);
      expect(find.text('webhook.*'), findsOneWidget);
    });
  });
}

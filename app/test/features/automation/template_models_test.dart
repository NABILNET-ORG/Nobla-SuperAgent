import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/automation/models/template_models.dart';
import 'package:nobla_agent/features/automation/providers/template_providers.dart';

void main() {
  group('TemplateCategory', () {
    test('fromString parses all values', () {
      expect(TemplateCategory.fromString('ci_cd'), TemplateCategory.ciCd);
      expect(TemplateCategory.fromString('notifications'),
          TemplateCategory.notifications);
      expect(TemplateCategory.fromString('data_pipeline'),
          TemplateCategory.dataPipeline);
      expect(TemplateCategory.fromString('devops'), TemplateCategory.devops);
      expect(
          TemplateCategory.fromString('approval'), TemplateCategory.approval);
      expect(TemplateCategory.fromString('integration'),
          TemplateCategory.integration);
      expect(TemplateCategory.fromString('monitoring'),
          TemplateCategory.monitoring);
      expect(TemplateCategory.fromString('custom'), TemplateCategory.custom);
    });

    test('fromString defaults to custom', () {
      expect(TemplateCategory.fromString('unknown'), TemplateCategory.custom);
    });

    test('value returns snake_case string', () {
      expect(TemplateCategory.ciCd.value, 'ci_cd');
      expect(TemplateCategory.dataPipeline.value, 'data_pipeline');
    });

    test('label returns display string', () {
      expect(TemplateCategory.ciCd.label, 'CI/CD');
      expect(TemplateCategory.devops.label, 'DevOps');
      expect(TemplateCategory.dataPipeline.label, 'Data Pipeline');
    });

    test('icon is not empty', () {
      for (final cat in TemplateCategory.values) {
        expect(cat.icon.isNotEmpty, true);
      }
    });
  });

  group('TemplateStep', () {
    test('fromJson parses correctly', () {
      final s = TemplateStep.fromJson({
        'ref_id': 's1',
        'name': 'Build',
        'type': 'tool',
        'config': {'tool': 'build'},
        'depends_on': ['s0'],
        'error_handling': 'retry',
        'max_retries': 3,
        'timeout_seconds': 60,
        'description': 'Build step',
      });
      expect(s.refId, 's1');
      expect(s.name, 'Build');
      expect(s.type, 'tool');
      expect(s.config['tool'], 'build');
      expect(s.dependsOn, ['s0']);
      expect(s.errorHandling, 'retry');
      expect(s.maxRetries, 3);
      expect(s.timeoutSeconds, 60);
      expect(s.description, 'Build step');
    });

    test('fromJson uses defaults for missing fields', () {
      final s = TemplateStep.fromJson({});
      expect(s.refId, '');
      expect(s.type, 'tool');
      expect(s.dependsOn, isEmpty);
      expect(s.errorHandling, 'fail');
      expect(s.maxRetries, 0);
      expect(s.timeoutSeconds, isNull);
    });

    test('toJson produces correct output', () {
      const s = TemplateStep(
        refId: 'x',
        name: 'X',
        type: 'agent',
        config: {'a': 1},
        dependsOn: ['y'],
        maxRetries: 2,
      );
      final j = s.toJson();
      expect(j['ref_id'], 'x');
      expect(j['type'], 'agent');
      expect(j['depends_on'], ['y']);
      expect(j.containsKey('timeout_seconds'), false);
      expect(j.containsKey('description'), false);
    });

    test('toJson includes optional fields when set', () {
      const s = TemplateStep(
        refId: 'a',
        name: 'A',
        timeoutSeconds: 30,
        description: 'Desc',
      );
      final j = s.toJson();
      expect(j['timeout_seconds'], 30);
      expect(j['description'], 'Desc');
    });

    test('round trip via JSON', () {
      const original = TemplateStep(
        refId: 'r',
        name: 'R',
        type: 'delay',
        config: {'secs': 5},
        dependsOn: ['a'],
        timeoutSeconds: 10,
      );
      final restored = TemplateStep.fromJson(original.toJson());
      expect(restored.refId, original.refId);
      expect(restored.type, original.type);
      expect(restored.dependsOn, original.dependsOn);
      expect(restored.timeoutSeconds, original.timeoutSeconds);
    });
  });

  group('TemplateTrigger', () {
    test('fromJson parses correctly', () {
      final t = TemplateTrigger.fromJson({
        'event_pattern': 'webhook.*',
        'conditions': [
          {'field_path': 'action', 'operator': 'eq', 'value': 'push'}
        ],
        'description': 'On push',
      });
      expect(t.eventPattern, 'webhook.*');
      expect(t.conditions.length, 1);
      expect(t.description, 'On push');
    });

    test('fromJson uses defaults', () {
      final t = TemplateTrigger.fromJson({});
      expect(t.eventPattern, '*');
      expect(t.conditions, isEmpty);
    });

    test('toJson produces correct output', () {
      const t = TemplateTrigger(
        eventPattern: 'schedule.daily',
        conditions: [
          {'f': 'v'}
        ],
        description: 'Daily',
      );
      final j = t.toJson();
      expect(j['event_pattern'], 'schedule.daily');
      expect(j['conditions'].length, 1);
      expect(j['description'], 'Daily');
    });

    test('toJson omits description when empty', () {
      const t = TemplateTrigger(eventPattern: 'test.*');
      final j = t.toJson();
      expect(j.containsKey('description'), false);
    });

    test('round trip via JSON', () {
      const original = TemplateTrigger(
        eventPattern: 'webhook.github.*',
        conditions: [
          {'a': 'b'}
        ],
        description: 'GitHub',
      );
      final restored = TemplateTrigger.fromJson(original.toJson());
      expect(restored.eventPattern, original.eventPattern);
      expect(restored.conditions.length, original.conditions.length);
    });
  });

  group('WorkflowTemplate', () {
    test('fromJson parses summary', () {
      final t = WorkflowTemplate.fromJson({
        'template_id': 'tid',
        'name': 'Test',
        'description': 'A test',
        'category': 'ci_cd',
        'tags': ['ci', 'github'],
        'author': 'Nobla',
        'version': '2.0.0',
        'step_count': 4,
        'trigger_count': 1,
        'icon': 'build',
        'bundled': true,
      });
      expect(t.templateId, 'tid');
      expect(t.name, 'Test');
      expect(t.category, TemplateCategory.ciCd);
      expect(t.tags, ['ci', 'github']);
      expect(t.stepCount, 4);
      expect(t.bundled, true);
    });

    test('fromJson uses defaults', () {
      final t = WorkflowTemplate.fromJson({});
      expect(t.templateId, '');
      expect(t.category, TemplateCategory.custom);
      expect(t.bundled, false);
      expect(t.version, '1.0.0');
    });
  });

  group('WorkflowTemplateDetail', () {
    test('fromJson parses steps and triggers', () {
      final d = WorkflowTemplateDetail.fromJson({
        'template_id': 'tid',
        'name': 'Detail',
        'category': 'devops',
        'steps': [
          {'ref_id': 's1', 'name': 'S1', 'type': 'tool'},
          {'ref_id': 's2', 'name': 'S2', 'type': 'agent', 'depends_on': ['s1']},
        ],
        'triggers': [
          {'event_pattern': 'schedule.daily'},
        ],
        'step_count': 2,
        'trigger_count': 1,
        'created_at': '2026-01-01T00:00:00Z',
        'updated_at': '2026-01-02T00:00:00Z',
      });
      expect(d.steps.length, 2);
      expect(d.steps[1].dependsOn, ['s1']);
      expect(d.triggers.length, 1);
      expect(d.createdAt, '2026-01-01T00:00:00Z');
    });

    test('fromJson uses defaults for missing lists', () {
      final d = WorkflowTemplateDetail.fromJson({'template_id': 'x'});
      expect(d.steps, isEmpty);
      expect(d.triggers, isEmpty);
    });
  });

  group('WorkflowExportData', () {
    test('fromJson parses full export envelope', () {
      final e = WorkflowExportData.fromJson({
        r'$nobla_version': '1.0',
        'exported_at': '2026-03-28T12:00:00Z',
        'source': {'workflow_id': 'wid', 'workflow_version': 3},
        'workflow': {
          'name': 'Export',
          'description': 'Exported',
          'steps': [
            {'ref_id': 'a', 'name': 'A'}
          ],
          'triggers': [
            {'event_pattern': 'manual.*'}
          ],
        },
        'metadata': {'key': 'value'},
      });
      expect(e.noblaVersion, '1.0');
      expect(e.sourceWorkflowId, 'wid');
      expect(e.sourceWorkflowVersion, 3);
      expect(e.name, 'Export');
      expect(e.steps.length, 1);
      expect(e.triggers.length, 1);
      expect(e.metadata['key'], 'value');
    });

    test('fromJson uses defaults for missing sections', () {
      final e = WorkflowExportData.fromJson({});
      expect(e.noblaVersion, '');
      expect(e.name, '');
      expect(e.steps, isEmpty);
      expect(e.metadata, isEmpty);
    });

    test('toJson produces correct structure', () {
      const e = WorkflowExportData(
        noblaVersion: '1.0',
        name: 'Test',
        sourceWorkflowId: 'abc',
        sourceWorkflowVersion: 2,
        steps: [TemplateStep(refId: 'x', name: 'X')],
        triggers: [TemplateTrigger(eventPattern: 'test.*')],
        metadata: {'m': 1},
      );
      final j = e.toJson();
      expect(j[r'$nobla_version'], '1.0');
      expect(j['source']['workflow_id'], 'abc');
      expect(j['source']['workflow_version'], 2);
      expect(j['workflow']['name'], 'Test');
      expect((j['workflow']['steps'] as List).length, 1);
      expect(j['metadata']['m'], 1);
    });

    test('round trip via JSON encoding', () {
      const original = WorkflowExportData(
        noblaVersion: '1.0',
        name: 'RT',
        description: 'Round trip',
        steps: [
          TemplateStep(refId: 'a', name: 'A', type: 'tool'),
          TemplateStep(refId: 'b', name: 'B', dependsOn: ['a']),
        ],
        triggers: [TemplateTrigger(eventPattern: 'schedule.*')],
      );
      final jsonStr = jsonEncode(original.toJson());
      final restored =
          WorkflowExportData.fromJson(jsonDecode(jsonStr) as Map<String, dynamic>);
      expect(restored.name, original.name);
      expect(restored.steps.length, 2);
      expect(restored.steps[1].dependsOn, ['a']);
      expect(restored.triggers.length, 1);
    });
  });

  group('CategoryInfo', () {
    test('fromJson parses correctly', () {
      final c = CategoryInfo.fromJson({
        'category': 'ci_cd',
        'label': 'CI/CD',
        'count': 3,
      });
      expect(c.category, 'ci_cd');
      expect(c.label, 'CI/CD');
      expect(c.count, 3);
    });

    test('fromJson uses defaults', () {
      final c = CategoryInfo.fromJson({});
      expect(c.category, '');
      expect(c.count, 0);
    });
  });

  group('TemplateFilter', () {
    test('equality', () {
      const f1 = TemplateFilter(query: 'ci', category: TemplateCategory.ciCd);
      const f2 = TemplateFilter(query: 'ci', category: TemplateCategory.ciCd);
      expect(f1, equals(f2));
    });

    test('inequality', () {
      const f1 = TemplateFilter(query: 'ci');
      const f2 = TemplateFilter(query: 'devops');
      expect(f1, isNot(equals(f2)));
    });

    test('defaults', () {
      const f = TemplateFilter();
      expect(f.query, '');
      expect(f.category, isNull);
      expect(f.tags, isEmpty);
    });
  });
}

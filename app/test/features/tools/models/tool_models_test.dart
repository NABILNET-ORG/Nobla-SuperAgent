import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';

void main() {
  group('ToolCategory', () {
    test('has all 9 categories', () {
      expect(ToolCategory.values.length, 9);
      expect(ToolCategory.values, contains(ToolCategory.ssh));
      expect(ToolCategory.values, contains(ToolCategory.vision));
      expect(ToolCategory.values, contains(ToolCategory.code));
    });

    test('fromString parses backend category strings', () {
      expect(ToolCategory.fromString('ssh'), ToolCategory.ssh);
      expect(ToolCategory.fromString('vision'), ToolCategory.vision);
      expect(ToolCategory.fromString('file_system'), ToolCategory.fileSystem);
      expect(ToolCategory.fromString('app_control'), ToolCategory.appControl);
      expect(ToolCategory.fromString('unknown'), isNull);
    });
  });

  group('ToolManifestEntry', () {
    test('fromJson parses backend manifest', () {
      final entry = ToolManifestEntry.fromJson({
        'name': 'ssh.connect',
        'description': 'SSH connection management',
        'category': 'ssh',
        'tier': 4,
        'requires_approval': true,
      });
      expect(entry.name, 'ssh.connect');
      expect(entry.category, ToolCategory.ssh);
      expect(entry.tier, 4);
      expect(entry.requiresApproval, true);
    });
  });

  group('ActivityEntry with category', () {
    test('fromJson parses category field', () {
      final entry = ActivityEntry.fromJson({
        'tool_name': 'ssh.exec',
        'action': 'execute',
        'description': 'Run ls on server',
        'status': 'success',
        'category': 'ssh',
        'execution_time_ms': 245,
        'timestamp': '2026-03-25T14:30:00Z',
      });
      expect(entry.category, ToolCategory.ssh);
    });

    test('fromJson handles missing category gracefully', () {
      final entry = ActivityEntry.fromJson({
        'tool_name': 'ssh.exec',
        'status': 'success',
        'timestamp': '2026-03-25T14:30:00Z',
      });
      expect(entry.category, isNull);
    });
  });

  group('ActivityFilter', () {
    test('empty filter matches everything', () {
      final filter = ActivityFilter();
      expect(filter.categories, isNull);
      expect(filter.statuses, isNull);
    });

    test('matches checks category and status', () {
      final filter = ActivityFilter(
        categories: {ToolCategory.ssh},
        statuses: {ActivityStatus.success},
      );
      final entry = ActivityEntry(
        toolName: 'ssh.exec',
        action: 'execute',
        description: 'test',
        status: ActivityStatus.success,
        category: ToolCategory.ssh,
        timestamp: DateTime.now(),
      );
      expect(filter.matches(entry), true);
    });

    test('matches rejects wrong category', () {
      final filter = ActivityFilter(categories: {ToolCategory.code});
      final entry = ActivityEntry(
        toolName: 'ssh.exec',
        action: '',
        description: '',
        status: ActivityStatus.success,
        category: ToolCategory.ssh,
        timestamp: DateTime.now(),
      );
      expect(filter.matches(entry), false);
    });
  });
}

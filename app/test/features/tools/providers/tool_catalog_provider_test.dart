import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';

void main() {
  group('ToolManifestEntry.fromJson', () {
    test('parses a complete manifest list', () {
      final jsonList = [
        {
          'name': 'screenshot.capture',
          'description': 'Capture screenshot',
          'category': 'vision',
          'tier': 2,
          'requires_approval': false,
        },
        {
          'name': 'ssh.connect',
          'description': 'SSH connection management',
          'category': 'ssh',
          'tier': 4,
          'requires_approval': true,
        },
      ];
      final entries =
          jsonList.map((j) => ToolManifestEntry.fromJson(j)).toList();
      expect(entries.length, 2);
      expect(entries[0].category, ToolCategory.vision);
      expect(entries[1].requiresApproval, true);
    });

    test('groups by category correctly', () {
      final entries = [
        ToolManifestEntry(
            name: 'a', description: '', category: ToolCategory.ssh,
            tier: 1, requiresApproval: false),
        ToolManifestEntry(
            name: 'b', description: '', category: ToolCategory.ssh,
            tier: 1, requiresApproval: false),
        ToolManifestEntry(
            name: 'c', description: '', category: ToolCategory.code,
            tier: 1, requiresApproval: false),
      ];
      final grouped = <ToolCategory, List<ToolManifestEntry>>{};
      for (final e in entries) {
        if (e.category != null) {
          grouped.putIfAbsent(e.category!, () => []).add(e);
        }
      }
      expect(grouped[ToolCategory.ssh]!.length, 2);
      expect(grouped[ToolCategory.code]!.length, 1);
    });
  });
}

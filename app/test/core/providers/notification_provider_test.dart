import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/shared/providers/tool_activity_provider.dart';

void main() {
  test('tool.activity notification adds entry to shared provider', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(toolActivityProvider.notifier);
    expect(container.read(toolActivityProvider), isEmpty);

    // Simulate what NotificationDispatcher does:
    final params = {
      'tool_name': 'ssh.exec',
      'category': 'ssh',
      'description': 'Execute ls',
      'status': 'success',
      'execution_time_ms': 100,
      'timestamp': '2026-03-25T14:30:00Z',
    };
    notifier.addEntry(ActivityEntry.fromJson(params));

    expect(container.read(toolActivityProvider).length, 1);
    expect(container.read(toolActivityProvider).first.toolName, 'ssh.exec');
  });
}

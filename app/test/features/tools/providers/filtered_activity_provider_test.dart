import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/features/tools/providers/filtered_activity_provider.dart';
import 'package:nobla_agent/shared/providers/tool_activity_provider.dart';

void main() {
  late ProviderContainer container;

  setUp(() {
    container = ProviderContainer();
  });

  tearDown(() => container.dispose());

  void addEntry(String toolName, ActivityStatus status, ToolCategory cat) {
    container.read(toolActivityProvider.notifier).addEntry(ActivityEntry(
          toolName: toolName,
          action: '',
          description: '',
          status: status,
          category: cat,
          timestamp: DateTime.now(),
        ));
  }

  test('no filter returns all entries', () {
    addEntry('ssh.exec', ActivityStatus.success, ToolCategory.ssh);
    addEntry('code.run', ActivityStatus.failed, ToolCategory.code);
    final filtered = container.read(filteredActivityProvider);
    expect(filtered.length, 2);
  });

  test('category filter narrows results', () {
    addEntry('ssh.exec', ActivityStatus.success, ToolCategory.ssh);
    addEntry('code.run', ActivityStatus.failed, ToolCategory.code);
    container.read(activityFilterProvider.notifier).state =
        ActivityFilter(categories: {ToolCategory.ssh});
    final filtered = container.read(filteredActivityProvider);
    expect(filtered.length, 1);
    expect(filtered.first.toolName, 'ssh.exec');
  });

  test('status filter narrows results', () {
    addEntry('ssh.exec', ActivityStatus.success, ToolCategory.ssh);
    addEntry('code.run', ActivityStatus.failed, ToolCategory.code);
    container.read(activityFilterProvider.notifier).state =
        ActivityFilter(statuses: {ActivityStatus.failed});
    final filtered = container.read(filteredActivityProvider);
    expect(filtered.length, 1);
    expect(filtered.first.toolName, 'code.run');
  });

  test('combined filter applies both', () {
    addEntry('ssh.exec', ActivityStatus.success, ToolCategory.ssh);
    addEntry('ssh.connect', ActivityStatus.failed, ToolCategory.ssh);
    addEntry('code.run', ActivityStatus.success, ToolCategory.code);
    container.read(activityFilterProvider.notifier).state = ActivityFilter(
      categories: {ToolCategory.ssh},
      statuses: {ActivityStatus.success},
    );
    final filtered = container.read(filteredActivityProvider);
    expect(filtered.length, 1);
    expect(filtered.first.toolName, 'ssh.exec');
  });
}

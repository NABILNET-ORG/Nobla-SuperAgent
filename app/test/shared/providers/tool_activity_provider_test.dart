import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/shared/providers/tool_activity_provider.dart';

void main() {
  late ToolActivityNotifier notifier;

  setUp(() {
    notifier = ToolActivityNotifier();
  });

  tearDown(() {
    notifier.dispose();
  });

  ActivityEntry makeEntry({
    String toolName = 'test.tool',
    ActivityStatus status = ActivityStatus.success,
  }) {
    return ActivityEntry(
      toolName: toolName,
      action: 'test',
      description: 'test entry',
      status: status,
      timestamp: DateTime.now(),
    );
  }

  test('starts with empty list', () {
    expect(notifier.state, isEmpty);
  });

  test('addEntry prepends to list', () {
    final e1 = makeEntry(toolName: 'first');
    final e2 = makeEntry(toolName: 'second');
    notifier.addEntry(e1);
    notifier.addEntry(e2);
    expect(notifier.state.length, 2);
    expect(notifier.state.first.toolName, 'second');
  });

  test('enforces max 200 entries', () {
    for (var i = 0; i < 210; i++) {
      notifier.addEntry(makeEntry(toolName: 'tool.$i'));
    }
    expect(notifier.state.length, 200);
    expect(notifier.state.first.toolName, 'tool.209');
  });

  test('clear removes all entries', () {
    notifier.addEntry(makeEntry());
    notifier.addEntry(makeEntry());
    notifier.clear();
    expect(notifier.state, isEmpty);
  });
}

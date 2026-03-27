import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/features/tools/widgets/activity_list.dart';
import 'package:nobla_agent/shared/providers/tool_activity_provider.dart';

void main() {
  testWidgets('shows empty state when no entries', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(home: Scaffold(body: ActivityListTab())),
      ),
    );
    expect(find.text('No activity yet'), findsOneWidget);
  });

  testWidgets('displays activity entries', (tester) async {
    final container = ProviderContainer();
    container.read(toolActivityProvider.notifier).addEntry(ActivityEntry(
          toolName: 'ssh.exec',
          action: 'execute',
          description: 'Run ls on server',
          status: ActivityStatus.success,
          category: ToolCategory.ssh,
          timestamp: DateTime.now(),
          executionTimeMs: 245,
        ));

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: ActivityListTab())),
      ),
    );
    await tester.pump();

    expect(find.text('ssh.exec'), findsOneWidget);
    expect(find.text('Run ls on server'), findsOneWidget);
    expect(find.text('245ms'), findsOneWidget);
  });
}

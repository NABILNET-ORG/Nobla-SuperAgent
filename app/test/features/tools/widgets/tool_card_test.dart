import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/features/tools/widgets/tool_card.dart';

void main() {
  testWidgets('ToolCard displays tool name and description', (tester) async {
    const tool = ToolManifestEntry(
      name: 'ssh.connect',
      description: 'SSH connection management',
      category: ToolCategory.ssh,
      tier: 4,
      requiresApproval: true,
    );
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: ToolCard(tool: tool))),
    );
    expect(find.text('ssh.connect'), findsOneWidget);
    expect(find.text('SSH connection management'), findsOneWidget);
    expect(find.text('ADMIN'), findsOneWidget);
    expect(find.byIcon(Icons.lock_outline), findsOneWidget);
  });

  testWidgets('ToolCard hides lock icon when no approval required',
      (tester) async {
    const tool = ToolManifestEntry(
      name: 'screenshot.capture',
      description: 'Capture screenshot',
      category: ToolCategory.vision,
      tier: 2,
      requiresApproval: false,
    );
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: ToolCard(tool: tool))),
    );
    expect(find.byIcon(Icons.lock_outline), findsNothing);
    expect(find.text('STD'), findsOneWidget);
  });
}

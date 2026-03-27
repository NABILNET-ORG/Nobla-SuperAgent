import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/tools/widgets/mirror_view.dart';
import 'package:nobla_agent/features/tools/providers/tool_mirror_provider.dart';

void main() {
  testWidgets('shows placeholder when no screenshot', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          toolMirrorProvider.overrideWith(
            (ref) => ToolMirrorNotifier(
                sendRpc: (m, p) async => <String, dynamic>{}),
          ),
        ],
        child: const MaterialApp(home: Scaffold(body: MirrorView())),
      ),
    );
    expect(find.text('No screenshots yet'), findsOneWidget);
    expect(find.byIcon(Icons.camera_alt_outlined), findsOneWidget);
  });
}

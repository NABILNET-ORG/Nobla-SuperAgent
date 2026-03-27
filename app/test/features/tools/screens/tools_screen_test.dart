import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/tools/screens/tools_screen.dart';
import 'package:nobla_agent/features/tools/providers/tool_mirror_provider.dart';
import 'package:nobla_agent/features/tools/providers/tool_catalog_provider.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';

void main() {
  testWidgets('ToolsScreen shows 3 tabs', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          toolMirrorProvider.overrideWith(
            (ref) => ToolMirrorNotifier(
                sendRpc: (m, p) async => <String, dynamic>{}),
          ),
          toolCatalogProvider.overrideWith(
            (ref) async => <ToolManifestEntry>[],
          ),
        ],
        child: const MaterialApp(home: ToolsScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Mirror'), findsOneWidget);
    expect(find.text('Activity'), findsOneWidget);
    expect(find.text('Browse'), findsOneWidget);
  });
}

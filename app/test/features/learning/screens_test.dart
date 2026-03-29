import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/learning/providers/learning_providers.dart';
import 'package:nobla_agent/features/learning/screens/agent_intelligence_screen.dart';

Widget _wrap(Widget child, {List<Override> overrides = const []}) {
  return ProviderScope(
    overrides: overrides,
    child: MaterialApp(home: child),
  );
}

void main() {
  final defaultOverrides = [
    feedbackStatsProvider.overrideWith((_) async => {
      'total': 0, 'positive': 0, 'negative': 0,
    }),
    patternListProvider.overrideWith((_) async => []),
    macroListProvider.overrideWith((_) async => []),
  ];

  group('AgentIntelligenceScreen', () {
    testWidgets('shows 4 tabs', (tester) async {
      await tester.pumpWidget(_wrap(
        const AgentIntelligenceScreen(),
        overrides: defaultOverrides,
      ));
      await tester.pumpAndSettle();
      // Use Tab widget finder to avoid collision with stat card labels in tab body
      expect(find.widgetWithText(Tab, 'Overview'), findsOneWidget);
      expect(find.widgetWithText(Tab, 'Patterns'), findsOneWidget);
      expect(find.widgetWithText(Tab, 'Auto-Skills'), findsOneWidget);
      expect(find.widgetWithText(Tab, 'Settings'), findsOneWidget);
    });

    testWidgets('tabs are tappable', (tester) async {
      await tester.pumpWidget(_wrap(
        const AgentIntelligenceScreen(),
        overrides: defaultOverrides,
      ));
      await tester.pumpAndSettle();
      // Tap the Tab widget specifically (not the stat card label)
      await tester.tap(find.widgetWithText(Tab, 'Patterns'));
      await tester.pumpAndSettle();
      // No crash = tab switch works
    });

    testWidgets('shows app bar with title', (tester) async {
      await tester.pumpWidget(_wrap(
        const AgentIntelligenceScreen(),
        overrides: defaultOverrides,
      ));
      await tester.pumpAndSettle();
      expect(find.text('Agent Intelligence'), findsOneWidget);
    });
  });
}

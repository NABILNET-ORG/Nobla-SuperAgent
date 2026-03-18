import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/dashboard/widgets/connection_card.dart';
import 'package:nobla_agent/features/dashboard/widgets/security_tier_card.dart';
import 'package:nobla_agent/features/dashboard/widgets/cost_card.dart';

void main() {
  group('ConnectionCard', () {
    testWidgets('shows connected status', (tester) async {
      await tester.pumpWidget(const MaterialApp(
          home: Scaffold(
              body: ConnectionCard(
        serverUrl: 'ws://localhost:8000/ws',
        isConnected: true,
        serverVersion: '0.1.0',
      ))));
      expect(find.text('Connected'), findsOneWidget);
      expect(find.text('Server: ws://localhost:8000/ws'), findsOneWidget);
    });
  });

  group('SecurityTierCard', () {
    testWidgets('displays current tier', (tester) async {
      await tester.pumpWidget(MaterialApp(
          home: Scaffold(
              body: SecurityTierCard(
        currentTier: 1,
        onTierChange: (_) {},
      ))));
      expect(find.text('SAFE'), findsWidgets);
    });
  });

  group('CostCard', () {
    testWidgets('shows cost progress bars', (tester) async {
      await tester.pumpWidget(MaterialApp(
          home: Scaffold(
              body: CostCard(costData: {
        'session_usd': 0.5,
        'daily_usd': 2.0,
        'monthly_usd': 10.0,
        'limits': {
          'session': 1.0,
          'daily': 5.0,
          'monthly': 50.0,
        },
      }))));
      expect(find.text('Session'), findsOneWidget);
      expect(find.text('Daily'), findsOneWidget);
      expect(find.text('Monthly'), findsOneWidget);
      expect(find.byType(LinearProgressIndicator), findsNWidgets(3));
    });
  });
}

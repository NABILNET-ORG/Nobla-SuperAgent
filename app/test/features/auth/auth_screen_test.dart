import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/auth/screens/login_screen.dart';
import 'package:nobla_agent/features/auth/screens/register_screen.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

void main() {
  group('LoginScreen', () {
    testWidgets('shows passphrase field and connect button', (tester) async {
      await tester.pumpWidget(
          const ProviderScope(child: MaterialApp(home: LoginScreen())));
      expect(find.text('Passphrase'), findsOneWidget);
      expect(find.text('Connect'), findsOneWidget);
      expect(find.text('Register'), findsOneWidget);
    });

    testWidgets('shows error for empty passphrase', (tester) async {
      await tester.pumpWidget(
          const ProviderScope(child: MaterialApp(home: LoginScreen())));
      await tester.tap(find.text('Connect'));
      await tester.pumpAndSettle();
      expect(find.text('Passphrase is required'), findsOneWidget);
    });
  });

  group('RegisterScreen', () {
    testWidgets('shows all registration fields', (tester) async {
      await tester.pumpWidget(
          const ProviderScope(child: MaterialApp(home: RegisterScreen())));
      expect(find.text('Display Name'), findsOneWidget);
      expect(find.text('Passphrase'), findsOneWidget);
      expect(find.text('Confirm Passphrase'), findsOneWidget);
      expect(find.text('Create Account'), findsWidgets);
    });

    testWidgets('validates passphrase mismatch', (tester) async {
      await tester.pumpWidget(
          const ProviderScope(child: MaterialApp(home: RegisterScreen())));
      await tester.enterText(find.byType(TextFormField).at(0), 'TestUser');
      await tester.enterText(find.byType(TextFormField).at(1), 'password123');
      await tester.enterText(find.byType(TextFormField).at(2), 'different123');
      await tester.tap(find.byType(FilledButton).first);
      await tester.pumpAndSettle();
      expect(find.text('Passphrases do not match'), findsOneWidget);
    });
  });
}

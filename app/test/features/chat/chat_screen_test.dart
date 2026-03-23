import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/chat/widgets/message_bubble.dart';
import 'package:nobla_agent/features/chat/widgets/message_input.dart';
import 'package:nobla_agent/shared/models/chat_message.dart';

void main() {
  group('MessageBubble', () {
    testWidgets('renders user message on the right', (tester) async {
      final msg = ChatMessage.user('Hello');
      await tester.pumpWidget(
          MaterialApp(home: Scaffold(body: MessageBubble(message: msg))));
      final align = tester.widget<Align>(find.byType(Align).first);
      expect(align.alignment, Alignment.centerRight);
      expect(find.text('Hello'), findsOneWidget);
    });

    testWidgets('renders agent message on the left', (tester) async {
      final msg = ChatMessage(
        id: '1',
        content: 'Hi there',
        isUser: false,
        timestamp: DateTime.now(),
      );
      await tester.pumpWidget(
          MaterialApp(home: Scaffold(body: MessageBubble(message: msg))));
      final align = tester.widget<Align>(find.byType(Align).first);
      expect(align.alignment, Alignment.centerLeft);
    });
  });

  group('MessageInput', () {
    testWidgets('calls onSend with text and clears field', (tester) async {
      String? sent;
      await tester.pumpWidget(MaterialApp(
          home: Scaffold(body: MessageInput(onSend: (t) => sent = t))));
      await tester.enterText(find.byType(TextField), 'Test message');
      await tester.tap(find.byIcon(Icons.send));
      await tester.pump();
      expect(sent, 'Test message');
    });

    testWidgets('disabled state prevents input', (tester) async {
      await tester.pumpWidget(MaterialApp(
          home: Scaffold(body: MessageInput(onSend: (_) {}, enabled: false))));
      final field = tester.widget<TextField>(find.byType(TextField));
      expect(field.enabled, false);
    });
  });
}

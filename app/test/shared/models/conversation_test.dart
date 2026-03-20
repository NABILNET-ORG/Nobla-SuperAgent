import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/shared/models/conversation.dart';

void main() {
  group('Conversation', () {
    test('fromJson parses correctly', () {
      final json = {
        'id': 'abc-123',
        'title': 'Test Chat',
        'summary': 'A test conversation',
        'topics': ['python', 'ml'],
        'message_count': 5,
        'updated_at': '2026-03-19T10:00:00',
        'created_at': '2026-03-19T09:00:00',
      };
      final conv = Conversation.fromJson(json);
      expect(conv.id, 'abc-123');
      expect(conv.title, 'Test Chat');
      expect(conv.summary, 'A test conversation');
      expect(conv.topics, ['python', 'ml']);
      expect(conv.messageCount, 5);
    });

    test('fromJson handles missing optional fields', () {
      final json = {'id': 'abc', 'title': null};
      final conv = Conversation.fromJson(json);
      expect(conv.title, 'Untitled');
      expect(conv.summary, isNull);
      expect(conv.topics, isEmpty);
      expect(conv.messageCount, 0);
    });

    test('copyWith updates fields', () {
      const conv = Conversation(id: '1', title: 'Old');
      final updated = conv.copyWith(title: 'New');
      expect(updated.title, 'New');
      expect(updated.id, '1');
    });
  });
}

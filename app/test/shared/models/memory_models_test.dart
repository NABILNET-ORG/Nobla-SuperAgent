import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/shared/models/memory_fact.dart';
import 'package:nobla_agent/shared/models/memory_entity.dart';
import 'package:nobla_agent/shared/models/memory_stats.dart';

void main() {
  group('MemoryFact', () {
    test('fromJson parses correctly', () {
      final json = {
        'id': 'fact-1',
        'content': 'User likes Python',
        'note_type': 'preference',
        'confidence': 0.9,
        'keywords': ['python'],
        'created_at': '2026-03-19',
      };
      final fact = MemoryFact.fromJson(json);
      expect(fact.id, 'fact-1');
      expect(fact.content, 'User likes Python');
      expect(fact.noteType, 'preference');
      expect(fact.confidence, 0.9);
      expect(fact.keywords, ['python']);
    });

    test('fromJson handles missing fields', () {
      final json = {'id': '1', 'content': 'test'};
      final fact = MemoryFact.fromJson(json);
      expect(fact.noteType, 'fact');
      expect(fact.confidence, isNull);
      expect(fact.keywords, isEmpty);
    });
  });

  group('MemoryEntity', () {
    test('fromJson parses correctly', () {
      final json = {
        'name': 'Alice',
        'entity_type': 'PERSON',
        'neighbors': 3,
      };
      final entity = MemoryEntity.fromJson(json);
      expect(entity.name, 'Alice');
      expect(entity.entityType, 'PERSON');
      expect(entity.neighborCount, 3);
    });
  });

  group('MemoryStats', () {
    test('fromJson parses correctly', () {
      final json = {
        'total_memories': 42,
        'by_type': {'fact': 30, 'entity': 12},
        'total_links': 8,
        'graph_entities': 15,
        'graph_relationships': 10,
      };
      final stats = MemoryStats.fromJson(json);
      expect(stats.totalMemories, 42);
      expect(stats.byType['fact'], 30);
      expect(stats.graphEntities, 15);
    });

    test('default values', () {
      const stats = MemoryStats();
      expect(stats.totalMemories, 0);
      expect(stats.byType, isEmpty);
    });
  });
}

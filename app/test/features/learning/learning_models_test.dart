import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/learning/models/learning_models.dart';

void main() {
  group('PatternStatus', () {
    test('has all values', () {
      expect(PatternStatus.values.length, 4);
    });
  });

  group('SuggestionStatus', () {
    test('has snoozed status', () {
      expect(SuggestionStatus.snoozed.name, 'snoozed');
    });
    test('has all 5 values', () {
      expect(SuggestionStatus.values.length, 5);
    });
  });

  group('ProactiveLevel', () {
    test('has all 4 values', () {
      expect(ProactiveLevel.values.length, 4);
    });
  });

  group('ResponseFeedback', () {
    test('fromJson round-trip', () {
      final json = {
        'id': 'fb-1',
        'conversation_id': 'conv-1',
        'message_id': 'msg-1',
        'user_id': 'user-1',
        'quick_rating': 1,
        'star_rating': 5,
        'comment': 'Great!',
        'context': {
          'llm_model': 'gemini-pro',
          'tool_chain': ['code.run'],
        },
        'timestamp': '2026-03-28T10:00:00Z',
      };
      final fb = ResponseFeedback.fromJson(json);
      expect(fb.quickRating, 1);
      expect(fb.starRating, 5);
      expect(fb.isPositive, true);
      expect(fb.toJson()['quick_rating'], 1);
    });

    test('isNegative for thumbs down', () {
      final fb = ResponseFeedback.fromJson({
        'id': 'fb-2',
        'conversation_id': 'c',
        'message_id': 'm',
        'user_id': 'u',
        'quick_rating': -1,
        'context': {'llm_model': 'x', 'tool_chain': []},
        'timestamp': '2026-03-28T10:00:00Z',
      });
      expect(fb.isNegative, true);
    });
  });

  group('PatternCandidate', () {
    test('fromJson creates pattern', () {
      final json = {
        'id': 'pat-1',
        'user_id': 'u',
        'fingerprint': 'abc',
        'description': 'test',
        'occurrences': [],
        'tool_sequence': ['a', 'b'],
        'variable_params': {},
        'status': 'detected',
        'confidence': 0.8,
        'detection_method': 'sequence',
        'created_at': '2026-03-28T10:00:00Z',
      };
      final p = PatternCandidate.fromJson(json);
      expect(p.status, PatternStatus.detected);
      expect(p.toolSequence, ['a', 'b']);
    });
  });

  group('ProactiveSuggestion', () {
    test('fromJson with snooze fields', () {
      final json = {
        'id': 's-1',
        'type': 'pattern',
        'title': 'Test',
        'description': 'desc',
        'confidence': 0.9,
        'user_id': 'u',
        'status': 'snoozed',
        'snooze_until': '2026-03-30T10:00:00Z',
        'snooze_count': 2,
        'created_at': '2026-03-28T10:00:00Z',
      };
      final s = ProactiveSuggestion.fromJson(json);
      expect(s.status, SuggestionStatus.snoozed);
      expect(s.snoozeCount, 2);
      expect(s.snoozeUntil, isNotNull);
    });
  });

  group('LearningSettings', () {
    test('fromJson defaults', () {
      final s = LearningSettings.fromJson({
        'enabled': true,
        'proactive_level': 'conservative',
      });
      expect(s.enabled, true);
      expect(s.proactiveLevel, ProactiveLevel.conservative);
    });
  });

  group('ABExperiment', () {
    test('fromJson with variants', () {
      final json = {
        'id': 'exp-1',
        'task_category': 'hard',
        'variants': [
          {
            'id': 'v1',
            'model': 'gpt-4',
            'sample_count': 0,
            'win_rate': 0.0,
            'feedback_scores': [],
          },
        ],
        'status': 'running',
        'min_samples': 20,
        'epsilon': 0.1,
        'created_at': '2026-03-28T10:00:00Z',
      };
      final exp = ABExperiment.fromJson(json);
      expect(exp.variants.length, 1);
      expect(exp.status, ExperimentStatus.running);
    });
  });

  group('WorkflowMacro', () {
    test('fromJson creates macro', () {
      final json = {
        'id': 'm-1',
        'name': 'Deploy',
        'description': 'Auto deploy',
        'pattern_id': 'p1',
        'workflow_id': 'w1',
        'parameters': [],
        'tier': 'macro',
        'usage_count': 0,
        'user_id': 'u',
        'created_at': '2026-03-28T10:00:00Z',
      };
      final m = WorkflowMacro.fromJson(json);
      expect(m.tier, MacroTier.macro);
      expect(m.name, 'Deploy');
    });
  });
}

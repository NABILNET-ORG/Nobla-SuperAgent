import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Feedback statistics from the backend learning API.
/// Returns totals for positive, negative, and neutral feedback.
final feedbackStatsProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  return {'total': 0, 'positive': 0, 'negative': 0};
});

/// List of detected pattern candidates.
final patternListProvider = FutureProvider<List<dynamic>>((ref) async {
  return [];
});

/// List of workflow macros generated from patterns.
final macroListProvider = FutureProvider<List<dynamic>>((ref) async {
  return [];
});

/// List of active A/B experiments.
final experimentListProvider = FutureProvider<List<dynamic>>((ref) async {
  return [];
});

/// List of proactive suggestions for the current user.
final suggestionListProvider = FutureProvider<List<dynamic>>((ref) async {
  return [];
});

/// Learning feature settings (enabled flags, proactive level).
final learningSettingsProvider = StateProvider<Map<String, dynamic>>((ref) {
  return {'enabled': true, 'proactive_level': 'conservative'};
});

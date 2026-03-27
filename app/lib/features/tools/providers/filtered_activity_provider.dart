import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/shared/providers/tool_activity_provider.dart';

/// Holds the current filter state for the activity feed.
final activityFilterProvider = StateProvider<ActivityFilter>((ref) {
  return const ActivityFilter();
});

/// Derived provider that applies the current filter to the shared activity list.
final filteredActivityProvider = Provider<List<ActivityEntry>>((ref) {
  final entries = ref.watch(toolActivityProvider);
  final filter = ref.watch(activityFilterProvider);
  if (!filter.isActive) return entries;
  return entries.where((e) => filter.matches(e)).toList();
});

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';

/// Maximum number of activity entries kept in memory.
const int maxActivityEntries = 200;

/// Shared notifier for tool activity events from the backend.
///
/// Both the security feature (compact feed) and tools feature
/// (filterable full feed) consume this provider.
class ToolActivityNotifier extends StateNotifier<List<ActivityEntry>> {
  ToolActivityNotifier() : super(const []);

  /// Prepend a new activity entry, enforcing the max buffer size.
  void addEntry(ActivityEntry entry) {
    final updated = [entry, ...state];
    if (updated.length > maxActivityEntries) {
      state = updated.sublist(0, maxActivityEntries);
    } else {
      state = updated;
    }
  }

  /// Remove all entries.
  void clear() => state = const [];
}

final toolActivityProvider =
    StateNotifierProvider<ToolActivityNotifier, List<ActivityEntry>>((ref) {
  return ToolActivityNotifier();
});

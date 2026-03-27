import 'package:flutter/foundation.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';

/// Tool categories matching backend ToolCategory enum.
enum ToolCategory {
  vision,
  input,
  fileSystem,
  appControl,
  code,
  git,
  ssh,
  clipboard,
  search;

  /// Parse a backend category string like "file_system" into enum value.
  static ToolCategory? fromString(String? s) => switch (s) {
        'vision' => ToolCategory.vision,
        'input' => ToolCategory.input,
        'file_system' => ToolCategory.fileSystem,
        'app_control' => ToolCategory.appControl,
        'code' => ToolCategory.code,
        'git' => ToolCategory.git,
        'ssh' => ToolCategory.ssh,
        'clipboard' => ToolCategory.clipboard,
        'search' => ToolCategory.search,
        _ => null,
      };

  /// Human-readable label for display.
  String get label => switch (this) {
        ToolCategory.vision => 'Vision',
        ToolCategory.input => 'Input',
        ToolCategory.fileSystem => 'File System',
        ToolCategory.appControl => 'App Control',
        ToolCategory.code => 'Code',
        ToolCategory.git => 'Git',
        ToolCategory.ssh => 'SSH',
        ToolCategory.clipboard => 'Clipboard',
        ToolCategory.search => 'Search',
      };
}

/// A tool entry from the backend manifest (tool.list RPC).
@immutable
class ToolManifestEntry {
  final String name;
  final String description;
  final ToolCategory? category;
  final int tier;
  final bool requiresApproval;

  const ToolManifestEntry({
    required this.name,
    required this.description,
    this.category,
    required this.tier,
    required this.requiresApproval,
  });

  factory ToolManifestEntry.fromJson(Map<String, dynamic> json) {
    return ToolManifestEntry(
      name: json['name'] as String,
      description: json['description'] as String? ?? '',
      category: ToolCategory.fromString(json['category'] as String?),
      tier: json['tier'] as int? ?? 1,
      requiresApproval: json['requires_approval'] as bool? ?? false,
    );
  }
}

/// State for the screen mirror.
@immutable
class MirrorState {
  final bool isSubscribed;
  final Uint8List? latestScreenshot;
  final DateTime? lastUpdated;
  final bool isCapturing;
  final String? error;

  const MirrorState({
    this.isSubscribed = false,
    this.latestScreenshot,
    this.lastUpdated,
    this.isCapturing = false,
    this.error,
  });

  MirrorState copyWith({
    bool? isSubscribed,
    Uint8List? latestScreenshot,
    DateTime? lastUpdated,
    bool? isCapturing,
    String? error,
    bool clearScreenshot = false,
    bool clearError = false,
  }) {
    return MirrorState(
      isSubscribed: isSubscribed ?? this.isSubscribed,
      latestScreenshot:
          clearScreenshot ? null : (latestScreenshot ?? this.latestScreenshot),
      lastUpdated: lastUpdated ?? this.lastUpdated,
      isCapturing: isCapturing ?? this.isCapturing,
      error: clearError ? null : (error ?? this.error),
    );
  }
}

/// Filter state for the activity feed.
@immutable
class ActivityFilter {
  final Set<ToolCategory>? categories;
  final Set<ActivityStatus>? statuses;

  const ActivityFilter({this.categories, this.statuses});

  /// Returns true if [entry] passes this filter.
  bool matches(ActivityEntry entry) {
    if (categories != null &&
        categories!.isNotEmpty &&
        (entry.category == null || !categories!.contains(entry.category))) {
      return false;
    }
    if (statuses != null &&
        statuses!.isNotEmpty &&
        !statuses!.contains(entry.status)) {
      return false;
    }
    return true;
  }

  ActivityFilter copyWith({
    Set<ToolCategory>? categories,
    Set<ActivityStatus>? statuses,
    bool clearCategories = false,
    bool clearStatuses = false,
  }) {
    return ActivityFilter(
      categories: clearCategories ? null : (categories ?? this.categories),
      statuses: clearStatuses ? null : (statuses ?? this.statuses),
    );
  }

  /// True if any filter is active.
  bool get isActive =>
      (categories != null && categories!.isNotEmpty) ||
      (statuses != null && statuses!.isNotEmpty);
}

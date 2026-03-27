import 'package:flutter/foundation.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';

/// A pending tool-approval request received over WebSocket.
@immutable
class ApprovalRequest {
  final String requestId;
  final String toolName;
  final String description;
  final Map<String, dynamic> paramsSummary;
  final int timeoutSeconds;
  final DateTime receivedAt;

  const ApprovalRequest({
    required this.requestId,
    required this.toolName,
    required this.description,
    required this.paramsSummary,
    required this.timeoutSeconds,
    required this.receivedAt,
  });

  factory ApprovalRequest.fromJson(Map<String, dynamic> json) {
    return ApprovalRequest(
      requestId: json['request_id'] as String,
      toolName: json['tool_name'] as String,
      description: json['description'] as String? ?? '',
      paramsSummary: json['params_summary'] as Map<String, dynamic>? ?? {},
      timeoutSeconds: json['timeout_seconds'] as int? ?? 30,
      receivedAt: DateTime.now(),
    );
  }
}

/// Status of a completed or in-flight tool activity.
enum ActivityStatus { success, failed, denied, pending }

/// A single entry in the tool-activity feed.
@immutable
class ActivityEntry {
  final String toolName;
  final String action;
  final String description;
  final ActivityStatus status;
  final ToolCategory? category;
  final int? executionTimeMs;
  final DateTime timestamp;

  const ActivityEntry({
    required this.toolName,
    required this.action,
    required this.description,
    required this.status,
    this.category,
    this.executionTimeMs,
    required this.timestamp,
  });

  factory ActivityEntry.fromJson(Map<String, dynamic> json) {
    return ActivityEntry(
      toolName: json['tool_name'] as String,
      action: json['action'] as String? ?? '',
      description: json['description'] as String? ?? '',
      status: _parseStatus(json['status'] as String? ?? 'success'),
      category: ToolCategory.fromString(json['category'] as String?),
      executionTimeMs: json['execution_time_ms'] as int?,
      timestamp:
          DateTime.tryParse(json['timestamp'] as String? ?? '') ?? DateTime.now(),
    );
  }

  static ActivityStatus _parseStatus(String s) => switch (s) {
        'success' => ActivityStatus.success,
        'failed' => ActivityStatus.failed,
        'denied' => ActivityStatus.denied,
        _ => ActivityStatus.pending,
      };
}

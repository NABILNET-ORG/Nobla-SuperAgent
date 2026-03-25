import 'dart:async';
import 'dart:collection';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';

/// Immutable state exposed by [ApprovalNotifier].
class ApprovalState {
  final ApprovalRequest? current;
  final int remainingSeconds;
  final List<ActivityEntry> activities;

  const ApprovalState({
    this.current,
    this.remainingSeconds = 0,
    this.activities = const [],
  });

  ApprovalState copyWith({
    ApprovalRequest? current,
    int? remainingSeconds,
    List<ActivityEntry>? activities,
    bool clearCurrent = false,
  }) {
    return ApprovalState(
      current: clearCurrent ? null : (current ?? this.current),
      remainingSeconds: remainingSeconds ?? this.remainingSeconds,
      activities: activities ?? this.activities,
    );
  }
}

/// Manages approval requests queue, countdown timer, and activity feed.
///
/// [sendWebSocketMessage] is a callback the notifier uses to push
/// approve / deny responses back to the backend over the existing
/// WebSocket connection.
class ApprovalNotifier extends StateNotifier<ApprovalState> {
  final void Function(Map<String, dynamic>) sendWebSocketMessage;
  final Queue<ApprovalRequest> _queue = Queue<ApprovalRequest>();
  Timer? _countdownTimer;

  /// Maximum number of activity entries kept in memory.
  static const int _maxActivities = 50;

  ApprovalNotifier({required this.sendWebSocketMessage})
      : super(const ApprovalState());

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /// Called when a new approval request arrives from the backend.
  void onApprovalRequest(ApprovalRequest request) {
    if (state.current == null) {
      _showRequest(request);
    } else {
      _queue.add(request);
    }
  }

  /// User approves the current request.
  void approve(String requestId) {
    if (state.current?.requestId != requestId) return;
    _respond(requestId, approved: true);
    _processNext();
  }

  /// User denies the current request (or swipe-dismissed / timed out).
  void deny(String requestId) {
    if (state.current?.requestId != requestId) return;
    _respond(requestId, approved: false);
    _processNext();
  }

  /// Called when a tool-activity notification arrives from the backend.
  void onActivity(ActivityEntry entry) {
    final updated = [entry, ...state.activities];
    if (updated.length > _maxActivities) {
      state = state.copyWith(activities: updated.sublist(0, _maxActivities));
    } else {
      state = state.copyWith(activities: updated);
    }
  }

  // ---------------------------------------------------------------------------
  // Internal helpers
  // ---------------------------------------------------------------------------

  void _showRequest(ApprovalRequest request) {
    _countdownTimer?.cancel();
    state = state.copyWith(
      current: request,
      remainingSeconds: request.timeoutSeconds,
      clearCurrent: false,
    );
    _startCountdown(request);
  }

  void _startCountdown(ApprovalRequest request) {
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      final next = state.remainingSeconds - 1;
      if (next <= 0) {
        // Auto-deny on timeout.
        deny(request.requestId);
      } else {
        state = state.copyWith(remainingSeconds: next);
      }
    });
  }

  void _respond(String requestId, {required bool approved}) {
    _countdownTimer?.cancel();
    sendWebSocketMessage({
      'jsonrpc': '2.0',
      'method': 'tool.approval_response',
      'params': {
        'request_id': requestId,
        'approved': approved,
      },
    });
  }

  void _processNext() {
    if (_queue.isNotEmpty) {
      _showRequest(_queue.removeFirst());
    } else {
      state = state.copyWith(clearCurrent: true, remainingSeconds: 0);
    }
  }

  @override
  void dispose() {
    _countdownTimer?.cancel();
    super.dispose();
  }
}

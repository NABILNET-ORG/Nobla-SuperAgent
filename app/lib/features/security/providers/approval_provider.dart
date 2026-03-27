import 'dart:async';
import 'dart:collection';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';

/// Immutable state exposed by [ApprovalNotifier].
class ApprovalState {
  final ApprovalRequest? current;
  final int remainingSeconds;

  const ApprovalState({
    this.current,
    this.remainingSeconds = 0,
  });

  ApprovalState copyWith({
    ApprovalRequest? current,
    int? remainingSeconds,
    bool clearCurrent = false,
  }) {
    return ApprovalState(
      current: clearCurrent ? null : (current ?? this.current),
      remainingSeconds: remainingSeconds ?? this.remainingSeconds,
    );
  }
}

/// Manages approval requests queue and countdown timer.
///
/// Activity feed is now managed by [ToolActivityNotifier] in shared providers.
class ApprovalNotifier extends StateNotifier<ApprovalState> {
  final void Function(Map<String, dynamic>) sendWebSocketMessage;
  final Queue<ApprovalRequest> _queue = Queue<ApprovalRequest>();
  Timer? _countdownTimer;

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

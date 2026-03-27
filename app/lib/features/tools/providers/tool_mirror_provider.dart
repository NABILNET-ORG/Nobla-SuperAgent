import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/main.dart' show jsonRpcProvider;

/// Callback type for sending RPC calls.
typedef RpcSender = Future<Map<String, dynamic>> Function(
    String method, Map<String, dynamic> params);

/// Decode base64 in a background isolate to avoid UI jank.
Uint8List _decodeBase64(String encoded) => base64Decode(encoded);

/// Manages mirror subscription state and screenshot display.
class ToolMirrorNotifier extends StateNotifier<MirrorState> {
  final RpcSender _sendRpc;

  ToolMirrorNotifier({required RpcSender sendRpc})
      : _sendRpc = sendRpc,
        super(const MirrorState());

  /// Subscribe to event-driven screenshots.
  Future<void> subscribe() async {
    if (state.isSubscribed) return;
    try {
      await _sendRpc('tool.mirror.subscribe', {});
      state = state.copyWith(isSubscribed: true, clearError: true);
    } catch (e) {
      state = state.copyWith(error: 'Failed to subscribe: $e');
    }
  }

  /// Unsubscribe from event-driven screenshots.
  Future<void> unsubscribe() async {
    if (!state.isSubscribed) return;
    try {
      await _sendRpc('tool.mirror.unsubscribe', {});
    } catch (_) {
      // Best effort — server may already have disconnected
    }
    state = state.copyWith(isSubscribed: false);
  }

  /// Manual capture — request-response pattern.
  Future<void> captureNow() async {
    if (state.isCapturing) return;
    state = state.copyWith(isCapturing: true, clearError: true);
    try {
      final result = await _sendRpc('tool.mirror.capture', {});
      final b64 = result['screenshot_b64'] as String?;
      final error = result['error'] as String?;
      if (b64 != null) {
        final bytes = await compute(_decodeBase64, b64);
        state = state.copyWith(
          latestScreenshot: bytes,
          lastUpdated: DateTime.now(),
          isCapturing: false,
        );
      } else {
        state = state.copyWith(
          isCapturing: false,
          error: error ?? 'No screenshot returned',
        );
      }
    } catch (e) {
      state = state.copyWith(isCapturing: false, error: 'Capture failed: $e');
    }
  }

  /// Handle event-driven screenshot notification from backend.
  Future<void> onScreenshotNotification(Map<String, dynamic> params) async {
    final b64 = params['screenshot_b64'] as String?;
    if (b64 == null) return;
    try {
      final bytes = await compute(_decodeBase64, b64);
      state = state.copyWith(
        latestScreenshot: bytes,
        lastUpdated: DateTime.now(),
      );
    } catch (_) {
      // Silently skip corrupt frames
    }
  }
}

final toolMirrorProvider =
    StateNotifierProvider<ToolMirrorNotifier, MirrorState>((ref) {
  final rpc = ref.watch(jsonRpcProvider);
  return ToolMirrorNotifier(
    sendRpc: (method, params) => rpc.call(method, params),
  );
});

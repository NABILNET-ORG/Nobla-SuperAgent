import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/tools/providers/tool_mirror_provider.dart';

void main() {
  late ToolMirrorNotifier notifier;

  setUp(() {
    notifier = ToolMirrorNotifier(
      sendRpc: (method, params) async => <String, dynamic>{},
    );
  });

  tearDown(() => notifier.dispose());

  test('starts unsubscribed with no screenshot', () {
    expect(notifier.state.isSubscribed, false);
    expect(notifier.state.latestScreenshot, isNull);
    expect(notifier.state.isCapturing, false);
  });

  test('subscribe sets isSubscribed true', () async {
    await notifier.subscribe();
    expect(notifier.state.isSubscribed, true);
  });

  test('unsubscribe sets isSubscribed false', () async {
    await notifier.subscribe();
    await notifier.unsubscribe();
    expect(notifier.state.isSubscribed, false);
  });

  test('onScreenshotNotification decodes base64 screenshot', () async {
    // Create a tiny 1x1 white PNG as base64
    final pngBytes = Uint8List.fromList([
      0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
    ]);
    final b64 = base64Encode(pngBytes);

    await notifier.onScreenshotNotification({
      'screenshot_b64': b64,
      'timestamp': '2026-03-25T14:30:00Z',
    });

    expect(notifier.state.latestScreenshot, isNotNull);
    expect(notifier.state.latestScreenshot!.length, pngBytes.length);
    expect(notifier.state.lastUpdated, isNotNull);
  });

  test('onScreenshotNotification ignores null screenshot', () async {
    await notifier.onScreenshotNotification({
      'screenshot_b64': null,
      'timestamp': '2026-03-25T14:30:00Z',
    });
    expect(notifier.state.latestScreenshot, isNull);
  });
}

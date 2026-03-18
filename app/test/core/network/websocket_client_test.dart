import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/core/network/websocket_client.dart';

void main() {
  group('WebSocketClient', () {
    late WebSocketClient client;

    setUp(() {
      client = WebSocketClient();
    });

    tearDown(() {
      client.dispose();
    });

    test('initial status is disconnected', () {
      expect(client.currentStatus, ConnectionStatus.disconnected);
    });

    test('connect changes status to connecting then handles failure', () async {
      final statuses = <ConnectionStatus>[];
      client.statusStream.listen(statuses.add);
      await client.connect('ws://localhost:99999/invalid');
      await Future.delayed(const Duration(milliseconds: 100));
      expect(statuses, contains(ConnectionStatus.connecting));
    });

    test('disconnect resets status', () {
      client.disconnect();
      expect(client.currentStatus, ConnectionStatus.disconnected);
    });

    test('messageStream is a broadcast stream', () {
      client.messageStream.listen((_) {});
      client.messageStream.listen((_) {});
    });
  });
}

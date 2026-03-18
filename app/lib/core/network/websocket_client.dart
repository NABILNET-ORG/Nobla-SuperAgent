import 'dart:async';
import 'dart:math';
import 'package:web_socket_channel/web_socket_channel.dart';

enum ConnectionStatus { disconnected, connecting, connected, error }

class WebSocketClient {
  WebSocketChannel? _channel;
  final _statusController = StreamController<ConnectionStatus>.broadcast();
  final _messageController = StreamController<String>.broadcast();
  ConnectionStatus _currentStatus = ConnectionStatus.disconnected;
  String? _url;
  Timer? _reconnectTimer;
  Timer? _heartbeatTimer;
  int _reconnectAttempts = 0;
  bool _disposed = false;

  Stream<ConnectionStatus> get statusStream => _statusController.stream;
  Stream<String> get messageStream => _messageController.stream;
  ConnectionStatus get currentStatus => _currentStatus;

  void _setStatus(ConnectionStatus status) {
    _currentStatus = status;
    if (!_disposed) _statusController.add(status);
  }

  Future<void> connect(String url) async {
    _url = url;
    _reconnectAttempts = 0;
    await _doConnect();
  }

  Future<void> _doConnect() async {
    if (_disposed) return;
    _setStatus(ConnectionStatus.connecting);
    try {
      final uri = Uri.parse(_url!);
      _channel = WebSocketChannel.connect(uri);
      await _channel!.ready;
      _setStatus(ConnectionStatus.connected);
      _reconnectAttempts = 0;
      _startHeartbeat();
      _channel!.stream.listen(
        (data) {
          if (!_disposed) _messageController.add(data as String);
        },
        onDone: _onDisconnected,
        onError: (_) => _onDisconnected(),
      );
    } catch (e) {
      _setStatus(ConnectionStatus.error);
      _scheduleReconnect();
    }
  }

  void _onDisconnected() {
    _stopHeartbeat();
    if (!_disposed && _url != null) {
      _setStatus(ConnectionStatus.disconnected);
      _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    if (_disposed || _url == null) return;
    _reconnectAttempts++;
    final delay = min(pow(2, _reconnectAttempts).toInt(), 30);
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(Duration(seconds: delay), _doConnect);
  }

  void _startHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (_currentStatus == ConnectionStatus.connected) {
        try {
          send('{"jsonrpc":"2.0","method":"system.health","id":0}');
        } catch (_) {
          _onDisconnected();
        }
      }
    });
  }

  void _stopHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
  }

  void send(String message) {
    _channel?.sink.add(message);
  }

  void disconnect() {
    _url = null;
    _reconnectTimer?.cancel();
    _stopHeartbeat();
    _channel?.sink.close();
    _channel = null;
    _setStatus(ConnectionStatus.disconnected);
  }

  void dispose() {
    _disposed = true;
    disconnect();
    _statusController.close();
    _messageController.close();
  }
}

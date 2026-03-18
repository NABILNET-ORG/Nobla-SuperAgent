import 'dart:async';
import 'dart:convert';
import 'package:nobla_agent/core/network/websocket_client.dart';
import 'package:nobla_agent/shared/models/rpc_error.dart';

class JsonRpcClient {
  final WebSocketClient _ws;
  int _nextId = 1;
  final _pendingCalls = <int, Completer<Map<String, dynamic>>>{};
  final _notificationController =
      StreamController<Map<String, dynamic>>.broadcast();
  StreamSubscription? _messageSubscription;

  JsonRpcClient(this._ws) {
    _messageSubscription = _ws.messageStream.listen(_handleMessage);
  }

  Stream<Map<String, dynamic>> get notificationStream =>
      _notificationController.stream;

  Future<Map<String, dynamic>> call(
    String method, [
    Map<String, dynamic> params = const {},
    Duration timeout = const Duration(seconds: 30),
  ]) {
    final id = _nextId++;
    final request = {
      'jsonrpc': '2.0',
      'method': method,
      'params': params,
      'id': id,
    };
    final completer = Completer<Map<String, dynamic>>();
    _pendingCalls[id] = completer;
    _ws.send(jsonEncode(request));
    return completer.future.timeout(timeout, onTimeout: () {
      _pendingCalls.remove(id);
      throw RpcError(code: -32000, message: 'Request timed out');
    });
  }

  void _handleMessage(String raw) {
    try {
      final json = jsonDecode(raw) as Map<String, dynamic>;
      if (json.containsKey('id') && json['id'] != null) {
        final id = json['id'] as int;
        final completer = _pendingCalls.remove(id);
        if (completer == null) return;
        if (json.containsKey('error') && json['error'] != null) {
          completer.completeError(
            RpcError.fromJson(json['error'] as Map<String, dynamic>),
          );
        } else {
          completer.complete(
            json['result'] as Map<String, dynamic>? ?? {},
          );
        }
      } else if (json.containsKey('method')) {
        _notificationController.add(json);
      }
    } catch (e) {
      // Ignore malformed messages
    }
  }

  void dispose() {
    _messageSubscription?.cancel();
    _notificationController.close();
    for (final completer in _pendingCalls.values) {
      completer.completeError(
        RpcError(code: -32000, message: 'Client disposed'),
      );
    }
    _pendingCalls.clear();
  }
}

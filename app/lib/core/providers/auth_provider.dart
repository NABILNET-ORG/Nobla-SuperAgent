import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';

sealed class AuthState {}

class Unauthenticated extends AuthState {}

class Authenticated extends AuthState {
  final String userId;
  final String displayName;
  final int tier;
  final String accessToken;
  final String refreshToken;

  Authenticated({
    required this.userId,
    required this.displayName,
    this.tier = 1,
    required this.accessToken,
    required this.refreshToken,
  });

  Authenticated copyWith({int? tier}) {
    return Authenticated(
      userId: userId,
      displayName: displayName,
      tier: tier ?? this.tier,
      accessToken: accessToken,
      refreshToken: refreshToken,
    );
  }
}

class AuthNotifier extends StateNotifier<AuthState> {
  final JsonRpcClient _rpc;
  AuthNotifier(this._rpc) : super(Unauthenticated());

  Future<void> register(String displayName, String passphrase) async {
    final result = await _rpc.call('system.register', {
      'display_name': displayName,
      'passphrase': passphrase,
    });
    if (result.containsKey('error')) throw Exception(result['error']);
    state = Authenticated(
      userId: result['user_id'] as String,
      displayName: result['display_name'] as String,
      accessToken: result['access_token'] as String,
      refreshToken: result['refresh_token'] as String,
    );
  }

  Future<void> login(String passphrase) async {
    final result = await _rpc.call('system.authenticate', {'passphrase': passphrase});
    if (result['authenticated'] != true) {
      throw Exception(result['message'] ?? 'Authentication failed');
    }
    state = Authenticated(
      userId: result['user_id'] as String,
      displayName: 'User',
      accessToken: result['access_token'] as String? ?? '',
      refreshToken: result['refresh_token'] as String? ?? '',
    );
  }

  Future<void> loginWithToken(String token) async {
    final result = await _rpc.call('system.authenticate', {'token': token});
    if (result['authenticated'] != true) {
      throw Exception(result['message'] ?? 'Token auth failed');
    }
    state = Authenticated(
      userId: result['user_id'] as String,
      displayName: 'User',
      tier: result['tier'] as int? ?? 1,
      accessToken: token,
      refreshToken: '',
    );
  }

  Future<void> refreshToken() async {
    final current = state;
    if (current is! Authenticated) return;
    final result = await _rpc.call('system.refresh', {'refresh_token': current.refreshToken});
    if (result.containsKey('error')) return;
    state = Authenticated(
      userId: current.userId,
      displayName: current.displayName,
      tier: current.tier,
      accessToken: result['access_token'] as String,
      refreshToken: result['refresh_token'] as String,
    );
  }

  Future<void> escalate(int tier, [String? passphrase]) async {
    final params = <String, dynamic>{'tier': tier};
    if (passphrase != null) params['passphrase'] = passphrase;
    final result = await _rpc.call('system.escalate', params);
    if (result.containsKey('error')) throw Exception(result['error']);
    final current = state;
    if (current is Authenticated) {
      state = current.copyWith(tier: result['tier'] as int);
    }
  }

  void logout() {
    state = Unauthenticated();
  }
}

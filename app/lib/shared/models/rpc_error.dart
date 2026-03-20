class RpcError implements Exception {
  final int code;
  final String message;
  final Map<String, dynamic>? data;

  const RpcError({required this.code, required this.message, this.data});

  factory RpcError.fromJson(Map<String, dynamic> json) {
    return RpcError(
      code: json['code'] as int,
      message: json['message'] as String,
      data: json['data'] as Map<String, dynamic>?,
    );
  }

  bool get isAuthRequired => code == -32011;
  bool get isAuthFailed => code == -32012;
  bool get isTokenExpired => code == -32013;
  bool get isPermissionDenied => code == -32010;
  bool get isBudgetExceeded => code == -32020;
  bool get isServerKilled => code == -32030;
  bool get isParseError => code == -32700;
  bool get isMethodNotFound => code == -32601;
  bool get isInternalError => code == -32603;

  @override
  String toString() => 'RpcError($code): $message';
}

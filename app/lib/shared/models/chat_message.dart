import 'package:uuid/uuid.dart';

enum MessageStatus { sending, sent, error }

class ChatMessage {
  final String id;
  final String content;
  final bool isUser;
  final DateTime timestamp;
  final String? model;
  final int? tokensUsed;
  final double? costUsd;
  final MessageStatus status;

  const ChatMessage({
    required this.id,
    required this.content,
    required this.isUser,
    required this.timestamp,
    this.model,
    this.tokensUsed,
    this.costUsd,
    this.status = MessageStatus.sent,
  });

  factory ChatMessage.user(String content) {
    return ChatMessage(
      id: const Uuid().v4(),
      content: content,
      isUser: true,
      timestamp: DateTime.now(),
      status: MessageStatus.sending,
    );
  }

  factory ChatMessage.fromRpcResponse(
    Map<String, dynamic> json, {
    required bool isUser,
  }) {
    return ChatMessage(
      id: const Uuid().v4(),
      content: json['message'] as String,
      isUser: isUser,
      timestamp: DateTime.now(),
      model: json['model'] as String?,
      tokensUsed: json['tokens_used'] as int?,
      costUsd: (json['cost_usd'] as num?)?.toDouble(),
      status: MessageStatus.sent,
    );
  }

  ChatMessage copyWith({MessageStatus? status, String? content}) {
    return ChatMessage(
      id: id,
      content: content ?? this.content,
      isUser: isUser,
      timestamp: timestamp,
      model: model,
      tokensUsed: tokensUsed,
      costUsd: costUsd,
      status: status ?? this.status,
    );
  }
}

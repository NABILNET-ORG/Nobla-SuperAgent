/// Conversation model for conversation list and switching.
class Conversation {
  final String id;
  final String title;
  final String? summary;
  final List<String> topics;
  final int messageCount;
  final String? updatedAt;
  final String? createdAt;

  const Conversation({
    required this.id,
    required this.title,
    this.summary,
    this.topics = const [],
    this.messageCount = 0,
    this.updatedAt,
    this.createdAt,
  });

  factory Conversation.fromJson(Map<String, dynamic> json) {
    return Conversation(
      id: json['id'] as String,
      title: json['title'] as String? ?? 'Untitled',
      summary: json['summary'] as String?,
      topics: (json['topics'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          [],
      messageCount: json['message_count'] as int? ?? 0,
      updatedAt: json['updated_at']?.toString(),
      createdAt: json['created_at']?.toString(),
    );
  }

  Conversation copyWith({String? title, String? summary}) {
    return Conversation(
      id: id,
      title: title ?? this.title,
      summary: summary ?? this.summary,
      topics: topics,
      messageCount: messageCount,
      updatedAt: updatedAt,
      createdAt: createdAt,
    );
  }
}

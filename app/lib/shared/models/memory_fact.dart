/// A fact extracted from conversations and stored in semantic memory.
class MemoryFact {
  final String id;
  final String content;
  final String noteType;
  final double? confidence;
  final List<String> keywords;
  final String? createdAt;

  const MemoryFact({
    required this.id,
    required this.content,
    this.noteType = 'fact',
    this.confidence,
    this.keywords = const [],
    this.createdAt,
  });

  factory MemoryFact.fromJson(Map<String, dynamic> json) {
    return MemoryFact(
      id: json['id'] as String,
      content: json['content'] as String,
      noteType: json['note_type'] as String? ?? 'fact',
      confidence: (json['confidence'] as num?)?.toDouble(),
      keywords: (json['keywords'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          [],
      createdAt: json['created_at']?.toString(),
    );
  }
}

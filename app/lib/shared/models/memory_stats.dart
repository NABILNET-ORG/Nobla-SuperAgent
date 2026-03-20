/// Memory system statistics for the dashboard.
class MemoryStats {
  final int totalMemories;
  final Map<String, int> byType;
  final int totalLinks;
  final int graphEntities;
  final int graphRelationships;

  const MemoryStats({
    this.totalMemories = 0,
    this.byType = const {},
    this.totalLinks = 0,
    this.graphEntities = 0,
    this.graphRelationships = 0,
  });

  factory MemoryStats.fromJson(Map<String, dynamic> json) {
    final byTypeRaw = json['by_type'] as Map<String, dynamic>? ?? {};
    return MemoryStats(
      totalMemories: json['total_memories'] as int? ?? 0,
      byType: byTypeRaw.map((k, v) => MapEntry(k, v as int)),
      totalLinks: json['total_links'] as int? ?? 0,
      graphEntities: json['graph_entities'] as int? ?? 0,
      graphRelationships: json['graph_relationships'] as int? ?? 0,
    );
  }
}

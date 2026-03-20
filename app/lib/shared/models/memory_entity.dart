/// An entity in the knowledge graph.
class MemoryEntity {
  final String name;
  final String entityType;
  final int neighborCount;

  const MemoryEntity({
    required this.name,
    this.entityType = 'UNKNOWN',
    this.neighborCount = 0,
  });

  factory MemoryEntity.fromJson(Map<String, dynamic> json) {
    return MemoryEntity(
      name: json['name'] as String,
      entityType: json['entity_type'] as String? ?? 'UNKNOWN',
      neighborCount: json['neighbors'] as int? ?? 0,
    );
  }
}

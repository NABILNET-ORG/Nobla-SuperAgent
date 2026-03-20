import 'package:flutter/material.dart';
import '../../../shared/models/memory_entity.dart';

/// Card displaying a single knowledge graph entity.
class EntityCard extends StatelessWidget {
  final MemoryEntity entity;

  const EntityCard({super.key, required this.entity});

  IconData _iconForType(String type) {
    return switch (type) {
      'PERSON' => Icons.person,
      'ORGANIZATION' => Icons.business,
      'LOCATION' => Icons.place,
      'TOOL' => Icons.build,
      'DATE' => Icons.calendar_today,
      _ => Icons.circle_outlined,
    };
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: theme.colorScheme.tertiaryContainer,
          child: Icon(
            _iconForType(entity.entityType),
            color: theme.colorScheme.onTertiaryContainer,
            size: 20,
          ),
        ),
        title: Text(entity.name),
        subtitle: Text(entity.entityType),
        trailing: entity.neighborCount > 0
            ? Chip(
                label: Text('${entity.neighborCount}'),
                avatar: const Icon(Icons.link, size: 16),
                visualDensity: VisualDensity.compact,
              )
            : null,
      ),
    );
  }
}

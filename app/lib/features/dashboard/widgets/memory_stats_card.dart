import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../memory/providers/memory_provider.dart';

/// Dashboard card showing memory system statistics.
class MemoryStatsCard extends ConsumerStatefulWidget {
  const MemoryStatsCard({super.key});

  @override
  ConsumerState<MemoryStatsCard> createState() => _MemoryStatsCardState();
}

class _MemoryStatsCardState extends ConsumerState<MemoryStatsCard> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() {
      ref.read(memoryViewerProvider.notifier).loadStats();
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(memoryViewerProvider);
    final stats = state.stats;
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.memory, color: theme.colorScheme.primary),
                const SizedBox(width: 8),
                Text(
                  'Memory',
                  style: theme.textTheme.titleMedium,
                ),
              ],
            ),
            const Divider(),
            if (state.isLoading)
              const Center(child: CircularProgressIndicator())
            else ...[
              _StatRow(
                label: 'Total Memories',
                value: '${stats.totalMemories}',
              ),
              _StatRow(
                label: 'Graph Entities',
                value: '${stats.graphEntities}',
              ),
              _StatRow(
                label: 'Relationships',
                value: '${stats.graphRelationships}',
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _StatRow extends StatelessWidget {
  final String label;
  final String value;

  const _StatRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label),
          Text(
            value,
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
        ],
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/memory_provider.dart';
import '../widgets/fact_card.dart';
import '../widgets/entity_card.dart';

/// Memory viewer with tabs for facts, entities, and procedures.
class MemoryViewerScreen extends ConsumerStatefulWidget {
  const MemoryViewerScreen({super.key});

  @override
  ConsumerState<MemoryViewerScreen> createState() => _MemoryViewerScreenState();
}

class _MemoryViewerScreenState extends ConsumerState<MemoryViewerScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
    Future.microtask(() {
      ref.read(memoryViewerProvider.notifier).loadStats();
      ref.read(memoryViewerProvider.notifier).loadFacts();
    });
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(memoryViewerProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Memory'),
        bottom: TabBar(
          controller: _tabController,
          onTap: _onTabChanged,
          tabs: const [
            Tab(icon: Icon(Icons.lightbulb_outline), text: 'Facts'),
            Tab(icon: Icon(Icons.hub_outlined), text: 'Entities'),
            Tab(icon: Icon(Icons.info_outline), text: 'Stats'),
          ],
        ),
      ),
      body: state.isLoading
          ? const Center(child: CircularProgressIndicator())
          : TabBarView(
              controller: _tabController,
              children: [
                _buildFactsTab(state),
                _buildEntitiesTab(state),
                _buildStatsTab(state),
              ],
            ),
    );
  }

  void _onTabChanged(int index) {
    final notifier = ref.read(memoryViewerProvider.notifier);
    switch (index) {
      case 0:
        notifier.loadFacts();
      case 1:
        notifier.loadGraph();
      case 2:
        notifier.loadStats();
    }
  }

  Widget _buildFactsTab(MemoryViewerState state) {
    if (state.facts.isEmpty) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.lightbulb_outline, size: 48, color: Colors.grey),
            SizedBox(height: 16),
            Text('No facts stored yet'),
            Text(
              'Chat with Nobla and facts will be extracted automatically',
              style: TextStyle(color: Colors.grey),
            ),
          ],
        ),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: state.facts.length,
      itemBuilder: (context, index) => FactCard(fact: state.facts[index]),
    );
  }

  Widget _buildEntitiesTab(MemoryViewerState state) {
    if (state.entities.isEmpty) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.hub_outlined, size: 48, color: Colors.grey),
            SizedBox(height: 16),
            Text('No entities in knowledge graph'),
          ],
        ),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: state.entities.length,
      itemBuilder: (context, index) =>
          EntityCard(entity: state.entities[index]),
    );
  }

  Widget _buildStatsTab(MemoryViewerState state) {
    final stats = state.stats;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _StatTile(
          icon: Icons.memory,
          label: 'Total Memories',
          value: '${stats.totalMemories}',
        ),
        _StatTile(
          icon: Icons.hub,
          label: 'Graph Entities',
          value: '${stats.graphEntities}',
        ),
        _StatTile(
          icon: Icons.link,
          label: 'Graph Relationships',
          value: '${stats.graphRelationships}',
        ),
        _StatTile(
          icon: Icons.connect_without_contact,
          label: 'Total Links',
          value: '${stats.totalLinks}',
        ),
        const SizedBox(height: 16),
        if (stats.byType.isNotEmpty) ...[
          Text(
            'By Type',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          ...stats.byType.entries.map(
            (e) => _StatTile(
              icon: Icons.label_outline,
              label: e.key,
              value: '${e.value}',
            ),
          ),
        ],
      ],
    );
  }
}

class _StatTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;

  const _StatTile({
    required this.icon,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(icon),
      title: Text(label),
      trailing: Text(
        value,
        style: Theme.of(context).textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.bold,
            ),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/tools/providers/tool_mirror_provider.dart';
import 'package:nobla_agent/features/tools/widgets/mirror_view.dart';
import 'package:nobla_agent/features/tools/widgets/activity_list.dart';
import 'package:nobla_agent/features/tools/providers/tool_catalog_provider.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/features/tools/widgets/tool_category_section.dart';
import 'package:shimmer/shimmer.dart';

class ToolsScreen extends ConsumerStatefulWidget {
  const ToolsScreen({super.key});

  @override
  ConsumerState<ToolsScreen> createState() => _ToolsScreenState();
}

class _ToolsScreenState extends ConsumerState<ToolsScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
    _tabController.addListener(_onTabChanged);
  }

  void _onTabChanged() {
    if (_tabController.indexIsChanging) return;
    final mirror = ref.read(toolMirrorProvider.notifier);
    if (_tabController.index == 0) {
      mirror.subscribe();
    } else {
      mirror.unsubscribe();
    }
  }

  @override
  void dispose() {
    _tabController.removeListener(_onTabChanged);
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Tools'),
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(icon: Icon(Icons.screenshot_monitor), text: 'Mirror'),
            Tab(icon: Icon(Icons.history), text: 'Activity'),
            Tab(icon: Icon(Icons.widgets_outlined), text: 'Browse'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: const [
          MirrorView(),
          ActivityListTab(),
          _BrowseTab(),
        ],
      ),
    );
  }
}

class _BrowseTab extends ConsumerWidget {
  const _BrowseTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final catalogAsync = ref.watch(toolCatalogProvider);

    return catalogAsync.when(
      loading: () => _ShimmerLoading(),
      error: (err, _) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 48),
            const SizedBox(height: 12),
            const Text("Couldn't load tools"),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: () => ref.invalidate(toolCatalogProvider),
              child: const Text('Retry'),
            ),
          ],
        ),
      ),
      data: (tools) {
        // Group by category
        final grouped = <ToolCategory, List<ToolManifestEntry>>{};
        for (final t in tools) {
          if (t.category != null) {
            grouped.putIfAbsent(t.category!, () => []).add(t);
          }
        }
        // Sort categories in defined order
        final sortedCats = ToolCategory.values
            .where((c) => grouped.containsKey(c))
            .toList();

        if (sortedCats.isEmpty) {
          return const Center(child: Text('No tools available'));
        }

        return RefreshIndicator(
          onRefresh: () async => ref.invalidate(toolCatalogProvider),
          child: ListView.builder(
            itemCount: sortedCats.length,
            itemBuilder: (context, index) {
              final cat = sortedCats[index];
              return ToolCategorySection(
                category: cat,
                tools: grouped[cat]!,
                initiallyExpanded: sortedCats.length <= 3,
              );
            },
          ),
        );
      },
    );
  }
}

class _ShimmerLoading extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Shimmer.fromColors(
      baseColor: Theme.of(context).colorScheme.surfaceContainerHighest,
      highlightColor: Theme.of(context).colorScheme.surface,
      child: ListView.builder(
        itemCount: 5,
        padding: const EdgeInsets.all(16),
        itemBuilder: (_, __) => Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Container(
            height: 60,
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(8),
            ),
          ),
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../models/marketplace_models.dart';
import '../providers/marketplace_providers.dart';
import '../widgets/skill_card.dart';

class MarketplaceScreen extends ConsumerStatefulWidget {
  const MarketplaceScreen({super.key});

  @override
  ConsumerState<MarketplaceScreen> createState() => _MarketplaceScreenState();
}

class _MarketplaceScreenState extends ConsumerState<MarketplaceScreen> {
  final _searchController = TextEditingController();

  static const _categories = [
    'All', 'productivity', 'utilities', 'code', 'communication',
    'automation', 'research', 'media', 'finance',
  ];

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final selectedCategory = ref.watch(marketplaceCategoryProvider);
    final searchAsync = ref.watch(marketplaceSearchProvider);
    final recsAsync = ref.watch(recommendationsProvider);
    final query = ref.watch(marketplaceQueryProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Skills Marketplace')),
      body: Column(
        children: [
          // Search bar
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: TextField(
              controller: _searchController,
              decoration: InputDecoration(
                hintText: 'Search skills...',
                prefixIcon: const Icon(Icons.search),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                contentPadding: const EdgeInsets.symmetric(horizontal: 16),
              ),
              onSubmitted: (v) =>
                  ref.read(marketplaceQueryProvider.notifier).state = v,
            ),
          ),
          // Category filter chips
          SizedBox(
            height: 48,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              itemCount: _categories.length,
              separatorBuilder: (_, __) => const SizedBox(width: 8),
              itemBuilder: (context, index) {
                final cat = _categories[index];
                final selected =
                    (cat == 'All' && selectedCategory == null) ||
                        cat == selectedCategory;
                return FilterChip(
                  label: Text(cat),
                  selected: selected,
                  onSelected: (_) {
                    ref.read(marketplaceCategoryProvider.notifier).state =
                        cat == 'All' ? null : cat;
                  },
                );
              },
            ),
          ),
          // Content
          Expanded(
            child: searchAsync.when(
              data: (results) {
                if (results.items.isEmpty) {
                  return const Center(child: Text('No skills found'));
                }
                return CustomScrollView(
                  slivers: [
                    if (query.isEmpty) ...[
                      ...recsAsync.when(
                        data: (recs) => _buildRecommendationSections(recs),
                        loading: () => [const SliverToBoxAdapter()],
                        error: (_, __) => [const SliverToBoxAdapter()],
                      ),
                    ],
                    SliverPadding(
                      padding: const EdgeInsets.all(16),
                      sliver: SliverGrid(
                        gridDelegate:
                            const SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: 2,
                          childAspectRatio: 0.72,
                          crossAxisSpacing: 12,
                          mainAxisSpacing: 12,
                        ),
                        delegate: SliverChildBuilderDelegate(
                          (context, index) {
                            final skill = results.items[index];
                            return SkillCard(
                              skill: skill,
                              onTap: () => context.go(
                                '/home/tools/marketplace/${skill.id}',
                              ),
                            );
                          },
                          childCount: results.items.length,
                        ),
                      ),
                    ),
                  ],
                );
              },
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text('Error: $e')),
            ),
          ),
        ],
      ),
    );
  }

  List<Widget> _buildRecommendationSections(
      Map<String, List<MarketplaceSkill>> recs) {
    final sections = <Widget>[];
    for (final entry in recs.entries) {
      if (entry.value.isEmpty) continue;
      final title = entry.key == 'based_on_patterns'
          ? 'Based on your patterns'
          : 'Similar to installed';
      sections.add(SliverToBoxAdapter(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
          child: Text(title,
              style: Theme.of(context).textTheme.titleSmall),
        ),
      ));
      sections.add(SliverToBoxAdapter(
        child: SizedBox(
          height: 200,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            itemCount: entry.value.length,
            separatorBuilder: (_, __) => const SizedBox(width: 12),
            itemBuilder: (context, index) {
              final skill = entry.value[index];
              return SizedBox(
                width: 160,
                child: SkillCard(
                  skill: skill,
                  onTap: () => context.go(
                    '/home/tools/marketplace/${skill.id}',
                  ),
                ),
              );
            },
          ),
        ),
      ));
    }
    return sections;
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/marketplace_models.dart';
import '../providers/marketplace_providers.dart';
import '../widgets/rating_widget.dart';
import '../widgets/version_list_widget.dart';

class SkillDetailScreen extends ConsumerWidget {
  final String skillId;

  const SkillDetailScreen({super.key, required this.skillId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final skillAsync = ref.watch(skillDetailProvider(skillId));
    final ratingsAsync = ref.watch(skillRatingsProvider(skillId));
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Skill Details')),
      body: skillAsync.when(
        data: (skill) {
          if (skill == null) {
            return const Center(child: Text('Skill not found'));
          }
          return SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Header
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(skill.displayName,
                              style: theme.textTheme.headlineSmall),
                          const SizedBox(height: 4),
                          Text('by ${skill.authorName}',
                              style: theme.textTheme.bodyMedium),
                        ],
                      ),
                    ),
                    _buildTrustBadge(skill.trustTier),
                  ],
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 6,
                  children: [
                    Chip(label: Text(skill.category)),
                    Text('v${skill.currentVersion}',
                        style: theme.textTheme.bodySmall),
                  ],
                ),
                const SizedBox(height: 12),
                // Install button
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: () {},
                    icon: const Icon(Icons.download),
                    label: const Text('Install'),
                  ),
                ),
                const SizedBox(height: 16),
                // Description
                Text(skill.description, style: theme.textTheme.bodyMedium),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 6,
                  children: skill.tags
                      .map((t) => Chip(
                            label: Text(t, style: const TextStyle(fontSize: 12)),
                            visualDensity: VisualDensity.compact,
                          ))
                      .toList(),
                ),
                const SizedBox(height: 16),
                // Stats row
                Row(
                  children: [
                    _statCard(Icons.download, '${skill.installCount}', 'Installs'),
                    _statCard(Icons.person, '${skill.activeUsers}', 'Active'),
                    _statCard(Icons.star, skill.avgRating.toStringAsFixed(1), 'Rating'),
                    _statCard(Icons.check_circle,
                        '${(skill.successRate * 100).toStringAsFixed(0)}%', 'Success'),
                  ],
                ),
                const SizedBox(height: 24),
                // Versions
                Text('Versions', style: theme.textTheme.titleMedium),
                VersionListWidget(versions: skill.versions),
                const SizedBox(height: 24),
                // Ratings
                Text('Ratings', style: theme.textTheme.titleMedium),
                const SizedBox(height: 8),
                RatingWidget(currentRating: skill.avgRating),
                const SizedBox(height: 12),
                ratingsAsync.when(
                  data: (ratings) {
                    if (ratings.isEmpty) {
                      return const Text('No reviews yet.');
                    }
                    return Column(
                      children: ratings
                          .map((r) => ListTile(
                                leading: Icon(Icons.star,
                                    color: Colors.amber.shade700),
                                title: Text('${r.stars}/5'),
                                subtitle: r.review != null
                                    ? Text(r.review!)
                                    : null,
                              ))
                          .toList(),
                    );
                  },
                  loading: () =>
                      const Center(child: CircularProgressIndicator()),
                  error: (e, _) => Text('Error loading ratings: $e'),
                ),
              ],
            ),
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
      ),
    );
  }

  Widget _statCard(IconData icon, String value, String label) {
    return Expanded(
      child: Card(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Column(
            children: [
              Icon(icon, size: 20),
              const SizedBox(height: 4),
              Text(value, style: const TextStyle(fontWeight: FontWeight.bold)),
              Text(label, style: const TextStyle(fontSize: 11)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTrustBadge(TrustTier tier) {
    final (label, color) = switch (tier) {
      TrustTier.verified => ('Verified', Colors.green),
      TrustTier.official => ('Official', Colors.blue),
      TrustTier.community => ('Community', Colors.grey),
    };
    return Chip(
      label: Text(label),
      backgroundColor: color.withValues(alpha: 0.15),
      labelStyle: TextStyle(color: color.shade700, fontSize: 12),
    );
  }
}

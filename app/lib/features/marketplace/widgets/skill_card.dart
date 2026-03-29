import 'package:flutter/material.dart';
import '../models/marketplace_models.dart';

class SkillCard extends StatelessWidget {
  final MarketplaceSkill skill;
  final bool isInstalled;
  final VoidCallback? onInstall;
  final VoidCallback? onTap;

  const SkillCard({
    super.key,
    required this.skill,
    this.isInstalled = false,
    this.onInstall,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      skill.displayName,
                      style: theme.textTheme.titleSmall,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  _buildTrustBadge(theme),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                skill.authorName,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                skill.description,
                style: theme.textTheme.bodySmall,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              const Spacer(),
              Row(
                children: [
                  Icon(Icons.star, size: 14, color: Colors.amber.shade700),
                  const SizedBox(width: 2),
                  Text(
                    skill.avgRating.toStringAsFixed(1),
                    style: theme.textTheme.bodySmall,
                  ),
                  const SizedBox(width: 8),
                  Icon(Icons.download, size: 14,
                      color: theme.colorScheme.onSurfaceVariant),
                  const SizedBox(width: 2),
                  Text(
                    '${skill.installCount}',
                    style: theme.textTheme.bodySmall,
                  ),
                ],
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: isInstalled
                    ? OutlinedButton(
                        onPressed: null,
                        child: const Text('Installed'),
                      )
                    : FilledButton(
                        onPressed: onInstall,
                        child: const Text('Install'),
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTrustBadge(ThemeData theme) {
    final (label, color) = switch (skill.trustTier) {
      TrustTier.verified => ('Verified', Colors.green),
      TrustTier.official => ('Official', Colors.blue),
      TrustTier.community => ('Community', Colors.grey),
    };
    return Chip(
      label: Text(label, style: const TextStyle(fontSize: 10)),
      backgroundColor: color.withValues(alpha: 0.15),
      labelStyle: TextStyle(color: color.shade700),
      visualDensity: VisualDensity.compact,
      padding: EdgeInsets.zero,
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/features/tools/providers/filtered_activity_provider.dart';
import 'package:nobla_agent/features/tools/widgets/tool_category_section.dart';
import 'package:nobla_agent/shared/providers/tool_activity_provider.dart';

/// Horizontal filter chip bar for the activity feed.
class ActivityFilterBar extends ConsumerWidget {
  const ActivityFilterBar({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filter = ref.watch(activityFilterProvider);
    final entries = ref.watch(toolActivityProvider);

    // Only show categories that have entries.
    final activeCategories = <ToolCategory>{};
    for (final e in entries) {
      if (e.category != null) activeCategories.add(e.category!);
    }

    return SizedBox(
      height: 48,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        children: [
          // Category chips (outlined)
          for (final cat in ToolCategory.values)
            if (activeCategories.contains(cat))
              Padding(
                padding: const EdgeInsets.only(right: 6),
                child: FilterChip(
                  label: Text(cat.label),
                  avatar: Icon(categoryStyle(cat).$1,
                      size: 16, color: categoryStyle(cat).$2),
                  selected: filter.categories?.contains(cat) ?? false,
                  onSelected: (selected) {
                    final current = {...?filter.categories};
                    selected ? current.add(cat) : current.remove(cat);
                    ref.read(activityFilterProvider.notifier).state =
                        filter.copyWith(
                      categories: current.isEmpty ? null : current,
                      clearCategories: current.isEmpty,
                    );
                  },
                ),
              ),

          // Gap
          if (activeCategories.isNotEmpty) const SizedBox(width: 10),

          // Status chips (tonal)
          for (final status in ActivityStatus.values)
            Padding(
              padding: const EdgeInsets.only(right: 6),
              child: FilterChip(
                label: Text(status.name),
                selected: filter.statuses?.contains(status) ?? false,
                selectedColor:
                    Theme.of(context).colorScheme.secondaryContainer,
                onSelected: (selected) {
                  final current = {...?filter.statuses};
                  selected ? current.add(status) : current.remove(status);
                  ref.read(activityFilterProvider.notifier).state =
                      filter.copyWith(
                    statuses: current.isEmpty ? null : current,
                    clearStatuses: current.isEmpty,
                  );
                },
              ),
            ),

          // Clear all button
          if (filter.isActive)
            Center(
              child: TextButton(
                onPressed: () {
                  ref.read(activityFilterProvider.notifier).state =
                      const ActivityFilter();
                },
                child: const Text('Clear all'),
              ),
            ),
        ],
      ),
    );
  }
}

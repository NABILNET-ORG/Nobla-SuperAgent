import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/automation/models/template_models.dart';
import 'package:nobla_agent/features/automation/providers/template_providers.dart';

/// Browse and instantiate workflow templates.
class TemplateGalleryScreen extends ConsumerStatefulWidget {
  const TemplateGalleryScreen({super.key});

  @override
  ConsumerState<TemplateGalleryScreen> createState() =>
      _TemplateGalleryScreenState();
}

class _TemplateGalleryScreenState
    extends ConsumerState<TemplateGalleryScreen> {
  TemplateCategory? _selectedCategory;
  String _searchQuery = '';

  TemplateFilter get _filter => TemplateFilter(
        query: _searchQuery,
        category: _selectedCategory,
      );

  @override
  Widget build(BuildContext context) {
    final templatesAsync = ref.watch(templateListProvider(_filter));
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        key: const ValueKey('gallery_appbar'),
        title: const Text('Template Gallery'),
      ),
      body: Column(
        children: [
          // Search bar
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
            child: TextField(
              key: const ValueKey('search_field'),
              decoration: InputDecoration(
                hintText: 'Search templates...',
                prefixIcon: const Icon(Icons.search),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                isDense: true,
              ),
              onChanged: (v) => setState(() => _searchQuery = v),
            ),
          ),
          // Category chips
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            child: Row(
              children: [
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: FilterChip(
                    key: const ValueKey('cat_all'),
                    label: const Text('All'),
                    selected: _selectedCategory == null,
                    onSelected: (_) =>
                        setState(() => _selectedCategory = null),
                  ),
                ),
                ...TemplateCategory.values.map((cat) {
                  return Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: FilterChip(
                      key: ValueKey('cat_${cat.value}'),
                      label: Text(cat.label),
                      selected: _selectedCategory == cat,
                      onSelected: (_) =>
                          setState(() => _selectedCategory = cat),
                    ),
                  );
                }),
              ],
            ),
          ),
          // Template grid
          Expanded(
            child: templatesAsync.when(
              loading: () => const Center(
                child: CircularProgressIndicator(key: ValueKey('loading')),
              ),
              error: (e, _) => Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.error_outline,
                        size: 48, color: theme.colorScheme.error),
                    const SizedBox(height: 8),
                    Text('Failed to load templates',
                        style: theme.textTheme.bodyLarge),
                    const SizedBox(height: 8),
                    FilledButton.tonal(
                      key: const ValueKey('retry_btn'),
                      onPressed: () => ref.invalidate(
                          templateListProvider(_filter)),
                      child: const Text('Retry'),
                    ),
                  ],
                ),
              ),
              data: (templates) {
                if (templates.isEmpty) {
                  return const Center(
                    key: ValueKey('empty_state'),
                    child: Text('No templates found'),
                  );
                }
                return RefreshIndicator(
                  onRefresh: () async =>
                      ref.invalidate(templateListProvider(_filter)),
                  child: ListView.builder(
                    key: const ValueKey('template_list'),
                    padding: const EdgeInsets.all(12),
                    itemCount: templates.length,
                    itemBuilder: (ctx, i) =>
                        _TemplateCard(template: templates[i]),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

/// Card displaying a single template with use button.
class _TemplateCard extends ConsumerWidget {
  final WorkflowTemplate template;

  const _TemplateCard({required this.template});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final cat = template.category;

    return Card(
      key: ValueKey('tmpl_${template.templateId}'),
      margin: const EdgeInsets.only(bottom: 12),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () => _showDetail(context, ref),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(cat.icon, style: const TextStyle(fontSize: 24)),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(template.name,
                            style: theme.textTheme.titleMedium),
                        Text(cat.label,
                            style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.outline)),
                      ],
                    ),
                  ),
                  if (template.bundled)
                    Chip(
                      label: const Text('Built-in'),
                      labelStyle: theme.textTheme.labelSmall,
                      visualDensity: VisualDensity.compact,
                    ),
                ],
              ),
              if (template.description.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(template.description,
                    style: theme.textTheme.bodyMedium,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis),
              ],
              const SizedBox(height: 8),
              Row(
                children: [
                  _InfoChip(
                    icon: Icons.account_tree_outlined,
                    label: '${template.stepCount} steps',
                  ),
                  const SizedBox(width: 8),
                  _InfoChip(
                    icon: Icons.bolt,
                    label: '${template.triggerCount} triggers',
                  ),
                  const Spacer(),
                  FilledButton.tonal(
                    key: ValueKey('use_${template.templateId}'),
                    onPressed: () => _showInstantiateDialog(context, ref),
                    child: const Text('Use'),
                  ),
                ],
              ),
              if (template.tags.isNotEmpty) ...[
                const SizedBox(height: 8),
                Wrap(
                  spacing: 4,
                  runSpacing: 4,
                  children: template.tags.map((tag) {
                    return Chip(
                      label: Text(tag),
                      labelStyle: theme.textTheme.labelSmall,
                      visualDensity: VisualDensity.compact,
                      padding: EdgeInsets.zero,
                    );
                  }).toList(),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  void _showDetail(BuildContext context, WidgetRef ref) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.6,
        maxChildSize: 0.9,
        builder: (ctx, controller) => TemplateDetailSheet(
          templateId: template.templateId,
          scrollController: controller,
        ),
      ),
    );
  }

  void _showInstantiateDialog(BuildContext context, WidgetRef ref) {
    final nameController = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        key: const ValueKey('instantiate_dialog'),
        title: Text('Use "${template.name}"'),
        content: TextField(
          key: const ValueKey('name_input'),
          controller: nameController,
          decoration: const InputDecoration(
            labelText: 'Workflow name (optional)',
            hintText: 'Leave blank to use template name',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const ValueKey('confirm_instantiate'),
            onPressed: () {
              Navigator.pop(ctx);
              ref.read(templateOperationsProvider.notifier).instantiate(
                    template.templateId,
                    name: nameController.text.isEmpty
                        ? null
                        : nameController.text,
                  );
            },
            child: const Text('Create'),
          ),
        ],
      ),
    );
  }
}

/// Bottom sheet showing full template detail.
class TemplateDetailSheet extends ConsumerWidget {
  final String templateId;
  final ScrollController scrollController;

  const TemplateDetailSheet({
    super.key,
    required this.templateId,
    required this.scrollController,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detailAsync = ref.watch(templateDetailProvider(templateId));
    final theme = Theme.of(context);

    return detailAsync.when(
      loading: () =>
          const Center(child: CircularProgressIndicator(key: ValueKey('detail_loading'))),
      error: (e, _) => Center(child: Text('Error: $e')),
      data: (detail) => ListView(
        controller: scrollController,
        padding: const EdgeInsets.all(16),
        children: [
          // Header
          Text(detail.name, style: theme.textTheme.headlineSmall),
          const SizedBox(height: 4),
          Text('by ${detail.author} · v${detail.version}',
              style: theme.textTheme.bodySmall),
          const SizedBox(height: 12),
          Text(detail.description, style: theme.textTheme.bodyMedium),
          const SizedBox(height: 16),
          // Steps
          Text('Steps', style: theme.textTheme.titleSmall),
          const SizedBox(height: 8),
          ...detail.steps.map((s) => ListTile(
                key: ValueKey('step_${s.refId}'),
                leading: Icon(_stepTypeIcon(s.type)),
                title: Text(s.name),
                subtitle: s.description.isNotEmpty ? Text(s.description) : null,
                dense: true,
              )),
          const SizedBox(height: 16),
          // Triggers
          Text('Triggers', style: theme.textTheme.titleSmall),
          const SizedBox(height: 8),
          ...detail.triggers.map((t) => ListTile(
                key: ValueKey('trigger_${t.eventPattern}'),
                leading: const Icon(Icons.bolt),
                title: Text(t.eventPattern),
                subtitle:
                    t.description.isNotEmpty ? Text(t.description) : null,
                dense: true,
              )),
        ],
      ),
    );
  }

  IconData _stepTypeIcon(String type) => switch (type) {
        'tool' => Icons.build,
        'agent' => Icons.smart_toy,
        'condition' => Icons.call_split,
        'webhook' => Icons.webhook,
        'delay' => Icons.timer,
        'approval' => Icons.check_circle,
        _ => Icons.extension,
      };
}

/// Small info chip for step/trigger counts.
class _InfoChip extends StatelessWidget {
  final IconData icon;
  final String label;

  const _InfoChip({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 14, color: theme.colorScheme.outline),
        const SizedBox(width: 4),
        Text(label, style: theme.textTheme.labelSmall),
      ],
    );
  }
}

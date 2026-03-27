import 'package:flutter/material.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/features/tools/widgets/tool_card.dart';

/// Category icon and color mapping.
const _categoryStyles = <ToolCategory, (IconData, Color)>{
  ToolCategory.vision: (Icons.visibility, Colors.purple),
  ToolCategory.input: (Icons.mouse, Colors.indigo),
  ToolCategory.fileSystem: (Icons.folder, Colors.amber),
  ToolCategory.appControl: (Icons.apps, Colors.teal),
  ToolCategory.code: (Icons.code, Colors.cyan),
  ToolCategory.git: (Icons.merge_type, Colors.deepOrange),
  ToolCategory.ssh: (Icons.terminal, Colors.blue),
  ToolCategory.clipboard: (Icons.content_paste, Colors.pink),
  ToolCategory.search: (Icons.search, Colors.green),
};

/// Icon for a [ToolCategory], using consistent colors.
(IconData, Color) categoryStyle(ToolCategory cat) =>
    _categoryStyles[cat] ?? (Icons.build, Colors.grey);

/// Collapsible section showing tools in a single category.
class ToolCategorySection extends StatefulWidget {
  final ToolCategory category;
  final List<ToolManifestEntry> tools;
  final bool initiallyExpanded;

  const ToolCategorySection({
    super.key,
    required this.category,
    required this.tools,
    this.initiallyExpanded = true,
  });

  @override
  State<ToolCategorySection> createState() => _ToolCategorySectionState();
}

class _ToolCategorySectionState extends State<ToolCategorySection> {
  late bool _expanded;

  @override
  void initState() {
    super.initState();
    _expanded = widget.initiallyExpanded;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final (icon, color) = categoryStyle(widget.category);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: () => setState(() => _expanded = !_expanded),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              children: [
                Icon(icon, color: color, size: 20),
                const SizedBox(width: 8),
                Text(
                  widget.category.label,
                  style: theme.textTheme.titleSmall
                      ?.copyWith(fontWeight: FontWeight.w600),
                ),
                const SizedBox(width: 8),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(
                    '${widget.tools.length}',
                    style: theme.textTheme.labelSmall,
                  ),
                ),
                const Spacer(),
                Icon(
                  _expanded ? Icons.expand_less : Icons.expand_more,
                  size: 20,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ],
            ),
          ),
        ),
        if (_expanded)
          ...widget.tools.map((t) => ToolCard(tool: t)),
      ],
    );
  }
}

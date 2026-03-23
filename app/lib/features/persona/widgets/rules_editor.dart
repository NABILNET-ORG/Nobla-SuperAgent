import 'package:flutter/material.dart';

class RulesEditor extends StatelessWidget {
  final List<String> rules;
  final ValueChanged<List<String>> onChanged;
  final int maxRules;
  final int maxRuleLength;

  const RulesEditor({
    super.key,
    required this.rules,
    required this.onChanged,
    this.maxRules = 20,
    this.maxRuleLength = 500,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Rules', style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 4,
          children: [
            for (int i = 0; i < rules.length; i++)
              InputChip(
                label: Text(
                  rules[i],
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                onDeleted: () {
                  final updated = List<String>.from(rules)..removeAt(i);
                  onChanged(updated);
                },
              ),
            if (rules.length < maxRules)
              ActionChip(
                avatar: const Icon(Icons.add, size: 18),
                label: const Text('Add rule'),
                onPressed: () => _showAddDialog(context),
              ),
          ],
        ),
      ],
    );
  }

  void _showAddDialog(BuildContext context) {
    final controller = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Add Rule'),
        content: TextField(
          controller: controller,
          maxLength: maxRuleLength,
          decoration: const InputDecoration(hintText: 'Enter a rule...'),
          autofocus: true,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () {
              final text = controller.text.trim();
              if (text.isNotEmpty) {
                onChanged([...rules, text]);
              }
              Navigator.pop(ctx);
            },
            child: const Text('Add'),
          ),
        ],
      ),
    );
  }
}

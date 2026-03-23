import 'package:flutter/material.dart';

class CostCard extends StatelessWidget {
  final Map<String, dynamic> costData;
  const CostCard({super.key, required this.costData});

  @override
  Widget build(BuildContext context) {
    final limits = costData['limits'] as Map<String, dynamic>? ?? {};
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.attach_money),
                const SizedBox(width: 8),
                Text('Cost Tracking',
                    style: Theme.of(context).textTheme.titleMedium),
              ],
            ),
            const Divider(),
            _buildBar(
              context,
              'Session',
              (costData['session_usd'] as num?)?.toDouble() ?? 0,
              (limits['session'] as num?)?.toDouble() ?? 1,
            ),
            const SizedBox(height: 8),
            _buildBar(
              context,
              'Daily',
              (costData['daily_usd'] as num?)?.toDouble() ?? 0,
              (limits['daily'] as num?)?.toDouble() ?? 5,
            ),
            const SizedBox(height: 8),
            _buildBar(
              context,
              'Monthly',
              (costData['monthly_usd'] as num?)?.toDouble() ?? 0,
              (limits['monthly'] as num?)?.toDouble() ?? 50,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBar(
      BuildContext context, String label, double spent, double limit) {
    final ratio = limit > 0 ? (spent / limit).clamp(0.0, 1.0) : 0.0;
    final color = ratio >= 1.0
        ? Colors.red
        : ratio >= 0.8
            ? Colors.amber
            : Colors.green;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: Theme.of(context).textTheme.bodyMedium),
            Text(
              '\$${spent.toStringAsFixed(2)} / \$${limit.toStringAsFixed(2)}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
        const SizedBox(height: 4),
        LinearProgressIndicator(
          value: ratio,
          backgroundColor: Theme.of(context).colorScheme.outline.withAlpha(51),
          color: color,
        ),
      ],
    );
  }
}

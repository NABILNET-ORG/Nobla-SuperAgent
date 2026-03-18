import 'package:flutter/material.dart';

class SecurityTierCard extends StatelessWidget {
  final int currentTier;
  final ValueChanged<int> onTierChange;

  const SecurityTierCard({
    super.key,
    required this.currentTier,
    required this.onTierChange,
  });

  static const _tierData = {
    1: ('SAFE', Icons.shield, Colors.green),
    2: ('STANDARD', Icons.shield, Colors.blue),
    3: ('ELEVATED', Icons.shield, Colors.amber),
    4: ('ADMIN', Icons.shield, Colors.red),
  };

  @override
  Widget build(BuildContext context) {
    final (name, icon, color) =
        _tierData[currentTier] ?? ('UNKNOWN', Icons.help, Colors.grey);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: color),
                const SizedBox(width: 8),
                Text('Security Tier',
                    style: Theme.of(context).textTheme.titleMedium),
              ],
            ),
            const Divider(),
            Row(
              children: [
                Text(
                  name,
                  style: Theme.of(context)
                      .textTheme
                      .headlineSmall
                      ?.copyWith(color: color),
                ),
                const Spacer(),
                DropdownButton<int>(
                  value: currentTier,
                  items: _tierData.entries.map((e) {
                    final (n, _, c) = e.value;
                    return DropdownMenuItem(
                      value: e.key,
                      child: Text(n, style: TextStyle(color: c)),
                    );
                  }).toList(),
                  onChanged: (v) {
                    if (v != null) onTierChange(v);
                  },
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

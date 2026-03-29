import 'package:flutter/material.dart';

class LearningStatsWidget extends StatelessWidget {
  final int feedbackCount;
  final int positiveCount;
  final int negativeCount;
  final int patternsDetected;
  final int autoSkillsActive;
  final int experimentsRunning;

  const LearningStatsWidget({
    super.key,
    required this.feedbackCount,
    required this.positiveCount,
    required this.negativeCount,
    required this.patternsDetected,
    required this.autoSkillsActive,
    required this.experimentsRunning,
  });

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        _StatCard(label: 'Feedback', value: '$feedbackCount', icon: Icons.feedback),
        _StatCard(label: 'Patterns', value: '$patternsDetected', icon: Icons.pattern),
        _StatCard(label: 'Auto-Skills', value: '$autoSkillsActive', icon: Icons.auto_fix_high),
        _StatCard(label: 'Experiments', value: '$experimentsRunning', icon: Icons.science),
      ],
    );
  }
}

class _StatCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;

  const _StatCard({required this.label, required this.value, required this.icon});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 24),
            const SizedBox(height: 4),
            Text(value, style: Theme.of(context).textTheme.headlineSmall),
            Text(label, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}

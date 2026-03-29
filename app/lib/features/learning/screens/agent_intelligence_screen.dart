import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/learning/providers/learning_providers.dart';
import 'package:nobla_agent/features/learning/widgets/learning_stats_widget.dart';

class AgentIntelligenceScreen extends ConsumerWidget {
  const AgentIntelligenceScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return DefaultTabController(
      length: 4,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Agent Intelligence'),
          bottom: const TabBar(
            tabs: [
              Tab(text: 'Overview'),
              Tab(text: 'Patterns'),
              Tab(text: 'Auto-Skills'),
              Tab(text: 'Settings'),
            ],
          ),
        ),
        body: TabBarView(
          children: [
            // Overview tab
            SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: ref.watch(feedbackStatsProvider).when(
                data: (stats) => LearningStatsWidget(
                  feedbackCount: stats['total'] ?? 0,
                  positiveCount: stats['positive'] ?? 0,
                  negativeCount: stats['negative'] ?? 0,
                  patternsDetected: 0,
                  autoSkillsActive: 0,
                  experimentsRunning: 0,
                ),
                loading: () => const Center(child: CircularProgressIndicator()),
                error: (e, _) => Text('Error: $e'),
              ),
            ),
            // Patterns tab
            ref.watch(patternListProvider).when(
              data: (patterns) => patterns.isEmpty
                  ? const Center(child: Text('No patterns detected yet'))
                  : ListView.builder(
                      itemCount: patterns.length,
                      itemBuilder: (context, index) => ListTile(
                        title: Text('Pattern ${index + 1}'),
                      ),
                    ),
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text('Error: $e')),
            ),
            // Auto-Skills tab
            ref.watch(macroListProvider).when(
              data: (macros) => macros.isEmpty
                  ? const Center(child: Text('No auto-skills yet'))
                  : ListView.builder(
                      itemCount: macros.length,
                      itemBuilder: (context, index) => ListTile(
                        title: Text('Skill ${index + 1}'),
                      ),
                    ),
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text('Error: $e')),
            ),
            // Settings tab
            SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Proactive Level', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  Text('Configure how proactively the agent suggests improvements.',
                      style: Theme.of(context).textTheme.bodySmall),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

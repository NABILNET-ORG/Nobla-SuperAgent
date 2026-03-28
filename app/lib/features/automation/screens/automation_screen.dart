import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/automation/screens/workflow_list_screen.dart';
import 'package:nobla_agent/features/automation/screens/webhook_screen.dart';

/// Top-level automation screen with Workflows and Webhooks tabs.
class AutomationScreen extends ConsumerStatefulWidget {
  const AutomationScreen({super.key});

  @override
  ConsumerState<AutomationScreen> createState() => _AutomationScreenState();
}

class _AutomationScreenState extends ConsumerState<AutomationScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Automation'),
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(icon: Icon(Icons.account_tree_outlined), text: 'Workflows'),
            Tab(icon: Icon(Icons.webhook_outlined), text: 'Webhooks'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: const [
          WorkflowListScreen(),
          WebhookScreen(),
        ],
      ),
    );
  }
}

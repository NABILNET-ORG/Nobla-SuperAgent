import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/providers/auth_provider.dart';
import 'package:nobla_agent/core/providers/config_provider.dart';
import 'package:nobla_agent/core/providers/notification_provider.dart';
import 'package:nobla_agent/features/dashboard/widgets/connection_card.dart';
import 'package:nobla_agent/features/dashboard/widgets/security_tier_card.dart';
import 'package:nobla_agent/features/dashboard/widgets/cost_card.dart';
import 'package:nobla_agent/main.dart';

final costDashboardProvider = StateProvider<Map<String, dynamic>>((ref) => {});

class DashboardScreen extends ConsumerStatefulWidget {
  const DashboardScreen({super.key});

  @override
  ConsumerState<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends ConsumerState<DashboardScreen> {
  Timer? _refreshTimer;

  @override
  void initState() {
    super.initState();
    _fetchCosts();
    _refreshTimer =
        Timer.periodic(const Duration(seconds: 30), (_) => _fetchCosts());
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    super.dispose();
  }

  Future<void> _fetchCosts() async {
    try {
      final result = await ref.read(jsonRpcProvider).call('system.costs');
      ref.read(costDashboardProvider.notifier).state = result;
    } catch (_) {}
  }

  Future<void> _onTierChange(int tier) async {
    final authState = ref.read(authProvider);
    if (authState is! Authenticated) return;
    String? passphrase;
    if (tier > authState.tier && tier >= 3) {
      passphrase = await _showPassphraseDialog();
      if (passphrase == null) return;
    }
    try {
      await ref.read(authProvider.notifier).escalate(tier, passphrase);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Escalation failed: $e')),
        );
      }
    }
  }

  Future<String?> _showPassphraseDialog() async {
    final controller = TextEditingController();
    return showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Passphrase Required'),
        content: TextField(
          controller: controller,
          obscureText: true,
          decoration: const InputDecoration(labelText: 'Passphrase'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, controller.text),
            child: const Text('Confirm'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authProvider);
    final killState = ref.watch(killSwitchProvider);
    final costs = ref.watch(costDashboardProvider);
    final config = ref.watch(configProvider);
    final currentTier = (authState is Authenticated) ? authState.tier : 1;

    return CustomScrollView(
      slivers: [
        const SliverAppBar(
            title: Text('Dashboard'), centerTitle: true, floating: true),
        SliverPadding(
          padding: const EdgeInsets.all(16),
          sliver: SliverList(
            delegate: SliverChildListDelegate([
              ConnectionCard(
                serverUrl: config.serverUrl,
                isConnected: true,
                serverVersion: '0.1.0',
              ),
              const SizedBox(height: 12),
              SecurityTierCard(
                currentTier: currentTier,
                onTierChange: _onTierChange,
              ),
              const SizedBox(height: 12),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    children: [
                      Icon(
                        killState == KillState.running
                            ? Icons.check_circle
                            : Icons.warning,
                        color: killState == KillState.running
                            ? Colors.green
                            : Colors.red,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        'Kill Switch: ${killState.name}',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              CostCard(costData: costs),
            ]),
          ),
        ),
      ],
    );
  }
}

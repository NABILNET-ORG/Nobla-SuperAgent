import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/providers/notification_provider.dart';
import 'package:nobla_agent/main.dart';

class KillSwitchFab extends ConsumerWidget {
  const KillSwitchFab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final killState = ref.watch(killSwitchProvider);
    return switch (killState) {
      KillState.running => _RunningFab(ref: ref),
      KillState.softKilling => _SoftKillingFab(ref: ref),
      KillState.killed => _KilledFab(ref: ref),
    };
  }
}

class _RunningFab extends StatelessWidget {
  final WidgetRef ref;
  const _RunningFab({required this.ref});

  @override
  Widget build(BuildContext context) {
    return FloatingActionButton(
      backgroundColor: Colors.red,
      onPressed: () => _confirmKill(context),
      tooltip: 'Emergency Stop',
      child: const Icon(Icons.stop, color: Colors.white),
    );
  }

  void _confirmKill(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Emergency Stop'),
        content: const Text('Halt all agent operations?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () {
              Navigator.pop(ctx);
              ref.read(jsonRpcProvider).call('system.kill');
              ref
                  .read(killSwitchProvider.notifier)
                  .updateFromNotification({'stage': 'soft'});
            },
            child: const Text('Kill'),
          ),
        ],
      ),
    );
  }
}

class _SoftKillingFab extends StatefulWidget {
  final WidgetRef ref;
  const _SoftKillingFab({required this.ref});

  @override
  State<_SoftKillingFab> createState() => _SoftKillingFabState();
}

class _SoftKillingFabState extends State<_SoftKillingFab>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return FloatingActionButton(
          backgroundColor:
              Color.lerp(Colors.amber, Colors.red, _controller.value),
          onPressed: () {
            widget.ref.read(jsonRpcProvider).call('system.kill');
          },
          tooltip: 'Force Kill',
          child: const Icon(Icons.warning, color: Colors.white),
        );
      },
    );
  }
}

class _KilledFab extends StatelessWidget {
  final WidgetRef ref;
  const _KilledFab({required this.ref});

  @override
  Widget build(BuildContext context) {
    return FloatingActionButton(
      backgroundColor: Colors.green,
      onPressed: () => _confirmResume(context),
      tooltip: 'Resume',
      child: const Icon(Icons.play_arrow, color: Colors.white),
    );
  }

  void _confirmResume(BuildContext context) {
    final controller = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Resume Agent'),
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
            onPressed: () {
              Navigator.pop(ctx);
              ref.read(jsonRpcProvider).call('system.resume', {
                'passphrase': controller.text,
              });
              ref.read(killSwitchProvider.notifier).setRunning();
            },
            child: const Text('Resume'),
          ),
        ],
      ),
    );
  }
}

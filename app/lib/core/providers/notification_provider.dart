import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';
import 'package:nobla_agent/features/security/models/approval_models.dart';
import 'package:nobla_agent/shared/providers/tool_activity_provider.dart';
import 'package:nobla_agent/features/tools/providers/tool_mirror_provider.dart';

enum KillState { running, softKilling, killed }

class KillSwitchNotifier extends StateNotifier<KillState> {
  KillSwitchNotifier() : super(KillState.running);

  void updateFromNotification(Map<String, dynamic> params) {
    final stage = params['stage'] as String?;
    if (stage == 'soft') {
      state = KillState.softKilling;
    } else if (stage == 'hard') {
      state = KillState.killed;
    }
  }

  void updateFromHealthResponse(String killState) {
    switch (killState) {
      case 'running':
        state = KillState.running;
      case 'soft_killing':
        state = KillState.softKilling;
      case 'killed':
        state = KillState.killed;
    }
  }

  void setRunning() => state = KillState.running;
}

final killSwitchProvider =
    StateNotifierProvider<KillSwitchNotifier, KillState>((ref) {
  return KillSwitchNotifier();
});

class BudgetWarning {
  final String period;
  final double limit;
  final double spent;
  const BudgetWarning(
      {required this.period, required this.limit, required this.spent});
}

final budgetWarningProvider = StateProvider<BudgetWarning?>((ref) => null);

class NotificationDispatcher {
  final WidgetRef _ref;
  StreamSubscription? _subscription;
  NotificationDispatcher(this._ref);

  void listen(JsonRpcClient rpc) {
    _subscription?.cancel();
    _subscription = rpc.notificationStream.listen(_dispatch);
  }

  void _dispatch(Map<String, dynamic> notification) {
    final method = notification['method'] as String?;
    final params = notification['params'] as Map<String, dynamic>? ?? {};
    switch (method) {
      case 'system.killed':
        _ref.read(killSwitchProvider.notifier).updateFromNotification(params);
      case 'system.budget_warning':
        _ref.read(budgetWarningProvider.notifier).state = BudgetWarning(
          period: params['period'] as String? ?? '',
          limit: (params['limit'] as num?)?.toDouble() ?? 0,
          spent: (params['spent'] as num?)?.toDouble() ?? 0,
        );
      case 'tool.activity':
        _ref
            .read(toolActivityProvider.notifier)
            .addEntry(ActivityEntry.fromJson(params));
      case 'tool.mirror.frame':
        _ref
            .read(toolMirrorProvider.notifier)
            .onScreenshotNotification(params);
    }
  }

  void dispose() {
    _subscription?.cancel();
  }
}

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/automation/models/webhook_models.dart';
import 'package:nobla_agent/main.dart' show jsonRpcProvider;

/// Fetches the webhook list for the current user.
///
/// Refresh with `ref.invalidate(webhookListProvider)`.
final webhookListProvider =
    FutureProvider<List<WebhookEntry>>((ref) async {
  final rpc = ref.watch(jsonRpcProvider);
  final result = await rpc.call('webhook.list', {});
  final items = result['webhooks'] as List<dynamic>? ?? [];
  return items
      .map((w) => WebhookEntry.fromJson(w as Map<String, dynamic>))
      .toList();
});

/// Fetches health summary for a specific webhook.
final webhookHealthProvider =
    FutureProvider.family<WebhookHealth, String>((ref, webhookId) async {
  final rpc = ref.watch(jsonRpcProvider);
  final result =
      await rpc.call('webhook.health', {'webhook_id': webhookId});
  return WebhookHealth.fromJson(result as Map<String, dynamic>);
});

/// Fetches recent events for a webhook.
final webhookEventsProvider =
    FutureProvider.family<List<WebhookEvent>, String>((ref, webhookId) async {
  final rpc = ref.watch(jsonRpcProvider);
  final result =
      await rpc.call('webhook.events', {'webhook_id': webhookId});
  final items = result['events'] as List<dynamic>? ?? [];
  return items
      .map((e) => WebhookEvent.fromJson(e as Map<String, dynamic>))
      .toList();
});

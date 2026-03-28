import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/automation/models/webhook_models.dart';
import 'package:nobla_agent/features/automation/providers/webhook_providers.dart';

/// Displays webhook registrations with health summaries.
class WebhookScreen extends ConsumerWidget {
  const WebhookScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final webhooksAsync = ref.watch(webhookListProvider);
    final theme = Theme.of(context);

    return Scaffold(
      body: webhooksAsync.when(
        loading: () => const Center(
          child: CircularProgressIndicator(key: ValueKey('loading')),
        ),
        error: (e, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.error_outline, size: 48, color: theme.colorScheme.error),
              const SizedBox(height: 8),
              Text('Failed to load webhooks', style: theme.textTheme.bodyLarge),
              const SizedBox(height: 8),
              FilledButton.tonal(
                onPressed: () => ref.invalidate(webhookListProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (webhooks) {
          if (webhooks.isEmpty) {
            return Center(
              key: const ValueKey('empty'),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.webhook_outlined, size: 64,
                      color: theme.colorScheme.outline),
                  const SizedBox(height: 12),
                  Text('No webhooks registered',
                      style: theme.textTheme.titleMedium),
                  const SizedBox(height: 4),
                  Text('Tap + to register one',
                      style: theme.textTheme.bodySmall),
                ],
              ),
            );
          }
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(webhookListProvider),
            child: ListView.builder(
              key: const ValueKey('webhook_list'),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              itemCount: webhooks.length,
              itemBuilder: (context, index) =>
                  WebhookCard(webhook: webhooks[index]),
            ),
          );
        },
      ),
      floatingActionButton: FloatingActionButton(
        key: const ValueKey('register_fab'),
        onPressed: () => _showRegisterDialog(context),
        child: const Icon(Icons.add),
      ),
    );
  }

  void _showRegisterDialog(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => const WebhookRegisterSheet(),
    );
  }
}

/// Card displaying a webhook with health indicators.
class WebhookCard extends StatelessWidget {
  final WebhookEntry webhook;
  const WebhookCard({super.key, required this.webhook});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dirIcon = webhook.direction == WebhookDirection.inbound
        ? Icons.call_received
        : Icons.call_made;
    final dirColor = webhook.direction == WebhookDirection.inbound
        ? Colors.blue
        : Colors.teal;

    return Card(
      key: ValueKey('webhook_${webhook.webhookId}'),
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Icon(dirIcon, color: dirColor),
        title: Text(webhook.name, maxLines: 1, overflow: TextOverflow.ellipsis),
        subtitle: Text(
          '${webhook.eventTypePrefix} \u2022 ${webhook.signatureScheme}',
          style: theme.textTheme.bodySmall,
        ),
        trailing: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          decoration: BoxDecoration(
            color: webhook.isActive
                ? Colors.green.withValues(alpha: 0.15)
                : Colors.grey.withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Text(
            webhook.isActive ? 'Active' : 'Inactive',
            style: TextStyle(
              color: webhook.isActive ? Colors.green : Colors.grey,
              fontSize: 12,
            ),
          ),
        ),
        onTap: () {
          // Navigate to webhook detail — future enhancement
        },
      ),
    );
  }
}

/// Bottom sheet for registering a new webhook.
class WebhookRegisterSheet extends StatefulWidget {
  const WebhookRegisterSheet({super.key});

  @override
  State<WebhookRegisterSheet> createState() => _WebhookRegisterSheetState();
}

class _WebhookRegisterSheetState extends State<WebhookRegisterSheet> {
  final _nameController = TextEditingController();
  final _prefixController = TextEditingController();
  final _secretController = TextEditingController();
  String _scheme = 'hmac-sha256';

  @override
  void dispose() {
    _nameController.dispose();
    _prefixController.dispose();
    _secretController.dispose();
    super.dispose();
  }

  bool get _isValid =>
      _nameController.text.trim().isNotEmpty &&
      _prefixController.text.trim().isNotEmpty &&
      _secretController.text.trim().length >= 8;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 16,
        right: 16,
        top: 16,
        bottom: MediaQuery.of(context).viewInsets.bottom + 16,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Register Webhook',
              style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          TextField(
            key: const ValueKey('name_input'),
            controller: _nameController,
            decoration: const InputDecoration(
              labelText: 'Name',
              hintText: 'e.g. GitHub Push',
              border: OutlineInputBorder(),
            ),
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 8),
          TextField(
            key: const ValueKey('prefix_input'),
            controller: _prefixController,
            decoration: const InputDecoration(
              labelText: 'Event prefix',
              hintText: 'e.g. github.push',
              border: OutlineInputBorder(),
            ),
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 8),
          TextField(
            key: const ValueKey('secret_input'),
            controller: _secretController,
            obscureText: true,
            decoration: const InputDecoration(
              labelText: 'Secret (min 8 chars)',
              border: OutlineInputBorder(),
            ),
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 8),
          DropdownButtonFormField<String>(
            key: const ValueKey('scheme_picker'),
            value: _scheme,
            decoration: const InputDecoration(
              labelText: 'Signature scheme',
              border: OutlineInputBorder(),
            ),
            items: const [
              DropdownMenuItem(value: 'hmac-sha256', child: Text('HMAC-SHA256')),
              DropdownMenuItem(value: 'hmac-sha1', child: Text('HMAC-SHA1')),
              DropdownMenuItem(value: 'none', child: Text('None')),
            ],
            onChanged: (v) => setState(() => _scheme = v ?? 'hmac-sha256'),
          ),
          const SizedBox(height: 12),
          FilledButton(
            key: const ValueKey('register_btn'),
            onPressed: _isValid ? () => Navigator.of(context).pop() : null,
            child: const Text('Register'),
          ),
        ],
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:nobla_agent/features/settings/providers/provider_settings_provider.dart';

class ProviderCard extends StatelessWidget {
  final ProviderInfo provider;
  final VoidCallback onConnect;
  final VoidCallback onDisconnect;

  const ProviderCard({
    super.key,
    required this.provider,
    required this.onConnect,
    required this.onDisconnect,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: ListTile(
        leading: Icon(
          provider.connected ? Icons.check_circle : Icons.circle_outlined,
          color: provider.connected ? Colors.green : Colors.grey,
        ),
        title: Text(provider.displayName),
        subtitle: Text(
          provider.connected
              ? 'Connected via ${provider.authType} \u2022 ${provider.model}'
              : 'Not connected',
          style: theme.textTheme.bodySmall,
        ),
        trailing: provider.connected
            ? TextButton(
                onPressed: onDisconnect,
                child: const Text('Disconnect'),
              )
            : FilledButton(
                onPressed: onConnect,
                child: const Text('Connect'),
              ),
      ),
    );
  }
}

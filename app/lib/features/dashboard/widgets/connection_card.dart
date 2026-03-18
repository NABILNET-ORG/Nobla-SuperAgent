import 'package:flutter/material.dart';

class ConnectionCard extends StatelessWidget {
  final String serverUrl;
  final bool isConnected;
  final String serverVersion;

  const ConnectionCard({
    super.key,
    required this.serverUrl,
    this.isConnected = false,
    this.serverVersion = 'Unknown',
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.cloud_outlined),
                const SizedBox(width: 8),
                Text('Connection',
                    style: Theme.of(context).textTheme.titleMedium),
              ],
            ),
            const Divider(),
            Row(
              children: [
                Container(
                  width: 10,
                  height: 10,
                  decoration: BoxDecoration(
                    color: isConnected ? Colors.green : Colors.red,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 8),
                Text(isConnected ? 'Connected' : 'Disconnected'),
              ],
            ),
            const SizedBox(height: 8),
            Text('Server: $serverUrl',
                style: Theme.of(context).textTheme.bodySmall),
            Text('Version: $serverVersion',
                style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}

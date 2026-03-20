import 'package:flutter/material.dart';

class ProviderManagementScreen extends StatelessWidget {
  const ProviderManagementScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('LLM Providers')),
      body: const Center(
        child: Text('Provider management - wire to Riverpod provider'),
      ),
    );
  }
}

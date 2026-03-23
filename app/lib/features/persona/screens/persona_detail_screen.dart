import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:nobla_agent/features/persona/providers/persona_list_provider.dart';
import 'package:nobla_agent/features/persona/providers/persona_preference_provider.dart';

class PersonaDetailScreen extends ConsumerWidget {
  final String personaId;
  const PersonaDetailScreen({super.key, required this.personaId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final personasAsync = ref.watch(personaListProvider);
    final persona = personasAsync.valueOrNull
        ?.where((p) => p.id == personaId)
        .firstOrNull;

    if (persona == null) {
      return Scaffold(
        appBar: AppBar(),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Text(persona.name),
        actions: [
          if (!persona.isBuiltin)
            IconButton(
              icon: const Icon(Icons.edit),
              tooltip: 'Edit',
              onPressed: () =>
                  context.go('/home/persona/${persona.id}/edit'),
            ),
          IconButton(
            icon: const Icon(Icons.copy),
            tooltip: 'Clone',
            onPressed: () => _clone(context, ref),
          ),
          if (!persona.isBuiltin)
            IconButton(
              icon: const Icon(Icons.delete),
              tooltip: 'Delete',
              onPressed: () => _confirmDelete(context, ref),
            ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (persona.isBuiltin)
            Chip(label: const Text('Builtin Preset')),
          const SizedBox(height: 16),
          _section(theme, 'Personality', persona.personality),
          _section(theme, 'Language Style', persona.languageStyle),
          if (persona.background != null)
            _section(theme, 'Background', persona.background!),
          if (persona.rules.isNotEmpty) ...[
            Text('Rules', style: theme.textTheme.titleSmall),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children:
                  persona.rules.map((r) => Chip(label: Text(r))).toList(),
            ),
            const SizedBox(height: 16),
          ],
          if (persona.temperatureBias != null)
            _section(theme, 'Temperature Bias',
                '${persona.temperatureBias! > 0 ? "+" : ""}${persona.temperatureBias!.toStringAsFixed(1)}'),
          if (persona.maxResponseLength != null)
            _section(theme, 'Max Response Length',
                '${persona.maxResponseLength} tokens'),
          if (persona.voiceConfig != null) ...[
            Text('Voice Config', style: theme.textTheme.titleSmall),
            const SizedBox(height: 8),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Text(
                  'Engine: ${persona.voiceConfig!['engine'] ?? 'default'}'
                  '${persona.voiceConfig!['voice_prompt'] != null ? '\nVoice: ${persona.voiceConfig!['voice_prompt']}' : ''}',
                ),
              ),
            ),
            const SizedBox(height: 16),
          ],
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: () => _setAsDefault(context, ref),
            icon: const Icon(Icons.star),
            label: const Text('Set as Default'),
          ),
        ],
      ),
    );
  }

  Widget _section(ThemeData theme, String title, String content) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: theme.textTheme.titleSmall),
          const SizedBox(height: 4),
          Text(content, style: theme.textTheme.bodyMedium),
        ],
      ),
    );
  }

  Future<void> _clone(BuildContext context, WidgetRef ref) async {
    try {
      final cloned =
          await ref.read(personaListProvider.notifier).clonePersona(personaId);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Cloned as "${cloned.name}"')),
        );
        context.go('/home/persona/${cloned.id}');
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Clone failed: $e')),
        );
      }
    }
  }

  Future<void> _confirmDelete(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete Persona?'),
        content: const Text('This action cannot be undone.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Delete', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;

    try {
      context.go('/home/persona');
      await ref.read(personaListProvider.notifier).deletePersona(personaId);
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Delete failed: $e')),
        );
      }
    }
  }

  Future<void> _setAsDefault(BuildContext context, WidgetRef ref) async {
    try {
      await ref
          .read(personaPreferenceProvider.notifier)
          .setDefault(personaId);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Set as default persona')),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to set default: $e')),
        );
      }
    }
  }
}

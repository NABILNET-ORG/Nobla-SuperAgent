import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shimmer/shimmer.dart';
import 'package:nobla_agent/features/persona/providers/persona_list_provider.dart';
import 'package:nobla_agent/features/persona/providers/persona_preference_provider.dart';
import 'package:nobla_agent/features/persona/providers/active_persona_provider.dart';
import 'package:nobla_agent/features/persona/widgets/persona_card.dart';

class PersonaListScreen extends ConsumerWidget {
  const PersonaListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final personasAsync = ref.watch(personaListProvider);
    final prefAsync = ref.watch(personaPreferenceProvider);
    final activePersona = ref.watch(activePersonaProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Personas'), centerTitle: true),
      floatingActionButton: FloatingActionButton(
        onPressed: () => context.go('/home/persona/create'),
        child: const Icon(Icons.add),
      ),
      body: personasAsync.when(
        loading: () => _buildShimmer(),
        error: (err, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('Failed to load personas',
                  style: Theme.of(context).textTheme.bodyLarge),
              const SizedBox(height: 8),
              FilledButton(
                onPressed: () =>
                    ref.read(personaListProvider.notifier).refresh(),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (personas) {
          final defaultId = prefAsync.valueOrNull?.defaultPersonaId;
          return ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: personas.length,
            itemBuilder: (context, index) {
              final persona = personas[index];
              return Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: PersonaCard(
                  persona: persona,
                  isDefault: persona.id == defaultId,
                  isActive: persona.id == activePersona?.id,
                  onTap: () => context.go('/home/persona/${persona.id}'),
                ),
              );
            },
          );
        },
      ),
    );
  }

  Widget _buildShimmer() {
    return Shimmer.fromColors(
      baseColor: Colors.grey.shade800,
      highlightColor: Colors.grey.shade600,
      child: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: 3,
        itemBuilder: (_, __) => Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Card(
            child: SizedBox(height: 100),
          ),
        ),
      ),
    );
  }
}

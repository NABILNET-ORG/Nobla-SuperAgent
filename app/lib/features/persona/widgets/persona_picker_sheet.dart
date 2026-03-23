import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:nobla_agent/features/persona/providers/active_persona_provider.dart';
import 'package:nobla_agent/features/persona/providers/persona_list_provider.dart';

class PersonaPickerSheet extends ConsumerWidget {
  const PersonaPickerSheet({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final personasAsync = ref.watch(personaListProvider);
    final activePersona = ref.watch(activePersonaProvider);
    final theme = Theme.of(context);

    return DraggableScrollableSheet(
      initialChildSize: 0.4,
      minChildSize: 0.25,
      maxChildSize: 0.6,
      expand: false,
      builder: (context, scrollController) {
        return Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text('Switch Persona', style: theme.textTheme.titleMedium),
            ),
            Expanded(
              child: personasAsync.when(
                loading: () => const Center(child: CircularProgressIndicator()),
                error: (_, __) =>
                    const Center(child: Text('Failed to load personas')),
                data: (personas) => ListView.builder(
                  controller: scrollController,
                  itemCount: personas.length + 1, // +1 for "Manage" link
                  itemBuilder: (context, index) {
                    if (index == personas.length) {
                      return ListTile(
                        leading: const Icon(Icons.settings),
                        title: const Text('Manage Personas'),
                        trailing: const Icon(Icons.arrow_forward_ios, size: 16),
                        onTap: () {
                          Navigator.pop(context);
                          context.go('/home/persona');
                        },
                      );
                    }
                    final persona = personas[index];
                    final isSelected = persona.id == activePersona?.id;
                    return ListTile(
                      leading: Icon(
                        isSelected
                            ? Icons.radio_button_checked
                            : Icons.radio_button_unchecked,
                        color: isSelected ? theme.colorScheme.primary : null,
                      ),
                      title: Text(persona.name),
                      subtitle: persona.isBuiltin
                          ? const Text('builtin',
                              style: TextStyle(fontSize: 12))
                          : null,
                      selected: isSelected,
                      onTap: () {
                        ref.read(sessionOverrideProvider.notifier).state =
                            persona.id;
                        Navigator.pop(context);
                      },
                    );
                  },
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

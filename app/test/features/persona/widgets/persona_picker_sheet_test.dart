import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:nobla_agent/core/network/api_client.dart';
import 'package:nobla_agent/features/persona/providers/persona_list_provider.dart';
import 'package:nobla_agent/features/persona/providers/persona_preference_provider.dart';
import 'package:nobla_agent/features/persona/widgets/persona_picker_sheet.dart';
import 'package:nobla_agent/shared/models/persona.dart';

class MockApiClient extends Mock implements ApiClient {}

void main() {
  final personas = [
    Persona(
      id: 'p1',
      name: 'Professional',
      personality: 'Expert',
      languageStyle: 'formal',
      isBuiltin: true,
    ),
    Persona(
      id: 'p2',
      name: 'Friendly',
      personality: 'Warm',
      languageStyle: 'casual',
      isBuiltin: true,
    ),
  ];

  testWidgets('shows all personas in list', (tester) async {
    final mockApi = MockApiClient();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          personaListProvider.overrideWith(
            (ref) {
              final notifier = PersonaListNotifier(mockApi);
              notifier.state = AsyncValue.data(personas);
              return notifier;
            },
          ),
          personaPreferenceProvider.overrideWith(
            (ref) {
              final notifier = PersonaPreferenceNotifier(mockApi);
              notifier.state = const AsyncValue.data(PersonaPreference());
              return notifier;
            },
          ),
        ],
        child: MaterialApp(
          home: Scaffold(
            // Render the sheet directly inside a SizedBox to avoid
            // DraggableScrollableSheet constraints issues in tests.
            body: SizedBox(
              height: 400,
              child: PersonaPickerSheet(),
            ),
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('Switch Persona'), findsOneWidget);
    expect(find.text('Professional'), findsOneWidget);
    expect(find.text('Friendly'), findsOneWidget);
    expect(
      find.text('Manage Personas', skipOffstage: false),
      findsOneWidget,
    );
  });
}

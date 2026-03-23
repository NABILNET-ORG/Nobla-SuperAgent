import 'package:flutter/material.dart';

class VoiceConfigSection extends StatelessWidget {
  final Map<String, dynamic>? voiceConfig;
  final ValueChanged<Map<String, dynamic>?> onChanged;

  const VoiceConfigSection({
    super.key,
    required this.voiceConfig,
    required this.onChanged,
  });

  static const _engines = ['cosyvoice', 'fish_speech', 'personaplex'];

  String get _currentEngine =>
      (voiceConfig?['engine'] as String?) ?? 'cosyvoice';

  String get _voicePrompt => (voiceConfig?['voice_prompt'] as String?) ?? '';

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isPersonaPlex = _currentEngine == 'personaplex';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Voice Settings', style: theme.textTheme.titleSmall),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          initialValue: _currentEngine,
          decoration: const InputDecoration(
            labelText: 'TTS Engine',
            border: OutlineInputBorder(),
          ),
          items: _engines
              .map((e) => DropdownMenuItem(value: e, child: Text(e)))
              .toList(),
          onChanged: (engine) {
            if (engine == null) return;
            final updated = Map<String, dynamic>.from(voiceConfig ?? {});
            updated['engine'] = engine;
            if (engine != 'personaplex') {
              updated.remove('voice_prompt');
              updated.remove('text_prompt');
            }
            onChanged(updated);
          },
        ),
        if (isPersonaPlex) ...[
          const SizedBox(height: 12),
          TextFormField(
            initialValue: _voicePrompt,
            decoration: const InputDecoration(
              labelText: 'Voice Prompt Filename',
              hintText: 'e.g., professional.wav',
              helperText: 'Pre-provisioned .wav file on the server',
              border: OutlineInputBorder(),
            ),
            onChanged: (value) {
              final updated = Map<String, dynamic>.from(voiceConfig ?? {});
              if (value.trim().isEmpty) {
                updated.remove('voice_prompt');
              } else {
                updated['voice_prompt'] = value.trim();
              }
              onChanged(updated);
            },
          ),
          const SizedBox(height: 8),
          Card(
            color: theme.colorScheme.surfaceContainerHighest,
            child: const Padding(
              padding: EdgeInsets.all(12),
              child: Row(
                children: [
                  Icon(Icons.info_outline, size: 18),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'PersonaPlex requires a running PersonaPlex server.',
                      style: TextStyle(fontSize: 12),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }
}

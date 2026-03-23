import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:nobla_agent/features/persona/providers/persona_list_provider.dart';
import 'package:nobla_agent/features/persona/widgets/rules_editor.dart';
import 'package:nobla_agent/features/persona/widgets/temperature_slider.dart';
import 'package:nobla_agent/features/persona/widgets/voice_config_section.dart';
import 'package:nobla_agent/main.dart';

class PersonaEditScreen extends ConsumerStatefulWidget {
  final String? personaId; // null = create mode

  const PersonaEditScreen({super.key, this.personaId});

  @override
  ConsumerState<PersonaEditScreen> createState() => _PersonaEditScreenState();
}

class _PersonaEditScreenState extends ConsumerState<PersonaEditScreen> {
  final _formKey = GlobalKey<FormState>();
  late TextEditingController _nameCtl;
  late TextEditingController _personalityCtl;
  late TextEditingController _styleCtl;
  late TextEditingController _backgroundCtl;
  late TextEditingController _maxLengthCtl;
  List<String> _rules = [];
  double? _temperatureBias;
  Map<String, dynamic>? _voiceConfig;
  bool _saving = false;

  bool get _isEditMode => widget.personaId != null;

  @override
  void initState() {
    super.initState();
    _nameCtl = TextEditingController();
    _personalityCtl = TextEditingController();
    _styleCtl = TextEditingController();
    _backgroundCtl = TextEditingController();
    _maxLengthCtl = TextEditingController();

    if (_isEditMode) {
      // Pre-fill from existing persona in next frame
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final personas = ref.read(personaListProvider).valueOrNull ?? [];
        final existing = personas.where((p) => p.id == widget.personaId);
        if (existing.isNotEmpty) {
          final p = existing.first;
          _nameCtl.text = p.name;
          _personalityCtl.text = p.personality;
          _styleCtl.text = p.languageStyle;
          _backgroundCtl.text = p.background ?? '';
          _maxLengthCtl.text =
              p.maxResponseLength?.toString() ?? '';
          setState(() {
            _rules = List.from(p.rules);
            _temperatureBias = p.temperatureBias;
            _voiceConfig = p.voiceConfig != null
                ? Map.from(p.voiceConfig!)
                : null;
          });
        }
      });
    }
  }

  @override
  void dispose() {
    _nameCtl.dispose();
    _personalityCtl.dispose();
    _styleCtl.dispose();
    _backgroundCtl.dispose();
    _maxLengthCtl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_isEditMode ? 'Edit Persona' : 'Create Persona'),
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextFormField(
              controller: _nameCtl,
              decoration: const InputDecoration(
                labelText: 'Name *',
                border: OutlineInputBorder(),
              ),
              maxLength: 100,
              validator: (v) =>
                  (v == null || v.trim().isEmpty) ? 'Name is required' : null,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _personalityCtl,
              decoration: const InputDecoration(
                labelText: 'Personality *',
                border: OutlineInputBorder(),
              ),
              maxLength: 1000,
              maxLines: 3,
              validator: (v) => (v == null || v.trim().isEmpty)
                  ? 'Personality is required'
                  : null,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _styleCtl,
              decoration: const InputDecoration(
                labelText: 'Language Style *',
                border: OutlineInputBorder(),
              ),
              maxLength: 500,
              validator: (v) => (v == null || v.trim().isEmpty)
                  ? 'Language style is required'
                  : null,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _backgroundCtl,
              decoration: const InputDecoration(
                labelText: 'Background',
                border: OutlineInputBorder(),
              ),
              maxLength: 2000,
              maxLines: 3,
            ),
            const SizedBox(height: 24),
            RulesEditor(
              rules: _rules,
              onChanged: (r) => setState(() => _rules = r),
            ),
            const SizedBox(height: 24),
            TemperatureSlider(
              value: _temperatureBias,
              onChanged: (v) => setState(() => _temperatureBias = v),
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _maxLengthCtl,
              decoration: const InputDecoration(
                labelText: 'Max Response Length (tokens)',
                border: OutlineInputBorder(),
                hintText: '50-4096',
              ),
              keyboardType: TextInputType.number,
              validator: (v) {
                if (v == null || v.trim().isEmpty) return null;
                final n = int.tryParse(v.trim());
                if (n == null || n < 50 || n > 4096) {
                  return 'Must be 50-4096';
                }
                return null;
              },
            ),
            const SizedBox(height: 24),
            VoiceConfigSection(
              voiceConfig: _voiceConfig,
              onChanged: (v) => setState(() => _voiceConfig = v),
            ),
            const SizedBox(height: 32),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: _saving
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Text(_isEditMode ? 'Save' : 'Create'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);

    final body = <String, dynamic>{
      'name': _nameCtl.text.trim(),
      'personality': _personalityCtl.text.trim(),
      'language_style': _styleCtl.text.trim(),
      if (_backgroundCtl.text.trim().isNotEmpty)
        'background': _backgroundCtl.text.trim(),
      'rules': _rules,
      if (_temperatureBias != null) 'temperature_bias': _temperatureBias,
      if (_maxLengthCtl.text.trim().isNotEmpty)
        'max_response_length': int.parse(_maxLengthCtl.text.trim()),
      if (_voiceConfig != null) 'voice_config': _voiceConfig,
    };

    // Auto-populate text_prompt for PersonaPlex
    if (_voiceConfig?['engine'] == 'personaplex') {
      body['voice_config'] = {
        ...(_voiceConfig ?? {}),
        'text_prompt': {
          'personality': _personalityCtl.text.trim(),
          'style': _styleCtl.text.trim(),
        },
      };
    }

    try {
      final api = ref.read(apiClientProvider);
      if (_isEditMode) {
        await api.updatePersona(widget.personaId!, body);
      } else {
        await api.createPersona(body);
      }
      ref.read(personaListProvider.notifier).refresh();
      if (mounted) context.go('/home/persona');
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Save failed: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}

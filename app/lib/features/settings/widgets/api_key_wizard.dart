import 'package:flutter/material.dart';

class ApiKeyWizard extends StatefulWidget {
  final String provider;
  final Future<bool> Function(String apiKey) onSubmit;

  const ApiKeyWizard({
    super.key,
    required this.provider,
    required this.onSubmit,
  });

  @override
  State<ApiKeyWizard> createState() => _ApiKeyWizardState();
}

class _ApiKeyWizardState extends State<ApiKeyWizard> {
  final _controller = TextEditingController();
  bool _isSubmitting = false;
  String? _error;

  static const _consoleUrls = {
    'openai': 'platform.openai.com/api-keys',
    'anthropic': 'console.anthropic.com/settings/keys',
    'groq': 'console.groq.com/keys',
    'deepseek': 'platform.deepseek.com/api_keys',
    'gemini': 'aistudio.google.com/apikey',
  };

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_controller.text.trim().isEmpty) return;
    setState(() {
      _isSubmitting = true;
      _error = null;
    });
    final success = await widget.onSubmit(_controller.text.trim());
    if (!mounted) return;
    if (success) {
      Navigator.of(context).pop(true);
    } else {
      setState(() {
        _isSubmitting = false;
        _error = 'Invalid API key';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final url = _consoleUrls[widget.provider] ?? '';
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
        left: 24,
        right: 24,
        top: 24,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Connect ${widget.provider.toUpperCase()}',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 16),
          if (url.isNotEmpty) ...[
            Text('1. Go to $url'),
            const Text('2. Create a new API key'),
            const Text('3. Paste it below'),
            const SizedBox(height: 16),
          ],
          TextField(
            controller: _controller,
            decoration: InputDecoration(
              labelText: 'API Key',
              errorText: _error,
              border: const OutlineInputBorder(),
            ),
            obscureText: true,
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: _isSubmitting ? null : _submit,
              child: _isSubmitting
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Connect'),
            ),
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}

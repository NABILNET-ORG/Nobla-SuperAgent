import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/automation/models/template_models.dart';
import 'package:nobla_agent/features/automation/providers/template_providers.dart';

/// Screen for importing a workflow from JSON.
class WorkflowImportScreen extends ConsumerStatefulWidget {
  const WorkflowImportScreen({super.key});

  @override
  ConsumerState<WorkflowImportScreen> createState() =>
      _WorkflowImportScreenState();
}

class _WorkflowImportScreenState
    extends ConsumerState<WorkflowImportScreen> {
  final _jsonController = TextEditingController();
  final _nameController = TextEditingController();
  WorkflowExportData? _preview;
  String? _parseError;

  @override
  void dispose() {
    _jsonController.dispose();
    _nameController.dispose();
    super.dispose();
  }

  void _tryParse() {
    final text = _jsonController.text.trim();
    if (text.isEmpty) {
      setState(() {
        _preview = null;
        _parseError = null;
      });
      return;
    }
    try {
      final data = jsonDecode(text) as Map<String, dynamic>;
      final version = data[r'$nobla_version'] as String?;
      if (version == null || version.isEmpty) {
        setState(() {
          _parseError = 'Missing \$nobla_version field';
          _preview = null;
        });
        return;
      }
      setState(() {
        _preview = WorkflowExportData.fromJson(data);
        _parseError = null;
      });
    } on FormatException {
      setState(() {
        _parseError = 'Invalid JSON format';
        _preview = null;
      });
    } catch (e) {
      setState(() {
        _parseError = 'Parse error: $e';
        _preview = null;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final opsState = ref.watch(templateOperationsProvider);

    return Scaffold(
      appBar: AppBar(
        key: const ValueKey('import_appbar'),
        title: const Text('Import Workflow'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Paste area
            Text('Paste workflow JSON', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            TextField(
              key: const ValueKey('json_input'),
              controller: _jsonController,
              maxLines: 8,
              decoration: InputDecoration(
                hintText: '{"\$nobla_version": "1.0", ...}',
                border: const OutlineInputBorder(),
                suffixIcon: IconButton(
                  key: const ValueKey('paste_btn'),
                  icon: const Icon(Icons.paste),
                  onPressed: () async {
                    final data = await Clipboard.getData('text/plain');
                    if (data?.text != null) {
                      _jsonController.text = data!.text!;
                      _tryParse();
                    }
                  },
                ),
              ),
              onChanged: (_) => _tryParse(),
            ),
            const SizedBox(height: 8),
            // Error
            if (_parseError != null)
              Container(
                key: const ValueKey('parse_error'),
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: theme.colorScheme.errorContainer,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(_parseError!,
                    style: TextStyle(color: theme.colorScheme.onErrorContainer)),
              ),
            // Preview
            if (_preview != null) ...[
              const SizedBox(height: 16),
              Card(
                key: const ValueKey('preview_card'),
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Preview', style: theme.textTheme.titleSmall),
                      const SizedBox(height: 8),
                      _PreviewRow(label: 'Name', value: _preview!.name),
                      _PreviewRow(
                          label: 'Description', value: _preview!.description),
                      _PreviewRow(
                          label: 'Steps',
                          value: '${_preview!.steps.length}'),
                      _PreviewRow(
                          label: 'Triggers',
                          value: '${_preview!.triggers.length}'),
                      _PreviewRow(
                          label: 'Schema',
                          value: 'v${_preview!.noblaVersion}'),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              // Name override
              TextField(
                key: const ValueKey('name_override'),
                controller: _nameController,
                decoration: const InputDecoration(
                  labelText: 'Workflow name (optional)',
                  hintText: 'Leave blank to use original name',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),
              // Import button
              FilledButton.icon(
                key: const ValueKey('import_btn'),
                onPressed: opsState.isLoading
                    ? null
                    : () => _doImport(),
                icon: opsState.isLoading
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.file_download),
                label: const Text('Import Workflow'),
              ),
            ],
            // Result
            if (opsState.hasError)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(
                  key: const ValueKey('import_error'),
                  'Import failed: ${opsState.error}',
                  style: TextStyle(color: theme.colorScheme.error),
                ),
              ),
            if (opsState.hasValue && opsState.value != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Card(
                  key: const ValueKey('import_success'),
                  color: theme.colorScheme.primaryContainer,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      children: [
                        Icon(Icons.check_circle,
                            color: theme.colorScheme.onPrimaryContainer),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            'Workflow imported successfully!',
                            style: TextStyle(
                                color: theme.colorScheme.onPrimaryContainer),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  void _doImport() {
    ref.read(templateOperationsProvider.notifier).importFromJson(
          _jsonController.text,
          name: _nameController.text.isEmpty ? null : _nameController.text,
        );
  }
}

/// Export bottom sheet — shows JSON and copy button.
class WorkflowExportSheet extends ConsumerWidget {
  final String workflowId;

  const WorkflowExportSheet({
    super.key,
    required this.workflowId,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final exportAsync = ref.watch(workflowExportProvider(workflowId));
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.all(16),
      child: exportAsync.when(
        loading: () => const Center(
          child: CircularProgressIndicator(key: ValueKey('export_loading')),
        ),
        error: (e, _) => Center(
          child: Text('Export failed: $e',
              style: TextStyle(color: theme.colorScheme.error)),
        ),
        data: (data) {
          final jsonStr =
              const JsonEncoder.withIndent('  ').convert(data.toJson());
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  Text('Export Workflow', style: theme.textTheme.titleMedium),
                  const Spacer(),
                  IconButton(
                    key: const ValueKey('copy_btn'),
                    icon: const Icon(Icons.copy),
                    onPressed: () {
                      Clipboard.setData(ClipboardData(text: jsonStr));
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                            content: Text('Copied to clipboard'),
                            duration: Duration(seconds: 2)),
                      );
                    },
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Container(
                key: const ValueKey('json_output'),
                constraints: const BoxConstraints(maxHeight: 300),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(12),
                  child: SelectableText(
                    jsonStr,
                    style: theme.textTheme.bodySmall
                        ?.copyWith(fontFamily: 'monospace'),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

/// Simple label-value row for preview card.
class _PreviewRow extends StatelessWidget {
  final String label;
  final String value;

  const _PreviewRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          SizedBox(
            width: 80,
            child: Text(label,
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.outline)),
          ),
          Expanded(
            child: Text(value, style: theme.textTheme.bodyMedium),
          ),
        ],
      ),
    );
  }
}

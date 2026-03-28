import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/automation/models/template_models.dart';
import 'package:nobla_agent/main.dart' show jsonRpcProvider;

/// Fetches all templates, optionally filtered by category/query/tags.
final templateListProvider =
    FutureProvider.family<List<WorkflowTemplate>, TemplateFilter>(
        (ref, filter) async {
  final rpc = ref.watch(jsonRpcProvider);
  final params = <String, dynamic>{};
  if (filter.query.isNotEmpty) params['query'] = filter.query;
  if (filter.category != null) params['category'] = filter.category!.value;
  if (filter.tags.isNotEmpty) params['tags'] = filter.tags.join(',');
  final result = await rpc.call('template.list', params);
  final items = result as List<dynamic>? ?? [];
  return items
      .map((t) => WorkflowTemplate.fromJson(t as Map<String, dynamic>))
      .toList();
});

/// Fetches full template detail with steps and triggers.
final templateDetailProvider =
    FutureProvider.family<WorkflowTemplateDetail, String>(
        (ref, templateId) async {
  final rpc = ref.watch(jsonRpcProvider);
  final result =
      await rpc.call('template.get', {'template_id': templateId});
  return WorkflowTemplateDetail.fromJson(result as Map<String, dynamic>);
});

/// Fetches available categories with counts.
final templateCategoriesProvider =
    FutureProvider<List<CategoryInfo>>((ref) async {
  final rpc = ref.watch(jsonRpcProvider);
  final result = await rpc.call('template.categories', {});
  final items = result as List<dynamic>? ?? [];
  return items
      .map((c) => CategoryInfo.fromJson(c as Map<String, dynamic>))
      .toList();
});

/// Exports a workflow as portable JSON data.
final workflowExportProvider =
    FutureProvider.family<WorkflowExportData, String>(
        (ref, workflowId) async {
  final rpc = ref.watch(jsonRpcProvider);
  final result =
      await rpc.call('workflow.export', {'workflow_id': workflowId});
  final data = result['data'] as Map<String, dynamic>? ?? {};
  return WorkflowExportData.fromJson(data);
});

/// Filter parameters for template search.
class TemplateFilter {
  final String query;
  final TemplateCategory? category;
  final List<String> tags;

  const TemplateFilter({
    this.query = '',
    this.category,
    this.tags = const [],
  });

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is TemplateFilter &&
          query == other.query &&
          category == other.category &&
          tags.length == other.tags.length;

  @override
  int get hashCode => Object.hash(query, category, tags.length);
}

/// Notifier for template instantiation and import operations.
class TemplateOperationsNotifier extends StateNotifier<AsyncValue<String?>> {
  final Ref _ref;

  TemplateOperationsNotifier(this._ref) : super(const AsyncValue.data(null));

  /// Instantiate a template into a live workflow.
  Future<String?> instantiate(String templateId, {String? name}) async {
    state = const AsyncValue.loading();
    try {
      final rpc = _ref.read(jsonRpcProvider);
      final params = <String, dynamic>{'template_id': templateId};
      if (name != null && name.isNotEmpty) params['name'] = name;
      final result = await rpc.call('template.instantiate', params);
      final workflowId = result['workflow_id'] as String?;
      state = AsyncValue.data(workflowId);
      return workflowId;
    } catch (e, st) {
      state = AsyncValue.error(e, st);
      return null;
    }
  }

  /// Import a workflow from JSON string.
  Future<String?> importFromJson(String jsonStr, {String? name}) async {
    state = const AsyncValue.loading();
    try {
      final data = jsonDecode(jsonStr) as Map<String, dynamic>;
      final rpc = _ref.read(jsonRpcProvider);
      final params = <String, dynamic>{'data': data};
      if (name != null && name.isNotEmpty) params['name'] = name;
      final result = await rpc.call('workflow.import', params);
      final workflowId = result['workflow_id'] as String?;
      state = AsyncValue.data(workflowId);
      return workflowId;
    } catch (e, st) {
      state = AsyncValue.error(e, st);
      return null;
    }
  }

  void clear() {
    state = const AsyncValue.data(null);
  }
}

/// Provider for template operations (instantiate, import).
final templateOperationsProvider =
    StateNotifierProvider<TemplateOperationsNotifier, AsyncValue<String?>>(
  (ref) => TemplateOperationsNotifier(ref),
);

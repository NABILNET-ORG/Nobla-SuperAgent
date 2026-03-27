import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/tools/models/tool_models.dart';
import 'package:nobla_agent/main.dart' show jsonRpcProvider;

/// Fetches the tool manifest from the backend via tool.list RPC.
///
/// Refresh with `ref.invalidate(toolCatalogProvider)`.
final toolCatalogProvider =
    FutureProvider<List<ToolManifestEntry>>((ref) async {
  final rpc = ref.watch(jsonRpcProvider);
  final result = await rpc.call('tool.list', {});
  final tools = result['tools'] as List<dynamic>? ?? [];
  return tools
      .map((t) => ToolManifestEntry.fromJson(t as Map<String, dynamic>))
      .toList();
});

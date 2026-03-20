import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/network/jsonrpc_client.dart';
import '../../../shared/models/memory_fact.dart';
import '../../../shared/models/memory_entity.dart';
import '../../../shared/models/memory_stats.dart';

/// State for memory viewer.
class MemoryViewerState {
  final List<MemoryFact> facts;
  final List<MemoryEntity> entities;
  final MemoryStats stats;
  final bool isLoading;
  final String? error;

  const MemoryViewerState({
    this.facts = const [],
    this.entities = const [],
    this.stats = const MemoryStats(),
    this.isLoading = false,
    this.error,
  });

  MemoryViewerState copyWith({
    List<MemoryFact>? facts,
    List<MemoryEntity>? entities,
    MemoryStats? stats,
    bool? isLoading,
    String? error,
  }) {
    return MemoryViewerState(
      facts: facts ?? this.facts,
      entities: entities ?? this.entities,
      stats: stats ?? this.stats,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}

/// Manages memory viewer state via JSON-RPC.
class MemoryViewerNotifier extends StateNotifier<MemoryViewerState> {
  final JsonRpcClient _rpc;

  MemoryViewerNotifier(this._rpc) : super(const MemoryViewerState());

  Future<void> loadStats() async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final result = await _rpc.call('memory.stats', {});
      state = state.copyWith(
        stats: MemoryStats.fromJson(result),
        isLoading: false,
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> loadFacts({String type = 'fact', int limit = 20}) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final result = await _rpc.call('memory.facts', {
        'type': type,
        'limit': limit,
      });
      final facts = (result['facts'] as List<dynamic>)
          .map((f) => MemoryFact.fromJson(f as Map<String, dynamic>))
          .toList();
      state = state.copyWith(facts: facts, isLoading: false);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> loadGraph({int limit = 50}) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final result = await _rpc.call('memory.graph', {'limit': limit});
      final entities = (result['entities'] as List<dynamic>)
          .map((e) => MemoryEntity.fromJson(e as Map<String, dynamic>))
          .toList();
      state = state.copyWith(entities: entities, isLoading: false);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<List<MemoryFact>> search(String query) async {
    try {
      final result = await _rpc.call('memory.search', {
        'query': query,
        'limit': 10,
      });
      return (result['results'] as List<dynamic>)
          .map((f) => MemoryFact.fromJson(f as Map<String, dynamic>))
          .toList();
    } catch (e) {
      return [];
    }
  }
}

/// Provider for memory viewer.
final memoryViewerProvider =
    StateNotifierProvider<MemoryViewerNotifier, MemoryViewerState>(
  (ref) {
    final rpc = ref.watch(jsonRpcProvider);
    return MemoryViewerNotifier(rpc);
  },
);

/// Placeholder — actual provider is in main.dart
final jsonRpcProvider = Provider<JsonRpcClient>((ref) {
  throw UnimplementedError('jsonRpcProvider must be overridden');
});

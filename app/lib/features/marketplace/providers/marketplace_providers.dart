import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/marketplace_models.dart';

/// Search params — use StateProvider so the screen controls the query.
final marketplaceQueryProvider = StateProvider<String>((ref) => '');
final marketplaceCategoryProvider = StateProvider<String?>((ref) => null);

/// Search results — derived from query + category state.
final marketplaceSearchProvider = FutureProvider<SearchResults>((ref) async {
  // Read search params (triggers rebuild when they change)
  ref.watch(marketplaceQueryProvider);
  ref.watch(marketplaceCategoryProvider);
  return const SearchResults(items: [], total: 0, page: 1, pageSize: 20);
});

final skillDetailProvider =
    FutureProvider.family<MarketplaceSkill?, String>((ref, skillId) async {
  return null;
});

final skillRatingsProvider =
    FutureProvider.family<List<SkillRating>, String>((ref, skillId) async {
  return [];
});

final updateListProvider = FutureProvider<List<UpdateNotification>>((ref) async {
  return [];
});

final recommendationsProvider =
    FutureProvider<Map<String, List<MarketplaceSkill>>>((ref) async {
  return {'based_on_patterns': [], 'similar_to_installed': []};
});

final categoryListProvider =
    FutureProvider<List<Map<String, dynamic>>>((ref) async {
  return [];
});

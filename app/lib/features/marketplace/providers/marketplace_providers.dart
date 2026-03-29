import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/marketplace_models.dart';

final marketplaceSearchProvider =
    FutureProvider.family<SearchResults, Map<String, dynamic>>(
        (ref, params) async {
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

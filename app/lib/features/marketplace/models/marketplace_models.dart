import 'package:flutter/foundation.dart';

// --- Enums ---

enum PackageType { archive, pointer }

enum TrustTier { community, verified, official }

enum VerificationStatus { none, pending, approved, rejected }

T _enumFromString<T extends Enum>(List<T> values, String? value, T defaultValue) {
  if (value == null) return defaultValue;
  final normalized = value.replaceAll('_', '').toLowerCase();
  return values.firstWhere(
    (e) {
      final enumName = e.name.toLowerCase();
      return enumName == normalized || enumName == value.toLowerCase();
    },
    orElse: () => defaultValue,
  );
}

// --- Models ---

@immutable
class SkillVersion {
  final String version;
  final String changelog;
  final String packageHash;
  final String? minNoblaVersion;
  final DateTime publishedAt;
  final bool scanPassed;

  const SkillVersion({
    required this.version,
    required this.changelog,
    required this.packageHash,
    this.minNoblaVersion,
    required this.publishedAt,
    required this.scanPassed,
  });

  factory SkillVersion.fromJson(Map<String, dynamic> json) {
    return SkillVersion(
      version: json['version'] as String? ?? '',
      changelog: json['changelog'] as String? ?? '',
      packageHash: json['package_hash'] as String? ?? '',
      minNoblaVersion: json['min_nobla_version'] as String?,
      publishedAt: DateTime.tryParse(json['published_at'] as String? ?? '') ??
          DateTime.now(),
      scanPassed: json['scan_passed'] as bool? ?? false,
    );
  }

  Map<String, dynamic> toJson() => {
        'version': version,
        'changelog': changelog,
        'package_hash': packageHash,
        if (minNoblaVersion != null) 'min_nobla_version': minNoblaVersion,
        'published_at': publishedAt.toIso8601String(),
        'scan_passed': scanPassed,
      };
}

@immutable
class MarketplaceSkill {
  final String id;
  final String name;
  final String displayName;
  final String description;
  final String authorId;
  final String authorName;
  final String category;
  final List<String> tags;
  final String sourceFormat;
  final PackageType packageType;
  final String? sourceUrl;
  final String currentVersion;
  final List<SkillVersion> versions;
  final TrustTier trustTier;
  final VerificationStatus verificationStatus;
  final bool securityScanPassed;
  final int installCount;
  final int activeUsers;
  final double avgRating;
  final int ratingCount;
  final double successRate;
  final DateTime createdAt;
  final DateTime updatedAt;

  const MarketplaceSkill({
    required this.id,
    required this.name,
    required this.displayName,
    required this.description,
    required this.authorId,
    required this.authorName,
    required this.category,
    required this.tags,
    required this.sourceFormat,
    required this.packageType,
    this.sourceUrl,
    required this.currentVersion,
    this.versions = const [],
    required this.trustTier,
    required this.verificationStatus,
    required this.securityScanPassed,
    required this.installCount,
    required this.activeUsers,
    required this.avgRating,
    required this.ratingCount,
    required this.successRate,
    required this.createdAt,
    required this.updatedAt,
  });

  factory MarketplaceSkill.fromJson(Map<String, dynamic> json) {
    return MarketplaceSkill(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      displayName: json['display_name'] as String? ?? '',
      description: json['description'] as String? ?? '',
      authorId: json['author_id'] as String? ?? '',
      authorName: json['author_name'] as String? ?? '',
      category: json['category'] as String? ?? 'utilities',
      tags: (json['tags'] as List?)?.cast<String>() ?? [],
      sourceFormat: json['source_format'] as String? ?? 'nobla',
      packageType: _enumFromString(
          PackageType.values, json['package_type'] as String?, PackageType.archive),
      sourceUrl: json['source_url'] as String?,
      currentVersion: json['current_version'] as String? ?? '0.0.0',
      versions: (json['versions'] as List?)
              ?.map((e) => SkillVersion.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
      trustTier: _enumFromString(
          TrustTier.values, json['trust_tier'] as String?, TrustTier.community),
      verificationStatus: _enumFromString(VerificationStatus.values,
          json['verification_status'] as String?, VerificationStatus.none),
      securityScanPassed: json['security_scan_passed'] as bool? ?? false,
      installCount: json['install_count'] as int? ?? 0,
      activeUsers: json['active_users'] as int? ?? 0,
      avgRating: (json['avg_rating'] as num?)?.toDouble() ?? 0.0,
      ratingCount: json['rating_count'] as int? ?? 0,
      successRate: (json['success_rate'] as num?)?.toDouble() ?? 0.0,
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ??
          DateTime.now(),
      updatedAt: DateTime.tryParse(json['updated_at'] as String? ?? '') ??
          DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'display_name': displayName,
        'description': description,
        'author_id': authorId,
        'author_name': authorName,
        'category': category,
        'tags': tags,
        'source_format': sourceFormat,
        'package_type': packageType.name,
        if (sourceUrl != null) 'source_url': sourceUrl,
        'current_version': currentVersion,
        'versions': versions.map((v) => v.toJson()).toList(),
        'trust_tier': trustTier.name,
        'verification_status': verificationStatus.name,
        'security_scan_passed': securityScanPassed,
        'install_count': installCount,
        'active_users': activeUsers,
        'avg_rating': avgRating,
        'rating_count': ratingCount,
        'success_rate': successRate,
        'created_at': createdAt.toIso8601String(),
        'updated_at': updatedAt.toIso8601String(),
      };
}

@immutable
class SkillRating {
  final String id;
  final String skillId;
  final String userId;
  final int stars;
  final String? review;
  final DateTime createdAt;

  const SkillRating({
    required this.id,
    required this.skillId,
    required this.userId,
    required this.stars,
    this.review,
    required this.createdAt,
  });

  factory SkillRating.fromJson(Map<String, dynamic> json) {
    return SkillRating(
      id: json['id'] as String? ?? '',
      skillId: json['skill_id'] as String? ?? '',
      userId: json['user_id'] as String? ?? '',
      stars: json['stars'] as int? ?? 0,
      review: json['review'] as String?,
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ??
          DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'skill_id': skillId,
        'user_id': userId,
        'stars': stars,
        if (review != null) 'review': review,
        'created_at': createdAt.toIso8601String(),
      };
}

@immutable
class UpdateNotification {
  final String skillId;
  final String skillName;
  final String installedVersion;
  final String latestVersion;
  final String changelog;

  const UpdateNotification({
    required this.skillId,
    required this.skillName,
    required this.installedVersion,
    required this.latestVersion,
    required this.changelog,
  });

  factory UpdateNotification.fromJson(Map<String, dynamic> json) {
    return UpdateNotification(
      skillId: json['skill_id'] as String? ?? '',
      skillName: json['skill_name'] as String? ?? '',
      installedVersion: json['installed_version'] as String? ?? '',
      latestVersion: json['latest_version'] as String? ?? '',
      changelog: json['changelog'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() => {
        'skill_id': skillId,
        'skill_name': skillName,
        'installed_version': installedVersion,
        'latest_version': latestVersion,
        'changelog': changelog,
      };
}

@immutable
class SearchResults {
  final List<MarketplaceSkill> items;
  final int total;
  final int page;
  final int pageSize;

  const SearchResults({
    required this.items,
    required this.total,
    required this.page,
    required this.pageSize,
  });

  factory SearchResults.fromJson(Map<String, dynamic> json) {
    return SearchResults(
      items: (json['items'] as List?)
              ?.map((e) => MarketplaceSkill.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
      total: json['total'] as int? ?? 0,
      page: json['page'] as int? ?? 1,
      pageSize: json['page_size'] as int? ?? 20,
    );
  }
}

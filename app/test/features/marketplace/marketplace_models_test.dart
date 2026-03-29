import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/marketplace/models/marketplace_models.dart';

void main() {
  group('PackageType enum', () {
    test('has 2 values', () {
      expect(PackageType.values.length, 2);
    });

    test('values match backend', () {
      expect(PackageType.archive.name, 'archive');
      expect(PackageType.pointer.name, 'pointer');
    });
  });

  group('TrustTier enum', () {
    test('has 3 values', () {
      expect(TrustTier.values.length, 3);
    });

    test('values match backend', () {
      expect(TrustTier.community.name, 'community');
      expect(TrustTier.verified.name, 'verified');
      expect(TrustTier.official.name, 'official');
    });
  });

  group('VerificationStatus enum', () {
    test('has 4 values', () {
      expect(VerificationStatus.values.length, 4);
    });
  });

  group('SkillVersion', () {
    test('fromJson round-trip', () {
      final json = {
        'version': '1.2.3',
        'changelog': 'Added feature X',
        'package_hash': 'abc123',
        'min_nobla_version': null,
        'published_at': '2026-03-29T10:00:00.000Z',
        'scan_passed': true,
      };
      final v = SkillVersion.fromJson(json);
      expect(v.version, '1.2.3');
      expect(v.changelog, 'Added feature X');
      expect(v.scanPassed, true);

      final out = v.toJson();
      expect(out['version'], '1.2.3');
      expect(out['scan_passed'], true);
    });
  });

  group('MarketplaceSkill', () {
    final json = {
      'id': 'skill-1',
      'name': 'github-mcp',
      'display_name': 'GitHub MCP',
      'description': 'GitHub integration via MCP',
      'author_id': 'a1',
      'author_name': 'Nobla Team',
      'category': 'productivity',
      'tags': ['github', 'git'],
      'source_format': 'mcp',
      'package_type': 'pointer',
      'source_url': 'npx server-github',
      'current_version': '1.0.0',
      'trust_tier': 'community',
      'verification_status': 'none',
      'security_scan_passed': true,
      'install_count': 42,
      'active_users': 10,
      'avg_rating': 4.5,
      'rating_count': 8,
      'success_rate': 0.95,
      'created_at': '2026-03-29T10:00:00.000Z',
      'updated_at': '2026-03-29T12:00:00.000Z',
    };

    test('fromJson parses all fields', () {
      final s = MarketplaceSkill.fromJson(json);
      expect(s.id, 'skill-1');
      expect(s.name, 'github-mcp');
      expect(s.displayName, 'GitHub MCP');
      expect(s.category, 'productivity');
      expect(s.tags, ['github', 'git']);
      expect(s.packageType, PackageType.pointer);
      expect(s.trustTier, TrustTier.community);
      expect(s.installCount, 42);
      expect(s.avgRating, 4.5);
      expect(s.successRate, 0.95);
    });

    test('toJson round-trip', () {
      final s = MarketplaceSkill.fromJson(json);
      final out = s.toJson();
      expect(out['name'], 'github-mcp');
      expect(out['package_type'], 'pointer');
      expect(out['trust_tier'], 'community');
    });

    test('fromJson with nested versions', () {
      final withVersions = Map<String, dynamic>.from(json);
      withVersions['versions'] = [
        {
          'version': '1.0.0',
          'changelog': 'Initial',
          'package_hash': 'h1',
          'min_nobla_version': null,
          'published_at': '2026-03-29T10:00:00.000Z',
          'scan_passed': true,
        }
      ];
      final s = MarketplaceSkill.fromJson(withVersions);
      expect(s.versions.length, 1);
      expect(s.versions.first.version, '1.0.0');
    });
  });

  group('SkillRating', () {
    test('fromJson with review', () {
      final json = {
        'id': 'r1',
        'skill_id': 's1',
        'user_id': 'u1',
        'stars': 4,
        'review': 'Great tool!',
        'created_at': '2026-03-29T10:00:00.000Z',
      };
      final r = SkillRating.fromJson(json);
      expect(r.stars, 4);
      expect(r.review, 'Great tool!');
    });

    test('fromJson without review', () {
      final json = {
        'id': 'r2',
        'skill_id': 's1',
        'user_id': 'u2',
        'stars': 5,
        'review': null,
        'created_at': '2026-03-29T10:00:00.000Z',
      };
      final r = SkillRating.fromJson(json);
      expect(r.stars, 5);
      expect(r.review, isNull);
    });
  });

  group('UpdateNotification', () {
    test('fromJson with version comparison', () {
      final json = {
        'skill_id': 's1',
        'skill_name': 'github-mcp',
        'installed_version': '1.0.0',
        'latest_version': '1.1.0',
        'changelog': 'Bug fixes',
      };
      final n = UpdateNotification.fromJson(json);
      expect(n.installedVersion, '1.0.0');
      expect(n.latestVersion, '1.1.0');
      expect(n.changelog, 'Bug fixes');
    });
  });

  group('SearchResults', () {
    test('fromJson with items list and pagination', () {
      final json = {
        'items': [
          {
            'id': 's1',
            'name': 'test',
            'display_name': 'Test',
            'description': 'desc',
            'author_id': 'a1',
            'author_name': 'Author',
            'category': 'utilities',
            'tags': <String>[],
            'source_format': 'nobla',
            'package_type': 'archive',
            'source_url': null,
            'current_version': '1.0.0',
            'trust_tier': 'community',
            'verification_status': 'none',
            'security_scan_passed': true,
            'install_count': 0,
            'active_users': 0,
            'avg_rating': 0.0,
            'rating_count': 0,
            'success_rate': 0.0,
            'created_at': '2026-03-29T10:00:00.000Z',
            'updated_at': '2026-03-29T10:00:00.000Z',
          }
        ],
        'total': 1,
        'page': 1,
        'page_size': 20,
      };
      final r = SearchResults.fromJson(json);
      expect(r.items.length, 1);
      expect(r.total, 1);
      expect(r.page, 1);
      expect(r.pageSize, 20);
    });
  });
}

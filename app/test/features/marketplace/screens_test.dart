import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/marketplace/models/marketplace_models.dart';
import 'package:nobla_agent/features/marketplace/providers/marketplace_providers.dart';
import 'package:nobla_agent/features/marketplace/screens/marketplace_screen.dart';
import 'package:nobla_agent/features/marketplace/screens/skill_detail_screen.dart';

MarketplaceSkill _testSkill({String id = 's1', String displayName = 'Test Skill'}) {
  return MarketplaceSkill(
    id: id,
    name: 'test-skill',
    displayName: displayName,
    description: 'A test skill description',
    authorId: 'a1',
    authorName: 'Author',
    category: 'utilities',
    tags: ['test', 'utility'],
    sourceFormat: 'nobla',
    packageType: PackageType.archive,
    currentVersion: '1.0.0',
    versions: [
      SkillVersion(
        version: '1.0.0',
        changelog: 'Initial release',
        packageHash: 'h1',
        publishedAt: DateTime(2026, 3, 29),
        scanPassed: true,
      ),
    ],
    trustTier: TrustTier.community,
    verificationStatus: VerificationStatus.none,
    securityScanPassed: true,
    installCount: 42,
    activeUsers: 10,
    avgRating: 4.0,
    ratingCount: 5,
    successRate: 0.95,
    createdAt: DateTime(2026, 3, 29),
    updatedAt: DateTime(2026, 3, 29),
  );
}

Widget _wrap(Widget child, {List<Override> overrides = const []}) {
  return ProviderScope(
    overrides: overrides,
    child: MaterialApp(home: child),
  );
}

void main() {
  group('MarketplaceScreen', () {
    testWidgets('shows search bar', (tester) async {
      await tester.pumpWidget(_wrap(const MarketplaceScreen()));
      expect(find.byType(TextField), findsOneWidget);
      expect(find.byIcon(Icons.search), findsOneWidget);
    });

    testWidgets('shows category filter chips', (tester) async {
      await tester.pumpWidget(_wrap(const MarketplaceScreen()));
      expect(find.byType(FilterChip), findsWidgets);
      expect(find.text('All'), findsOneWidget);
    });

    testWidgets('shows No skills found when empty', (tester) async {
      await tester.pumpWidget(_wrap(const MarketplaceScreen()));
      await tester.pumpAndSettle();
      expect(find.text('No skills found'), findsOneWidget);
    });
  });

  group('SkillDetailScreen', () {
    testWidgets('shows skill name and description', (tester) async {
      final skill = _testSkill();
      await tester.pumpWidget(_wrap(
        const SkillDetailScreen(skillId: 's1'),
        overrides: [
          skillDetailProvider.overrideWith((ref, id) async => skill),
          skillRatingsProvider.overrideWith((ref, id) async => <SkillRating>[]),
        ],
      ));
      await tester.pumpAndSettle();
      expect(find.text('Test Skill'), findsOneWidget);
      expect(find.text('A test skill description'), findsOneWidget);
    });

    testWidgets('shows Install button', (tester) async {
      final skill = _testSkill();
      await tester.pumpWidget(_wrap(
        const SkillDetailScreen(skillId: 's1'),
        overrides: [
          skillDetailProvider.overrideWith((ref, id) async => skill),
          skillRatingsProvider.overrideWith((ref, id) async => <SkillRating>[]),
        ],
      ));
      await tester.pumpAndSettle();
      expect(find.text('Install'), findsOneWidget);
    });

    testWidgets('shows Versions and Ratings sections', (tester) async {
      final skill = _testSkill();
      await tester.pumpWidget(_wrap(
        const SkillDetailScreen(skillId: 's1'),
        overrides: [
          skillDetailProvider.overrideWith((ref, id) async => skill),
          skillRatingsProvider.overrideWith((ref, id) async => <SkillRating>[]),
        ],
      ));
      await tester.pumpAndSettle();
      expect(find.text('Versions'), findsOneWidget);
      expect(find.text('Ratings'), findsOneWidget);
    });

    testWidgets('shows skill not found when null', (tester) async {
      await tester.pumpWidget(_wrap(
        const SkillDetailScreen(skillId: 'bad'),
        overrides: [
          skillDetailProvider.overrideWith((ref, id) async => null),
          skillRatingsProvider.overrideWith((ref, id) async => <SkillRating>[]),
        ],
      ));
      await tester.pumpAndSettle();
      expect(find.text('Skill not found'), findsOneWidget);
    });
  });
}

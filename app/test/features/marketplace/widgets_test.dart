import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/marketplace/models/marketplace_models.dart';
import 'package:nobla_agent/features/marketplace/widgets/skill_card.dart';
import 'package:nobla_agent/features/marketplace/widgets/rating_widget.dart';
import 'package:nobla_agent/features/marketplace/widgets/version_list_widget.dart';

MarketplaceSkill _testSkill({
  String name = 'test-skill',
  String displayName = 'Test Skill',
  String authorName = 'Author',
  TrustTier trustTier = TrustTier.community,
  double avgRating = 4.0,
  int installCount = 42,
}) {
  return MarketplaceSkill(
    id: 's1',
    name: name,
    displayName: displayName,
    description: 'A test skill for testing',
    authorId: 'a1',
    authorName: authorName,
    category: 'utilities',
    tags: ['test'],
    sourceFormat: 'nobla',
    packageType: PackageType.archive,
    currentVersion: '1.0.0',
    trustTier: trustTier,
    verificationStatus: VerificationStatus.none,
    securityScanPassed: true,
    installCount: installCount,
    activeUsers: 5,
    avgRating: avgRating,
    ratingCount: 3,
    successRate: 0.95,
    createdAt: DateTime(2026, 3, 29),
    updatedAt: DateTime(2026, 3, 29),
  );
}

Widget _wrap(Widget child) {
  return MaterialApp(home: Scaffold(body: child));
}

void main() {
  group('SkillCard', () {
    testWidgets('shows skill name and author', (tester) async {
      await tester.pumpWidget(_wrap(
        SkillCard(skill: _testSkill()),
      ));
      expect(find.text('Test Skill'), findsOneWidget);
      expect(find.text('Author'), findsOneWidget);
    });

    testWidgets('shows rating and install count', (tester) async {
      await tester.pumpWidget(_wrap(
        SkillCard(skill: _testSkill(avgRating: 4.0, installCount: 42)),
      ));
      expect(find.text('4.0'), findsOneWidget);
      expect(find.text('42'), findsOneWidget);
    });

    testWidgets('shows trust badge', (tester) async {
      await tester.pumpWidget(_wrap(
        SkillCard(skill: _testSkill(trustTier: TrustTier.verified)),
      ));
      expect(find.text('Verified'), findsOneWidget);
    });

    testWidgets('Install button calls callback', (tester) async {
      var called = false;
      await tester.pumpWidget(_wrap(
        SkillCard(
          skill: _testSkill(),
          onInstall: () => called = true,
        ),
      ));
      await tester.tap(find.text('Install'));
      expect(called, isTrue);
    });

    testWidgets('shows Installed when already installed', (tester) async {
      await tester.pumpWidget(_wrap(
        SkillCard(skill: _testSkill(), isInstalled: true),
      ));
      expect(find.text('Installed'), findsOneWidget);
      expect(find.text('Install'), findsNothing);
    });

    testWidgets('onTap triggers card tap', (tester) async {
      var tapped = false;
      await tester.pumpWidget(_wrap(
        SkillCard(
          skill: _testSkill(),
          onTap: () => tapped = true,
        ),
      ));
      await tester.tap(find.byType(InkWell).first);
      expect(tapped, isTrue);
    });
  });

  group('RatingWidget', () {
    testWidgets('shows 5 stars', (tester) async {
      await tester.pumpWidget(_wrap(
        const RatingWidget(currentRating: 3.0),
      ));
      expect(find.byIcon(Icons.star), findsNWidgets(3));
      expect(find.byIcon(Icons.star_border), findsNWidgets(2));
    });

    testWidgets('tap on star calls onRate with correct value', (tester) async {
      int? rated;
      await tester.pumpWidget(_wrap(
        RatingWidget(currentRating: 0, onRate: (v) => rated = v),
      ));
      // Tap the 4th star (index 3)
      final stars = find.byIcon(Icons.star_border);
      await tester.tap(stars.at(3));
      expect(rated, 4);
    });

    testWidgets('displays existing average rating', (tester) async {
      await tester.pumpWidget(_wrap(
        const RatingWidget(currentRating: 5.0),
      ));
      expect(find.byIcon(Icons.star), findsNWidgets(5));
      expect(find.byIcon(Icons.star_border), findsNothing);
    });
  });

  group('VersionListWidget', () {
    final versions = [
      SkillVersion(
        version: '1.0.0',
        changelog: 'Initial release',
        packageHash: 'h1',
        publishedAt: DateTime(2026, 3, 1),
        scanPassed: true,
      ),
      SkillVersion(
        version: '1.1.0',
        changelog: 'Bug fixes and improvements',
        packageHash: 'h2',
        publishedAt: DateTime(2026, 3, 15),
        scanPassed: true,
      ),
    ];

    testWidgets('shows version numbers', (tester) async {
      await tester.pumpWidget(_wrap(
        VersionListWidget(versions: versions),
      ));
      expect(find.text('v1.0.0'), findsOneWidget);
      expect(find.text('v1.1.0'), findsOneWidget);
    });

    testWidgets('expandable shows changelog', (tester) async {
      await tester.pumpWidget(_wrap(
        SingleChildScrollView(child: VersionListWidget(versions: versions)),
      ));
      // Tap to expand v1.1.0 (shown first as newest)
      await tester.tap(find.text('v1.1.0'));
      await tester.pumpAndSettle();
      expect(find.text('Bug fixes and improvements'), findsOneWidget);
    });

    testWidgets('shows empty message when no versions', (tester) async {
      await tester.pumpWidget(_wrap(
        const VersionListWidget(versions: []),
      ));
      expect(find.text('No version history available.'), findsOneWidget);
    });
  });
}

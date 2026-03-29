import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/learning/models/learning_models.dart';
import 'package:nobla_agent/features/learning/widgets/feedback_widget.dart';
import 'package:nobla_agent/features/learning/widgets/pattern_card.dart';
import 'package:nobla_agent/features/learning/widgets/suggestion_card.dart';
import 'package:nobla_agent/features/learning/widgets/learning_stats_widget.dart';

Widget _wrap(Widget child, {List<Override> overrides = const []}) {
  return ProviderScope(
    overrides: overrides,
    child: MaterialApp(home: Scaffold(body: child)),
  );
}

void main() {
  group('FeedbackWidget', () {
    testWidgets('shows thumbs up and down buttons', (tester) async {
      await tester.pumpWidget(_wrap(
        FeedbackWidget(messageId: 'msg-1', onFeedback: (_) {}),
      ));
      expect(find.byIcon(Icons.thumb_up_outlined), findsOneWidget);
      expect(find.byIcon(Icons.thumb_down_outlined), findsOneWidget);
    });

    testWidgets('tap thumbs up calls callback with 1', (tester) async {
      int? rating;
      await tester.pumpWidget(_wrap(
        FeedbackWidget(messageId: 'msg-1', onFeedback: (r) => rating = r),
      ));
      await tester.tap(find.byIcon(Icons.thumb_up_outlined));
      await tester.pump();
      expect(rating, 1);
    });

    testWidgets('tap expands to star rating', (tester) async {
      await tester.pumpWidget(_wrap(
        FeedbackWidget(messageId: 'msg-1', onFeedback: (_) {}),
      ));
      await tester.tap(find.byIcon(Icons.thumb_up_outlined));
      await tester.pumpAndSettle();
      expect(find.byIcon(Icons.star_border), findsNWidgets(5));
    });
  });

  group('PatternCard', () {
    testWidgets('shows pattern description', (tester) async {
      await tester.pumpWidget(_wrap(
        PatternCard(
          description: 'file.manage \u2192 code.run',
          status: PatternStatus.detected,
          confidence: 0.85,
          onReview: () {},
          onDismiss: () {},
        ),
      ));
      expect(find.text('file.manage \u2192 code.run'), findsOneWidget);
    });

    testWidgets('shows Review and Dismiss buttons', (tester) async {
      await tester.pumpWidget(_wrap(
        PatternCard(
          description: 'test', status: PatternStatus.detected,
          confidence: 0.8, onReview: () {}, onDismiss: () {},
        ),
      ));
      expect(find.text('Review'), findsOneWidget);
      expect(find.text('Dismiss'), findsOneWidget);
    });

    testWidgets('shows status chip', (tester) async {
      await tester.pumpWidget(_wrap(
        PatternCard(
          description: 'test', status: PatternStatus.confirmed,
          confidence: 0.9, onReview: () {}, onDismiss: () {},
        ),
      ));
      expect(find.text('confirmed'), findsOneWidget);
    });
  });

  group('SuggestionCard', () {
    testWidgets('shows title and description', (tester) async {
      await tester.pumpWidget(_wrap(
        SuggestionCard(
          title: 'Automate deploy',
          description: 'You do this every Monday',
          type: SuggestionType.pattern,
          onAccept: () {},
          onDismiss: () {},
          onSnooze: (_) {},
        ),
      ));
      expect(find.text('Automate deploy'), findsOneWidget);
      expect(find.text('You do this every Monday'), findsOneWidget);
    });

    testWidgets('shows Accept, Snooze, Dismiss actions', (tester) async {
      await tester.pumpWidget(_wrap(
        SuggestionCard(
          title: 't', description: 'd', type: SuggestionType.pattern,
          onAccept: () {}, onDismiss: () {}, onSnooze: (_) {},
        ),
      ));
      expect(find.text('Accept'), findsOneWidget);
      expect(find.text('Snooze'), findsOneWidget);
      expect(find.text('Dismiss'), findsOneWidget);
    });

    testWidgets('snooze shows duration options', (tester) async {
      await tester.pumpWidget(_wrap(
        SuggestionCard(
          title: 't', description: 'd', type: SuggestionType.pattern,
          onAccept: () {}, onDismiss: () {}, onSnooze: (_) {},
        ),
      ));
      await tester.tap(find.text('Snooze'));
      await tester.pumpAndSettle();
      expect(find.text('1 day'), findsOneWidget);
      expect(find.text('3 days'), findsOneWidget);
      expect(find.text('7 days'), findsOneWidget);
    });
  });

  group('LearningStatsWidget', () {
    testWidgets('shows stat labels', (tester) async {
      await tester.pumpWidget(_wrap(
        LearningStatsWidget(
          feedbackCount: 42,
          positiveCount: 35,
          negativeCount: 7,
          patternsDetected: 5,
          autoSkillsActive: 2,
          experimentsRunning: 1,
        ),
      ));
      expect(find.text('42'), findsOneWidget);
      expect(find.text('Feedback'), findsOneWidget);
      expect(find.text('Patterns'), findsOneWidget);
    });
  });
}

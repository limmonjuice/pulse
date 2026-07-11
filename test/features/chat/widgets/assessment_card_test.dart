// test/features/chat/widgets/assessment_card_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/widgets/assessment_card.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';

const _populated = UrgencyResult(
  type: ChatTurnType.assessment,
  message: 'msg',
  urgency: UrgencyLevel.seeDoctorSoon,
  explanation: 'explanation text',
  nextStep: 'next step text',
  selfCare: ['Rest', 'Fluids'],
  monitoring: ['Check temperature'],
  watchFor: ['Trouble breathing'],
  encouragement: 'You got this',
);

const _gracefulEmpty = UrgencyResult(
  type: ChatTurnType.assessment,
  message: 'msg',
  urgency: UrgencyLevel.seekCareNow,
  explanation: 'explanation text',
  nextStep: 'next step text',
  watchFor: ['Chest pain'],
  // selfCare and monitoring intentionally omitted (empty)
);

// AssessmentCard is only ever placed inside the chat transcript's scrolling
// ListView (unbounded height), never directly in a bounded Scaffold body —
// so the test harness wraps it in a SingleChildScrollView to match that,
// rather than changing the widget to scroll internally.
Widget _wrap(Widget child) =>
    MaterialApp(theme: AppTheme.light, home: Scaffold(body: SingleChildScrollView(child: child)));

void main() {
  testWidgets('renders every populated section', (tester) async {
    await tester.pumpWidget(_wrap(AssessmentCard(
      result: _populated,
      checkedSelfCare: const {},
      onToggleSelfCare: (_) {},
    )));

    expect(find.text('See a doctor soon'), findsOneWidget);
    expect(find.text('explanation text'), findsOneWidget);
    expect(find.text('What to do next'), findsOneWidget);
    expect(find.text('next step text'), findsOneWidget);
    expect(find.text('Things you can do today'), findsOneWidget);
    expect(find.text('Rest'), findsOneWidget);
    expect(find.text('Check in on yourself'), findsOneWidget);
    expect(find.text('Get care if…'), findsOneWidget);
    expect(find.text('You got this'), findsOneWidget);
    expect(find.text('Book a GP visit'), findsOneWidget);
  });

  testWidgets('empty self_care and monitoring sections disappear entirely', (tester) async {
    await tester.pumpWidget(_wrap(AssessmentCard(
      result: _gracefulEmpty,
      checkedSelfCare: const {},
      onToggleSelfCare: (_) {},
    )));

    expect(find.text('Things you can do today'), findsNothing);
    expect(find.text('Check in on yourself'), findsNothing);
    // watch_for is populated, so it still renders:
    expect(find.text('Get care if…'), findsOneWidget);
    expect(find.text('Find urgent care nearby'), findsOneWidget);
  });

  testWidgets('the monitor_at_home CTA uses the passive follow-up copy, not a manual-reminder phrase', (tester) async {
    await tester.pumpWidget(_wrap(AssessmentCard(
      result: const UrgencyResult(
        type: ChatTurnType.assessment,
        message: 'msg',
        urgency: UrgencyLevel.monitorAtHome,
      ),
      checkedSelfCare: const {},
      onToggleSelfCare: (_) {},
    )));

    expect(find.text("Okay — I'll check in on this tomorrow."), findsOneWidget);
  });

  testWidgets('tapping a self-care row calls onToggleSelfCare with its index', (tester) async {
    int? toggledIndex;
    await tester.pumpWidget(_wrap(AssessmentCard(
      result: _populated,
      checkedSelfCare: const {},
      onToggleSelfCare: (i) => toggledIndex = i,
    )));

    await tester.tap(find.text('Fluids'));
    await tester.pump();

    expect(toggledIndex, 1);
  });

  testWidgets('a checked self-care item renders with strikethrough styling', (tester) async {
    await tester.pumpWidget(_wrap(AssessmentCard(
      result: _populated,
      checkedSelfCare: const {0},
      onToggleSelfCare: (_) {},
    )));

    final restText = tester.widget<Text>(find.text('Rest'));
    expect(restText.style?.decoration, TextDecoration.lineThrough);
  });
}

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/widgets/urgency_strip.dart';

Widget _wrap(Widget child) => MaterialApp(
  theme: AppTheme.light,
  home: Scaffold(body: child),
);

void main() {
  testWidgets('shows the tier label and the next-step line', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const UrgencyStrip(
          urgency: UrgencyLevel.seekCareNow,
          nextStep: 'Go to the nearest ER today.',
        ),
      ),
    );

    // Label and next step render as one rich-text line, so exact-match
    // finders only work on the concatenated string.
    expect(find.textContaining('Seek care now'), findsOneWidget);
    expect(find.textContaining('Go to the nearest ER today.'), findsOneWidget);
  });

  testWidgets('label is always present even without a next step — color is '
      'never the only signal (accessibility rule)', (tester) async {
    await tester.pumpWidget(
      _wrap(const UrgencyStrip(urgency: UrgencyLevel.monitorAtHome)),
    );

    expect(find.text('Monitor at home'), findsOneWidget);
  });

  testWidgets('tapping the strip invokes onTap', (tester) async {
    var tapped = false;
    await tester.pumpWidget(
      _wrap(
        UrgencyStrip(
          urgency: UrgencyLevel.seeDoctorSoon,
          nextStep: 'See a doctor within 1-2 days.',
          onTap: () => tapped = true,
        ),
      ),
    );

    await tester.tap(find.byType(UrgencyStrip));
    expect(tapped, isTrue);
  });
}

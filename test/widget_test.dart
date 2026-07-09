import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:pulse_app/features/onboarding/screens/disclaimer_screen.dart';

void main() {
  testWidgets('DisclaimerScreen shows the onboarding disclaimer', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      const ProviderScope(child: MaterialApp(home: DisclaimerScreen())),
    );

    expect(find.text('Pulse'), findsOneWidget);
    expect(find.text('I understand, continue'), findsOneWidget);
  });
}

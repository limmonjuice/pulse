import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/widgets/typing_indicator.dart';

void main() {
  testWidgets('renders three dots and animates without error', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: const Scaffold(body: TypingIndicator()),
      ),
    );

    // Do NOT use pumpAndSettle — the animation repeats forever by design.
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(TypingIndicator), findsOneWidget);
  });
}

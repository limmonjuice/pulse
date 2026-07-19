import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/shared/widgets/warning_pill.dart';

void main() {
  testWidgets('renders its text and a warning icon', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: const Scaffold(body: WarningPill(text: 'Trouble breathing')),
      ),
    );
    expect(find.text('Trouble breathing'), findsOneWidget);
    expect(find.byIcon(Icons.warning_amber_rounded), findsOneWidget);
  });
}

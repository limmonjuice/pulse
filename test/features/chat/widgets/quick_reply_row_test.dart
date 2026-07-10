import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/widgets/quick_reply_row.dart';

void main() {
  testWidgets('tapping a chip sends its exact label', (tester) async {
    String? selected;
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: Scaffold(
        body: QuickReplyRow(
          options: const ['Under 38°', '38–39°', 'Over 39°'],
          onSelect: (value) => selected = value,
        ),
      ),
    ));

    await tester.tap(find.text('38–39°'));
    await tester.pump();

    expect(selected, '38–39°');
  });

  testWidgets('renders every option', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: Scaffold(
        body: QuickReplyRow(options: const ['A', 'B', 'C', 'D'], onSelect: (_) {}),
      ),
    ));

    for (final option in ['A', 'B', 'C', 'D']) {
      expect(find.text(option), findsOneWidget);
    }
  });
}

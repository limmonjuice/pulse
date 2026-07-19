import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/shared/widgets/checklist_row.dart';

Widget _wrap(Widget child) => MaterialApp(
  theme: AppTheme.light,
  home: Scaffold(body: child),
);

void main() {
  testWidgets(
    'interactive mode (onTap set) renders a checkbox and calls onTap',
    (tester) async {
      var tapped = false;
      await tester.pumpWidget(
        _wrap(ChecklistRow(text: 'Rest', onTap: () => tapped = true)),
      );
      expect(find.text('Rest'), findsOneWidget);
      await tester.tap(find.text('Rest'));
      expect(tapped, isTrue);
    },
  );

  testWidgets('done: true renders strikethrough text', (tester) async {
    await tester.pumpWidget(
      _wrap(ChecklistRow(text: 'Rest', done: true, onTap: () {})),
    );
    final text = tester.widget<Text>(find.text('Rest'));
    expect(text.style?.decoration, TextDecoration.lineThrough);
  });

  testWidgets(
    'read-only mode (no onTap) renders no checkbox and is not tappable',
    (tester) async {
      await tester.pumpWidget(
        _wrap(const ChecklistRow(text: 'Check temperature')),
      );
      expect(find.text('Check temperature'), findsOneWidget);
      expect(find.byType(InkWell), findsNothing);
      expect(find.byIcon(Icons.history_rounded), findsOneWidget);
    },
  );

  test('done: true without onTap asserts', () {
    expect(
      () => ChecklistRow(text: 'Check temperature', done: true),
      throwsAssertionError,
    );
  });
}

// test/features/chat/widgets/chat_input_bar_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/widgets/chat_input_bar.dart';

Widget _wrap(Widget child) => MaterialApp(
  theme: AppTheme.light,
  home: Scaffold(body: child),
);

void main() {
  testWidgets('typing then tapping send calls onSend with the trimmed text', (
    tester,
  ) async {
    String? sent;
    await tester.pumpWidget(_wrap(ChatInputBar(onSend: (t) => sent = t)));

    await tester.enterText(find.byType(TextField), '  hello there  ');
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pump();

    expect(sent, 'hello there');
  });

  testWidgets('the field clears after sending', (tester) async {
    await tester.pumpWidget(_wrap(ChatInputBar(onSend: (_) {})));

    await tester.enterText(find.byType(TextField), 'hello');
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pump();

    final field = tester.widget<TextField>(find.byType(TextField));
    expect(field.controller!.text, isEmpty);
  });

  testWidgets('an empty message does not call onSend', (tester) async {
    var called = false;
    await tester.pumpWidget(_wrap(ChatInputBar(onSend: (_) => called = true)));

    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pump();

    expect(called, isFalse);
  });
}

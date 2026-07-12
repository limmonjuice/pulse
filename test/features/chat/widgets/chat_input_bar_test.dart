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

  testWidgets('a disabled ChatInputBar dims the send button and ignores taps', (
    tester,
  ) async {
    var called = false;
    await tester.pumpWidget(
      _wrap(ChatInputBar(onSend: (_) => called = true, enabled: false)),
    );

    final container = tester.widget<Container>(
      find.byKey(const Key('chatInputBar.sendButtonFill')),
    );
    final decoration = container.decoration! as BoxDecoration;
    expect(decoration.color, AppColors.primaryDeep.withValues(alpha: 0.4));

    await tester.tap(
      find.byIcon(Icons.arrow_upward_rounded),
      warnIfMissed: false,
    );
    await tester.pump();

    expect(called, isFalse);
  });

  testWidgets(
    'the char-counter row height is constant across remaining values, isolated from '
    'TextField wrapping and ambient parent constraints',
    (tester) async {
      // Deliberately does NOT measure ChatInputBar's outer size: under
      // Scaffold(body: ChatInputBar(...)), the root Column receives a
      // bounded height and (mainAxisSize.max, the default) fills it
      // regardless of content, so the outer size tracks the viewport,
      // not the widget's real content height — that earlier version of
      // this test passed even with the original bug reintroduced.
      // Measuring the counter row's own keyed size sidesteps that, and
      // also avoids conflating the counter with the TextField's
      // separate up-to-4-line growth as more text is typed.
      Future<double> counterRowHeightFor(int length) async {
        await tester.pumpWidget(_wrap(ChatInputBar(onSend: (_) {})));
        await tester.enterText(find.byType(TextField), 'x' * length);
        await tester.pump();
        return tester
            .getSize(find.byKey(const Key('chatInputBar.counterRow')))
            .height;
      }

      final hidden = await counterRowHeightFor(0); // remaining = 2000
      final visible = await counterRowHeightFor(1850); // remaining = 150
      final atZero = await counterRowHeightFor(2000); // remaining = 0

      expect(visible, hidden);
      expect(atZero, hidden);
    },
  );
}

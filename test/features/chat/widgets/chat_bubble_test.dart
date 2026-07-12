import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/core/theme/contrast.dart';
import 'package:pulse_app/features/chat/widgets/chat_bubble.dart';

Widget _wrap(Widget child) => MaterialApp(
  theme: AppTheme.light,
  home: Scaffold(body: child),
);

void main() {
  testWidgets('renders the message text', (tester) async {
    await tester.pumpWidget(
      _wrap(const ChatBubble(text: 'hello', isUser: true)),
    );
    expect(find.text('hello'), findsOneWidget);
  });

  testWidgets('a user bubble right-aligns', (tester) async {
    await tester.pumpWidget(_wrap(const ChatBubble(text: 'hi', isUser: true)));
    final align = tester.widget<Align>(find.byType(Align));
    expect(align.alignment, Alignment.centerRight);
  });

  testWidgets('a Pulse bubble left-aligns', (tester) async {
    await tester.pumpWidget(_wrap(const ChatBubble(text: 'hi', isUser: false)));
    final align = tester.widget<Align>(find.byType(Align));
    expect(align.alignment, Alignment.centerLeft);
  });

  testWidgets(
    'a user bubble is white text on primaryInk, the pairing that clears WCAG AA',
    (tester) async {
      await tester.pumpWidget(
        _wrap(const ChatBubble(text: 'hi', isUser: true)),
      );
      final text = tester.widget<Text>(find.text('hi'));
      expect(text.style?.color, Colors.white);
      final container = tester.widget<Container>(
        find
            .ancestor(of: find.text('hi'), matching: find.byType(Container))
            .first,
      );
      final decoration = container.decoration! as BoxDecoration;
      expect(decoration.color, AppColors.primaryInk);
    },
  );

  testWidgets(
    // PINNED: computes the real WCAG contrast ratio from the ChatBubble's
    // actual rendered text/fill colors (not hardcoded constants that could
    // silently drift out of sync with the widget) and asserts >= 4.5, the
    // AA threshold for normal-size text. If a future change swaps either
    // color, this recomputes against whatever is actually shipped and
    // fails the moment the pairing drops below AA again — see
    // PULSE_DESIGN_SYSTEM.md's chat-bubble entry for the derivation that
    // ruled out white-on-primary (~2.64:1) and white-on-primaryDeep
    // (~3.88:1) before landing on white-on-primaryInk (~4.84:1).
    'PINNED: the user bubble text/fill pairing meets WCAG AA (>= 4.5:1)',
    (tester) async {
      await tester.pumpWidget(
        _wrap(const ChatBubble(text: 'hi', isUser: true)),
      );

      final text = tester.widget<Text>(find.text('hi'));
      final container = tester.widget<Container>(
        find
            .ancestor(of: find.text('hi'), matching: find.byType(Container))
            .first,
      );
      final fill = (container.decoration! as BoxDecoration).color!;
      final textColor = text.style!.color!;

      final ratio = contrastRatio(textColor, fill);
      expect(
        ratio,
        greaterThanOrEqualTo(4.5),
        reason:
            'user bubble text/fill contrast is ${ratio.toStringAsFixed(4)}:1, '
            'below the 4.5:1 WCAG AA threshold for normal-size text',
      );
    },
  );

  testWidgets('softVariant renders without throwing', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const ChatBubble(text: 'still here', isUser: false, softVariant: true),
      ),
    );
    expect(find.text('still here'), findsOneWidget);
  });
}

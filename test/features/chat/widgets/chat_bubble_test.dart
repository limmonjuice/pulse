import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
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
    'a user bubble renders dark text, not white, for WCAG AA contrast',
    (tester) async {
      await tester.pumpWidget(
        _wrap(const ChatBubble(text: 'hi', isUser: true)),
      );
      final text = tester.widget<Text>(find.text('hi'));
      expect(text.style?.color, AppColors.text);
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

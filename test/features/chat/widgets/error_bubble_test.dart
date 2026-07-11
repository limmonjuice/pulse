// test/features/chat/widgets/error_bubble_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/widgets/error_bubble.dart';

void main() {
  testWidgets('renders the message and a retry tap resends', (tester) async {
    var retried = false;
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: Scaffold(
        body: ErrorBubble(message: 'Something went wrong', onRetry: () => retried = true),
      ),
    ));

    expect(find.text('Something went wrong'), findsOneWidget);

    await tester.tap(find.text('Tap to try again'));
    await tester.pump();

    expect(retried, isTrue);
  });
}

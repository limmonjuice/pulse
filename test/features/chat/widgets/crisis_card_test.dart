import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/constants/crisis_resources.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/widgets/crisis_card.dart';

void main() {
  testWidgets('renders the message and every crisis resource', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: Scaffold(
          body: CrisisCard(
            message: 'Nandito lang ako.',
            launcher: (_) async => true,
          ),
        ),
      ),
    );

    expect(find.text('Nandito lang ako.'), findsOneWidget);
    for (final resource in crisisResources) {
      expect(find.text(resource.name), findsOneWidget);
    }
  });

  testWidgets('tapping a resource row calls the launcher with its phone URI', (
    tester,
  ) async {
    Uri? launched;
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: Scaffold(
          body: CrisisCard(
            message: 'msg',
            launcher: (uri) async {
              launched = uri;
              return true;
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text(crisisResources.first.name));
    await tester.pump();

    expect(launched, Uri.parse(crisisResources.first.phoneUri));
  });

  testWidgets(
    'shows a fallback message with the number spelled out when the launcher fails',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light,
          home: Scaffold(
            body: CrisisCard(message: 'msg', launcher: (_) async => false),
          ),
        ),
      );

      await tester.tap(find.text(crisisResources.first.name));
      await tester.pumpAndSettle();

      expect(find.textContaining(crisisResources.first.number), findsWidgets);
    },
  );
}

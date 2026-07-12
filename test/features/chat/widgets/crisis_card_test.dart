import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/constants/crisis_resources.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/widgets/crisis_card.dart';

// CrisisCard is only ever placed inside the chat transcript's scrolling
// ListView (unbounded height), never directly in a bounded Scaffold body —
// so the test harness wraps it in a SingleChildScrollView to match that,
// rather than changing the widget to scroll internally. Same precedent as
// AssessmentCard's test (Task 14): with 4 resources and 12 contact rows,
// the real data overflows the default flutter_test viewport without this.
Widget _wrap(Widget child) => MaterialApp(
  theme: AppTheme.light,
  home: Scaffold(body: SingleChildScrollView(child: child)),
);

void main() {
  testWidgets(
    'renders the message and every crisis resource with all of its contacts',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          CrisisCard(message: 'Nandito lang ako.', launcher: (_) async => true),
        ),
      );

      expect(find.text('Nandito lang ako.'), findsOneWidget);
      for (final resource in crisisResources) {
        expect(find.text(resource.name), findsOneWidget);
        for (final contact in resource.contacts) {
          final display = contact.label == null
              ? contact.value
              : '${contact.value} (${contact.label})';
          expect(find.text(display), findsOneWidget);
        }
      }
    },
  );

  testWidgets(
    'tapping a call contact calls the launcher with a tel: URI of just its digits',
    (tester) async {
      Uri? launched;
      await tester.pumpWidget(
        _wrap(
          CrisisCard(
            message: 'msg',
            launcher: (uri) async {
              launched = uri;
              return true;
            },
          ),
        ),
      );

      await tester.ensureVisible(find.text('1553'));
      await tester.tap(find.text('1553'));
      await tester.pump();

      expect(launched, Uri.parse('tel:1553'));
    },
  );

  testWidgets('tapping a text contact calls the launcher with an sms: URI', (
    tester,
  ) async {
    Uri? launched;
    await tester.pumpWidget(
      _wrap(
        CrisisCard(
          message: 'msg',
          launcher: (uri) async {
            launched = uri;
            return true;
          },
        ),
      ),
    );

    await tester.ensureVisible(find.text('0918-912-2813'));
    await tester.tap(find.text('0918-912-2813'));
    await tester.pump();

    expect(launched, Uri.parse('sms:09189122813'));
  });

  testWidgets(
    'tapping the email contact calls the launcher with a mailto: URI',
    (tester) async {
      Uri? launched;
      await tester.pumpWidget(
        _wrap(
          CrisisCard(
            message: 'msg',
            launcher: (uri) async {
              launched = uri;
              return true;
            },
          ),
        ),
      );

      await tester.ensureVisible(find.text('wisupport@dswd.gov.ph'));
      await tester.tap(find.text('wisupport@dswd.gov.ph'));
      await tester.pump();

      expect(launched, Uri.parse('mailto:wisupport@dswd.gov.ph'));
    },
  );

  testWidgets(
    'shows a fallback message with the contact spelled out when the launcher fails',
    (tester) async {
      await tester.pumpWidget(
        _wrap(CrisisCard(message: 'msg', launcher: (_) async => false)),
      );

      await tester.ensureVisible(find.text('1553'));
      await tester.tap(find.text('1553'));
      await tester.pumpAndSettle();

      expect(find.textContaining('1553'), findsWidgets);
      expect(find.textContaining('dialer'), findsOneWidget);
    },
  );
}

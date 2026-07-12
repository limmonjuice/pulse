import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/models/message.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';
import 'package:pulse_app/features/chat/providers/chat_provider.dart';
import 'package:pulse_app/features/chat/repositories/chat_repository.dart';
import 'package:pulse_app/features/chat/screens/chat_screen.dart';

/// Returns a fixed sequence of replies, one per call, then repeats the
/// last one — lets each test script exactly the turns it needs.
class _ScriptedRepository implements ChatRepository {
  _ScriptedRepository(this._script);
  final List<UrgencyResult> _script;
  int _i = 0;

  @override
  Future<Message> send({
    required String text,
    required List<Message> history,
  }) async {
    final reply = _script[_i < _script.length ? _i : _script.length - 1];
    _i++;
    return Message.assistant(reply);
  }
}

Future<void> _pump(WidgetTester tester, ChatRepository repository) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [chatRepositoryProvider.overrideWithValue(repository)],
      child: MaterialApp(theme: AppTheme.light, home: const ChatScreen()),
    ),
  );
  await tester.pump();
}

void main() {
  testWidgets(
    'tapping a quick-reply chip sends its label as the next user message',
    (tester) async {
      await _pump(
        tester,
        _ScriptedRepository([
          const UrgencyResult(
            type: ChatTurnType.question,
            message: 'How high has your fever been?',
            quickReplies: ['Under 38°', '38–39°'],
          ),
        ]),
      );

      await tester.enterText(find.byType(TextField), 'I have a fever');
      await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
      await tester.pumpAndSettle();

      expect(find.text('38–39°'), findsOneWidget);
      await tester.tap(find.text('38–39°'));
      await tester.pump();

      expect(
        find.text('38–39°'),
        findsWidgets,
      ); // the chip label, now also the sent user bubble
    },
  );

  testWidgets(
    'once a crisis turn arrives, a second crisis-type reply renders as the soft bubble, not a second full card',
    (tester) async {
      await _pump(
        tester,
        _ScriptedRepository([
          const UrgencyResult(
            type: ChatTurnType.crisis,
            message: 'first crisis reply',
          ),
          const UrgencyResult(
            type: ChatTurnType.crisis,
            message: 'second crisis reply',
          ),
        ]),
      );

      await tester.enterText(find.byType(TextField), 'I feel hopeless');
      await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
      await tester.pumpAndSettle();

      expect(
        find.text('Someone to talk to'),
        findsOneWidget,
      ); // full crisis card

      await tester.enterText(find.byType(TextField), 'still feeling this way');
      await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
      await tester.pumpAndSettle();

      // Still exactly one full crisis card (resource list), even though a
      // second crisis-type message arrived — it rendered as the soft bubble.
      expect(find.text('Someone to talk to'), findsOneWidget);
      expect(find.text('second crisis reply'), findsOneWidget);
    },
  );

  testWidgets('error-retry resends the last user message', (tester) async {
    var calls = 0;
    final repository = _CountingThenSucceedingRepository(() => calls++);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [chatRepositoryProvider.overrideWithValue(repository)],
        child: MaterialApp(theme: AppTheme.light, home: const ChatScreen()),
      ),
    );

    await tester.enterText(find.byType(TextField), 'I have a fever');
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pumpAndSettle();

    expect(find.text('Tap to try again'), findsOneWidget);
    expect(calls, 1);

    await tester.tap(find.text('Tap to try again'));
    await tester.pumpAndSettle();

    expect(calls, 2);
    expect(
      find.text('I have a fever'),
      findsOneWidget,
    ); // exactly one, not duplicated
  });

  testWidgets(
    'toggling a self-care checkbox does not trigger an auto-scroll-to-bottom',
    (tester) async {
      // A shrunk physical viewport (rather than relying on a single
      // assessment card's natural height) guarantees the transcript is
      // genuinely scrollable — without this, maxScrollExtent can be 0
      // in the default test viewport, silently making the assertion
      // below pass even with the bug this test exists to catch
      // reintroduced (verified: this exact test, unmodified except for
      // this viewport shrink, fails against the pre-fix code and passes
      // against the fix).
      tester.view.physicalSize = const Size(400, 500);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await _pump(
        tester,
        _ScriptedRepository([
          const UrgencyResult(
            type: ChatTurnType.assessment,
            message: 'msg',
            urgency: UrgencyLevel.monitorAtHome,
            selfCare: ['Rest', 'Fluids'],
          ),
        ]),
      );

      await tester.enterText(find.byType(TextField), 'I have a mild cold');
      await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
      await tester.pumpAndSettle();

      final controller = tester
          .widget<ListView>(find.byType(ListView))
          .controller!;
      expect(
        controller.position.maxScrollExtent,
        greaterThan(0),
        reason: 'test setup must produce a genuinely scrollable transcript',
      );

      // Simulate the user having scrolled up from the bottom to read
      // something earlier, then toggling a checkbox — this must not
      // yank them back down.
      final midpoint = controller.position.maxScrollExtent / 2;
      controller.jumpTo(midpoint);
      await tester.pump();
      final offsetBeforeToggle = controller.offset;

      await tester.tap(find.text('Rest'));
      await tester.pumpAndSettle();

      expect(controller.offset, offsetBeforeToggle);
    },
  );
}

class _CountingThenSucceedingRepository implements ChatRepository {
  _CountingThenSucceedingRepository(this._onCall);
  final void Function() _onCall;

  @override
  Future<Message> send({
    required String text,
    required List<Message> history,
  }) async {
    _onCall();
    throw Exception('down');
  }
}

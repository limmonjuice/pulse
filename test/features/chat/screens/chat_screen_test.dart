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

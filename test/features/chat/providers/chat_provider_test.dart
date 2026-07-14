import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/models/message.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';
import 'package:pulse_app/features/chat/providers/chat_provider.dart';
import 'package:pulse_app/features/chat/repositories/chat_repository.dart';

class _StubRepository implements ChatRepository {
  _StubRepository(this._reply);
  final UrgencyResult _reply;

  @override
  Future<Message> send({
    required String text,
    required List<Message> history,
  }) async {
    return Message.assistant(_reply);
  }
}

class _ThrowingRepository implements ChatRepository {
  @override
  Future<Message> send({required String text, required List<Message> history}) {
    throw Exception('network down');
  }
}

void main() {
  stripDerivationTests();

  test('send() appends the user message then the assistant reply', () async {
    final container = ProviderContainer(
      overrides: [
        chatRepositoryProvider.overrideWithValue(
          _StubRepository(
            const UrgencyResult(type: ChatTurnType.question, message: 'reply'),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    await container.read(chatControllerProvider.notifier).send('hello');
    final messages = container.read(chatControllerProvider).value!;

    expect(messages.length, 2);
    expect(messages[0].role, MessageRole.user);
    expect(messages[0].text, 'hello');
    expect(messages[1].role, MessageRole.assistant);
    expect(messages[1].text, 'reply');
  });

  test('an empty/whitespace-only message is not sent', () async {
    final container = ProviderContainer(
      overrides: [
        chatRepositoryProvider.overrideWithValue(
          _StubRepository(
            const UrgencyResult(type: ChatTurnType.question, message: 'reply'),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    await container.read(chatControllerProvider.notifier).send('   ');
    final messages = container.read(chatControllerProvider).value!;

    expect(messages, isEmpty);
  });

  test(
    'a repository failure appends a synthetic error message, never throws',
    () async {
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(_ThrowingRepository()),
        ],
      );
      addTearDown(container.dispose);

      await container.read(chatControllerProvider.notifier).send('hello');
      final messages = container.read(chatControllerProvider).value!;

      expect(messages.length, 2);
      expect(messages[1].payload?.type, ChatTurnType.error);
    },
  );

  test(
    'toggleSelfCare flips only the targeted index on the targeted message',
    () async {
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(
            _StubRepository(
              const UrgencyResult(
                type: ChatTurnType.assessment,
                message: 'msg',
                urgency: UrgencyLevel.monitorAtHome,
                selfCare: ['Rest', 'Fluids'],
              ),
            ),
          ),
        ],
      );
      addTearDown(container.dispose);

      await container.read(chatControllerProvider.notifier).send('hello');
      final assistantMessage = container
          .read(chatControllerProvider)
          .value!
          .last;

      container
          .read(chatControllerProvider.notifier)
          .toggleSelfCare(assistantMessage.id, 0);
      var updated = container.read(chatControllerProvider).value!.last;
      expect(updated.checkedSelfCare, {0});

      container
          .read(chatControllerProvider.notifier)
          .toggleSelfCare(assistantMessage.id, 0);
      updated = container.read(chatControllerProvider).value!.last;
      expect(updated.checkedSelfCare, isEmpty);
    },
  );

  test(
    'retryLast() drops the last user+reply pair and resends the same text',
    () async {
      var callCount = 0;
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(
            _CountingRepository(() => callCount++),
          ),
        ],
      );
      addTearDown(container.dispose);

      await container.read(chatControllerProvider.notifier).send('hello');
      expect(callCount, 1);

      await container.read(chatControllerProvider.notifier).retryLast();
      expect(callCount, 2);

      final messages = container.read(chatControllerProvider).value!;
      // Exactly one user message ("hello") and one assistant reply remain —
      // retry did not duplicate the user turn.
      expect(messages.where((m) => m.role == MessageRole.user).length, 1);
      expect(messages.first.text, 'hello');
    },
  );

  test(
    'chatIsSendingProvider is true only while a send is in flight, on both success and failure paths',
    () async {
      final completer = Completer<Message>();
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(
            _CompleterRepository(completer),
          ),
        ],
      );
      addTearDown(container.dispose);

      expect(container.read(chatIsSendingProvider), isFalse);

      final sendFuture = container
          .read(chatControllerProvider.notifier)
          .send('hello');
      // The synchronous prefix of send() has run (up to the first await);
      // the flag must already be true before the repository call resolves.
      expect(container.read(chatIsSendingProvider), isTrue);

      completer.complete(
        Message.assistant(
          const UrgencyResult(type: ChatTurnType.question, message: 'reply'),
        ),
      );
      await sendFuture;

      expect(container.read(chatIsSendingProvider), isFalse);
    },
  );

  test(
    'chatIsSendingProvider resets to false even when the repository throws',
    () async {
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(_ThrowingRepository()),
        ],
      );
      addTearDown(container.dispose);

      await container.read(chatControllerProvider.notifier).send('hello');

      expect(container.read(chatIsSendingProvider), isFalse);
    },
  );

  test(
    'a second send() while one is already in flight is ignored (no clobbered state)',
    () async {
      var callCount = 0;
      final completer = Completer<Message>();
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(
            _CompleterRepository(completer, onCall: () => callCount++),
          ),
        ],
      );
      addTearDown(container.dispose);

      final first = container
          .read(chatControllerProvider.notifier)
          .send('first');
      // Fires while the first send is still awaiting the completer —
      // must be a no-op, not a second concurrent repository call.
      final second = container
          .read(chatControllerProvider.notifier)
          .send('second');

      completer.complete(
        Message.assistant(
          const UrgencyResult(type: ChatTurnType.question, message: 'reply'),
        ),
      );
      await first;
      await second;

      expect(callCount, 1);
      final messages = container.read(chatControllerProvider).value!;
      expect(messages.where((m) => m.role == MessageRole.user).length, 1);
      expect(messages.first.text, 'first');
    },
  );

  test(
    'retryLast() while a send is already in flight does not truncate the in-flight message',
    () async {
      final completer = Completer<Message>();
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(
            _CompleterRepository(completer),
          ),
        ],
      );
      addTearDown(container.dispose);

      final sendFuture = container
          .read(chatControllerProvider.notifier)
          .send('hello');
      // A send is now in flight (chatIsSendingProvider is true, state has
      // exactly one user message). A retry attempt here — e.g. a
      // double-tap on an error bubble from a PREVIOUS turn — must not
      // truncate that in-flight message.
      await container.read(chatControllerProvider.notifier).retryLast();

      final messagesWhileInFlight = container
          .read(chatControllerProvider)
          .value!;
      expect(messagesWhileInFlight.length, 1);
      expect(messagesWhileInFlight.first.text, 'hello');

      completer.complete(
        Message.assistant(
          const UrgencyResult(type: ChatTurnType.question, message: 'reply'),
        ),
      );
      await sendFuture;

      final messagesAfter = container.read(chatControllerProvider).value!;
      expect(messagesAfter.length, 2);
      expect(messagesAfter.first.text, 'hello');
    },
  );

  test(
    'a self-care checkbox toggled while a later send is in flight is not reverted when that send resolves',
    () async {
      final firstCompleter = Completer<Message>();
      final secondCompleter = Completer<Message>();
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(
            _QueuedCompleterRepository([firstCompleter, secondCompleter]),
          ),
        ],
      );
      addTearDown(container.dispose);

      final firstSend = container
          .read(chatControllerProvider.notifier)
          .send('hello');
      firstCompleter.complete(
        Message.assistant(
          const UrgencyResult(
            type: ChatTurnType.assessment,
            message: 'msg',
            urgency: UrgencyLevel.monitorAtHome,
            selfCare: ['Rest', 'Fluids'],
          ),
        ),
      );
      await firstSend;

      final assistantMessage = container
          .read(chatControllerProvider)
          .value!
          .last;

      final secondSend = container
          .read(chatControllerProvider.notifier)
          .send('a follow-up question');
      // Toggle a self-care box on the EARLIER assessment message while the
      // second send is still in flight — must not be reverted when the
      // second send's completion merges its reply into state.
      container
          .read(chatControllerProvider.notifier)
          .toggleSelfCare(assistantMessage.id, 0);
      final midFlight = container.read(chatControllerProvider).value!;
      expect(
        midFlight
            .firstWhere((m) => m.id == assistantMessage.id)
            .checkedSelfCare,
        {0},
      );

      secondCompleter.complete(
        Message.assistant(
          const UrgencyResult(type: ChatTurnType.question, message: 'reply 2'),
        ),
      );
      await secondSend;

      final after = container.read(chatControllerProvider).value!;
      expect(
        after.firstWhere((m) => m.id == assistantMessage.id).checkedSelfCare,
        {0},
      );
    },
  );
}

/// Resolves each successive send() call from the next completer in the
/// queue — lets a test control multiple in-flight calls independently.
class _QueuedCompleterRepository implements ChatRepository {
  _QueuedCompleterRepository(this._completers);
  final List<Completer<Message>> _completers;
  int _i = 0;

  @override
  Future<Message> send({required String text, required List<Message> history}) {
    return _completers[_i++].future;
  }
}

class _CountingRepository implements ChatRepository {
  _CountingRepository(this._onCall);
  final void Function() _onCall;

  @override
  Future<Message> send({
    required String text,
    required List<Message> history,
  }) async {
    _onCall();
    return Message.assistant(
      const UrgencyResult(type: ChatTurnType.question, message: 'reply'),
    );
  }
}

/// Lets a test control exactly when send() resolves, to observe
/// mid-flight state (chatIsSendingProvider, re-entrancy) deterministically.
class _CompleterRepository implements ChatRepository {
  _CompleterRepository(this._completer, {void Function()? onCall})
    : _onCall = onCall;
  final Completer<Message> _completer;
  final void Function()? _onCall;

  @override
  Future<Message> send({required String text, required List<Message> history}) {
    _onCall?.call();
    return _completer.future;
  }
}

// ---------------------------------------------------------------------------
// Engine v2: strip state derivation (pure functions — no Riverpod needed)
// ---------------------------------------------------------------------------

Message _assistant(UrgencyResult payload) => Message.assistant(payload);

void stripDerivationTests() {
  group('latestConversationState', () {
    test('returns the newest payload that carries a conversation state, '
        'skipping local error turns with no envelope', () {
      final messages = [
        _assistant(
          const UrgencyResult(
            type: ChatTurnType.assessment,
            message: 'card',
            urgency: UrgencyLevel.seekCareNow,
            cardAction: CardAction.newCard,
            conversationState: ConversationState(
              urgency: UrgencyLevel.seekCareNow,
              assessmentActive: true,
              phase: 'guidance',
            ),
          ),
        ),
        _assistant(const UrgencyResult(type: ChatTurnType.error, message: 'x')),
      ];

      final state = latestConversationState(messages);
      expect(state, isNotNull);
      expect(state!.urgency, UrgencyLevel.seekCareNow);
      expect(state.assessmentActive, isTrue);
    });

    test('returns null when nothing carries a state', () {
      expect(latestConversationState([Message.user('hi')]), isNull);
    });
  });

  group('latestCardNextStep', () {
    test('comes from the most recent new/update assessment card', () {
      final messages = [
        _assistant(
          const UrgencyResult(
            type: ChatTurnType.assessment,
            message: 'old card',
            urgency: UrgencyLevel.monitorAtHome,
            nextStep: 'old step',
            cardAction: CardAction.newCard,
          ),
        ),
        _assistant(
          const UrgencyResult(
            type: ChatTurnType.assessment,
            message: 'new card',
            urgency: UrgencyLevel.seekCareNow,
            nextStep: 'go to the ER today',
            cardAction: CardAction.update,
          ),
        ),
        _assistant(
          const UrgencyResult(
            type: ChatTurnType.conversation,
            message: 'still stands',
            cardAction: CardAction.keep,
          ),
        ),
      ];

      expect(latestCardNextStep(messages), 'go to the ER today');
    });
  });
}

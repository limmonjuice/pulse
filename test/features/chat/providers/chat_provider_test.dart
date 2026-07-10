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

import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/features/chat/models/message.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';

void main() {
  test('Message.user builds a user-role message with no payload', () {
    final message = Message.user('I have a fever');

    expect(message.role, MessageRole.user);
    expect(message.text, 'I have a fever');
    expect(message.payload, isNull);
    expect(message.checkedSelfCare, isEmpty);
  });

  test(
    'Message.assistant carries the payload and mirrors its message text',
    () {
      const payload = UrgencyResult(
        type: ChatTurnType.question,
        message: 'How long?',
      );
      final message = Message.assistant(payload);

      expect(message.role, MessageRole.assistant);
      expect(message.text, 'How long?');
      expect(message.payload, payload);
    },
  );

  test('copyWith replaces checkedSelfCare without mutating the original', () {
    final original = Message.user('hi');
    final updated = original.copyWith(checkedSelfCare: {0, 2});

    expect(original.checkedSelfCare, isEmpty);
    expect(updated.checkedSelfCare, {0, 2});
    expect(updated.id, original.id);
    expect(updated.text, original.text);
  });

  group('toHistoryJson', () {
    test('a user message emits {role, content}', () {
      final message = Message.user('I have a fever');

      expect(message.toHistoryJson(), {
        'role': 'user',
        'content': 'I have a fever',
      });
    });

    test(
      'an assistant message emits {role, content, type} per the client contract',
      () {
        const payload = UrgencyResult(
          type: ChatTurnType.assessment,
          message: 'msg',
        );
        final message = Message.assistant(payload);

        expect(message.toHistoryJson(), {
          'role': 'assistant',
          'content': 'msg',
          'type': 'assessment',
        });
      },
    );

    test(
      'an error-type assistant message returns null (not real model output)',
      () {
        const payload = UrgencyResult(
          type: ChatTurnType.error,
          message: 'oops',
        );
        final message = Message.assistant(payload);

        expect(message.toHistoryJson(), isNull);
      },
    );

    test('an unparseable-type assistant message returns null', () {
      final message = Message.assistant(UrgencyResult.unparseable());

      expect(message.toHistoryJson(), isNull);
    });
  });
}

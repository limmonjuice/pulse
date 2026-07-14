import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart' show UrgencyLevel;
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
      'a question message emits {role, content, type} per the client contract',
      () {
        const payload = UrgencyResult(
          type: ChatTurnType.question,
          message: 'msg',
        );
        final message = Message.assistant(payload);

        expect(message.toHistoryJson(), {
          'role': 'assistant',
          'content': 'msg',
          'type': 'question',
        });
      },
    );

    test('an assessment message additionally echoes urgency, findings, '
        'explanation, and next_step — the server episode derivation depends '
        'on these (engine v2 contract)', () {
      const payload = UrgencyResult(
        type: ChatTurnType.assessment,
        message: 'msg',
        urgency: UrgencyLevel.seeDoctorSoon,
        explanation: 'why',
        nextStep: 'do this',
        findings: ['fever', 'cough'],
      );
      final message = Message.assistant(payload);

      expect(message.toHistoryJson(), {
        'role': 'assistant',
        'content': 'msg',
        'type': 'assessment',
        'urgency': 'see_doctor_soon',
        'findings': ['fever', 'cough'],
        'explanation': 'why',
        'next_step': 'do this',
      });
    });

    test('a conversation turn is echoed (reset markers ride on it)', () {
      const payload = UrgencyResult(
        type: ChatTurnType.conversation,
        message: 'No worries — thanks for telling me!',
        assessmentCleared: true,
      );
      final message = Message.assistant(payload);

      expect(message.toHistoryJson(), {
        'role': 'assistant',
        'content': 'No worries — thanks for telling me!',
        'type': 'conversation',
        'assessment_cleared': true,
      });
    });

    test('a conversation turn without a reset carries no marker key', () {
      const payload = UrgencyResult(
        type: ChatTurnType.conversation,
        message: 'The advice still stands.',
      );

      expect(Message.assistant(payload).toHistoryJson(), {
        'role': 'assistant',
        'content': 'The advice still stands.',
        'type': 'conversation',
      });
    });

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

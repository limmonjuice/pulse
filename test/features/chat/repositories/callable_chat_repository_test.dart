import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/features/chat/models/message.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';
import 'package:pulse_app/features/chat/repositories/callable_chat_repository.dart';

void main() {
  group('CallableChatRepository.buildRequestData', () {
    test(
      'includes the message and null profile/worry_level/regional_context',
      () {
        final data = CallableChatRepository.buildRequestData(
          text: 'I have a fever',
          history: const [],
        );

        expect(data['message'], 'I have a fever');
        expect(data['profile'], isNull);
        expect(data['worry_level'], isNull);
        expect(data['regional_context'], isNull);
        expect(data['conversation_id'], isNull);
      },
    );

    test(
      'builds history from prior messages via toHistoryJson, dropping error/unparseable turns',
      () {
        final history = [
          Message.user('hello'),
          Message.assistant(
            const UrgencyResult(type: ChatTurnType.question, message: 'q'),
          ),
          Message.assistant(
            const UrgencyResult(type: ChatTurnType.error, message: 'oops'),
          ),
        ];

        final data = CallableChatRepository.buildRequestData(
          text: 'next',
          history: history,
        );

        expect(data['history'], [
          {'role': 'user', 'content': 'hello'},
          {'role': 'assistant', 'content': 'q', 'type': 'question'},
        ]);
      },
    );
  });
}

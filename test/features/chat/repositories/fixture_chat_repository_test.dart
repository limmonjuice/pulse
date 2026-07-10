import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/features/chat/fixtures/chat_fixtures.dart';
import 'package:pulse_app/features/chat/models/message.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';
import 'package:pulse_app/features/chat/repositories/fixture_chat_repository.dart';

void main() {
  test(
    'cycles through all 6 fixtures in order across repeated sends',
    () async {
      final repository = FixtureChatRepository();

      for (var i = 0; i < chatFixtures.length; i++) {
        final reply = await repository.send(text: 'msg $i', history: const []);
        final expected = UrgencyResult.fromJson(chatFixtures[i]);

        expect(reply.role, MessageRole.assistant);
        expect(reply.payload?.type, expected.type);
        expect(reply.text, expected.message);
      }
    },
  );

  test('wraps back to the first fixture after the last one', () async {
    final repository = FixtureChatRepository();
    for (var i = 0; i < chatFixtures.length; i++) {
      await repository.send(text: 'msg', history: const []);
    }

    final wrapped = await repository.send(text: 'one more', history: const []);
    final firstExpected = UrgencyResult.fromJson(chatFixtures[0]);

    expect(wrapped.payload?.type, firstExpected.type);
  });
}

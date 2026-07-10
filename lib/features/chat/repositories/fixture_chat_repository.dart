import '../fixtures/chat_fixtures.dart';
import '../models/message.dart';
import '../models/urgency_result.dart';
import 'chat_repository.dart';

/// Cycles through [chatFixtures] on every call so every payload state is
/// reachable by hand-testing with zero network calls or API quota.
/// Debug-only — see chat_provider.dart for the kDebugMode gate that
/// selects this over [CallableChatRepository].
class FixtureChatRepository implements ChatRepository {
  int _index = 0;

  @override
  Future<Message> send({
    required String text,
    required List<Message> history,
  }) async {
    await Future<void>.delayed(const Duration(milliseconds: 500));
    final json = chatFixtures[_index % chatFixtures.length];
    _index++;
    return Message.assistant(UrgencyResult.fromJson(json));
  }
}

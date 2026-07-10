import '../models/message.dart';

/// Sends a user's message and returns the assistant's turn. Both
/// implementations may throw on failure — [ChatController] is the single
/// place that catches and converts a thrown exception into a consistent
/// error [Message] (see chat_provider.dart), so neither implementation
/// needs its own try/catch.
abstract class ChatRepository {
  Future<Message> send({required String text, required List<Message> history});
}

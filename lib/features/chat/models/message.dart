// lib/features/chat/models/message.dart

import 'urgency_result.dart';

enum MessageRole { user, assistant }

/// One turn in the conversation. Nothing here is persisted this pass —
/// no Firestore yet (TODO(episode model): once conversations are
/// persisted server-side, this becomes a stream over the active
/// episode's messages instead of local AsyncNotifier state — see
/// chat_provider.dart). No wire `fromJson`: nothing reads a Message back
/// from storage yet, so only `toHistoryJson()` (the client contract) is
/// needed, not a full round-trip pair.
class Message {
  Message({
    required this.id,
    required this.role,
    required this.text,
    this.payload,
    DateTime? timestamp,
    this.checkedSelfCare = const {},
  }) : timestamp = timestamp ?? DateTime.now();

  final String id;
  final MessageRole role;
  final String text;
  final UrgencyResult? payload;
  final DateTime timestamp;

  /// Indices into `payload.selfCare` the user has checked off this
  /// session. UI state only — never sent to the server, never persisted,
  /// no gamification. Mutated only via ChatController.toggleSelfCare.
  final Set<int> checkedSelfCare;

  factory Message.user(String text) =>
      Message(id: _newId(), role: MessageRole.user, text: text);

  factory Message.assistant(UrgencyResult payload) => Message(
    id: _newId(),
    role: MessageRole.assistant,
    text: payload.message,
    payload: payload,
  );

  static String _newId() => DateTime.now().microsecondsSinceEpoch.toString();

  Message copyWith({Set<int>? checkedSelfCare}) => Message(
    id: id,
    role: role,
    text: text,
    payload: payload,
    timestamp: timestamp,
    checkedSelfCare: checkedSelfCare ?? this.checkedSelfCare,
  );

  /// Per functions/main.py's client contract: assistant turns MUST carry
  /// their `type` so the server's crisis-lock detection
  /// (`_history_has_crisis_lock`) works. Returns null for assistant turns
  /// whose type the server never emits itself (`error`, `unparseable`) —
  /// those aren't real model output and shouldn't be replayed as history.
  Map<String, dynamic>? toHistoryJson() {
    if (role == MessageRole.user) {
      return {'role': 'user', 'content': text};
    }
    final type = payload?.type;
    if (type != ChatTurnType.question &&
        type != ChatTurnType.assessment &&
        type != ChatTurnType.crisis) {
      return null;
    }
    return {
      'role': 'assistant',
      'content': text,
      'type': type == ChatTurnType.question
          ? 'question'
          : type == ChatTurnType.assessment
          ? 'assessment'
          : 'crisis',
    };
  }
}

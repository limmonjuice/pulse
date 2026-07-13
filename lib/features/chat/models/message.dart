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

  /// The engine-v2 history echo (functions/episode_state.py's client
  /// contract): assistant turns MUST carry their `type` (crisis-lock and
  /// phase derivation), assessment turns additionally echo `urgency`
  /// (the server's current-card tracking) plus `findings`/`explanation`/
  /// `next_step` (prompt scaffolding), and reset turns echo
  /// `assessment_cleared: true` (episode reset markers). Returns null
  /// for assistant turns whose type the server never emits itself
  /// (`error`, `unparseable`) — those aren't real model output and
  /// shouldn't be replayed as history.
  Map<String, dynamic>? toHistoryJson() {
    if (role == MessageRole.user) {
      return {'role': 'user', 'content': text};
    }
    final p = payload;
    final type = p?.type;
    if (type != ChatTurnType.question &&
        type != ChatTurnType.assessment &&
        type != ChatTurnType.crisis &&
        type != ChatTurnType.conversation) {
      return null;
    }
    final map = <String, dynamic>{
      'role': 'assistant',
      'content': text,
      'type': type == ChatTurnType.question
          ? 'question'
          : type == ChatTurnType.assessment
          ? 'assessment'
          : type == ChatTurnType.crisis
          ? 'crisis'
          : 'conversation',
    };
    if (type == ChatTurnType.assessment) {
      map['urgency'] = UrgencyResult.urgencyWire(p!.urgency);
      map['findings'] = p.findings;
      map['explanation'] = p.explanation;
      map['next_step'] = p.nextStep;
    }
    if (p!.assessmentCleared) {
      map['assessment_cleared'] = true;
    }
    return map;
  }
}

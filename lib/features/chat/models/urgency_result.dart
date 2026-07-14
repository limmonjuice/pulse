// lib/features/chat/models/urgency_result.dart

import '../../../core/theme/app_theme.dart' show UrgencyLevel;

/// The five wire types the backend can send, plus [unparseable] — a
/// client-only fallback for malformed/unrecognized payloads. The backend
/// itself never emits "unparseable"; it exists so [UrgencyResult.fromJson]
/// can guarantee it never throws (see AGENTS.md: unknown/invalid wire
/// values must not crash). [conversation] (engine v2) is a plain reply
/// turn: no urgency, no card — it answers the person's message while the
/// existing guidance card stands.
enum ChatTurnType {
  question,
  assessment,
  crisis,
  conversation,
  error,
  unparseable,
}

/// What the server decided should happen to the guidance card this turn
/// (engine v2). The client renders an AssessmentCard ONLY for [newCard]
/// and [update] — no urgency logic client-side (AGENTS.md AI/Backend
/// rule 7). [none] is the client-only fallback for an absent or
/// unrecognized directive: render no card rather than guess.
enum CardAction { newCard, update, keep, clear, none }

/// The server's post-turn episode snapshot (engine v2) — drives the
/// pinned UrgencyStrip. Absent on locally fabricated turns (transport
/// errors), which the strip provider skips.
class ConversationState {
  const ConversationState({
    this.urgency,
    required this.assessmentActive,
    this.phase,
  });

  final UrgencyLevel? urgency;
  final bool assessmentActive;
  final String? phase;

  /// Null on anything that isn't a map — never throws.
  static ConversationState? fromJson(dynamic json) {
    if (json is! Map) return null;
    return ConversationState(
      urgency: UrgencyResult._parseUrgency(json['urgency']),
      assessmentActive: json['assessment_active'] == true,
      phase: json['phase'] is String ? json['phase'] as String : null,
    );
  }
}

/// The assistant's structured response payload for one turn — the
/// contract documented in functions/main.py and functions/gemini_client.py.
class UrgencyResult {
  const UrgencyResult({
    required this.type,
    required this.message,
    this.quickReplies = const [],
    this.urgency,
    this.explanation,
    this.watchFor = const [],
    this.nextStep,
    this.selfCare = const [],
    this.monitoring = const [],
    this.encouragement,
    this.cardAction = CardAction.none,
    this.conversationState,
    this.assessmentCleared = false,
    this.findings = const [],
  });

  final ChatTurnType type;
  final String message;
  final List<String> quickReplies;
  final UrgencyLevel? urgency;
  final String? explanation;
  final List<String> watchFor;
  final String? nextStep;
  final List<String> selfCare;
  final List<String> monitoring;
  final String? encouragement;

  /// Engine v2 envelope: card directive, post-turn state snapshot, reset
  /// marker, and the assessment's findings (echoed back to the server in
  /// history — see Message.toHistoryJson).
  final CardAction cardAction;
  final ConversationState? conversationState;
  final bool assessmentCleared;
  final List<String> findings;

  /// Never throws. Any structurally invalid payload — an unrecognized
  /// `type`, a missing `message`, or (per the contract) an `assessment`
  /// turn missing a valid `urgency` tier — becomes [ChatTurnType.unparseable]
  /// instead, so the UI can render the same apologetic style as a real
  /// "error" turn rather than crashing.
  factory UrgencyResult.fromJson(Map<String, dynamic> json) {
    final type = _parseType(json['type']);
    final message = json['message'];
    if (type == null || message is! String) {
      return UrgencyResult.unparseable(message is String ? message : null);
    }

    final urgency = _parseUrgency(json['urgency']);
    if (type == ChatTurnType.assessment && urgency == null) {
      return UrgencyResult.unparseable(message);
    }

    return UrgencyResult(
      type: type,
      message: message,
      quickReplies: _stringList(json['quick_replies']),
      urgency: urgency,
      explanation: _stringOrNull(json['explanation']),
      watchFor: _stringList(json['watch_for']),
      nextStep: _stringOrNull(json['next_step']),
      selfCare: _stringList(json['self_care']),
      monitoring: _stringList(json['monitoring']),
      encouragement: _stringOrNull(json['encouragement']),
      cardAction: _parseCardAction(json['card']),
      conversationState: ConversationState.fromJson(json['conversation_state']),
      assessmentCleared: json['assessment_cleared'] == true,
      findings: _stringList(json['findings']),
    );
  }

  factory UrgencyResult.unparseable([String? rawMessage]) {
    return UrgencyResult(
      type: ChatTurnType.unparseable,
      message:
          rawMessage ??
          "I couldn't quite make sense of that reply — try sending your "
              'message again?',
    );
  }

  Map<String, dynamic> toJson() => {
    'type': _typeWire(type),
    'message': message,
    'quick_replies': quickReplies,
    'urgency': urgencyWire(urgency),
    'explanation': explanation,
    'watch_for': watchFor,
    'next_step': nextStep,
    'self_care': selfCare,
    'monitoring': monitoring,
    'encouragement': encouragement,
  };

  static ChatTurnType? _parseType(dynamic value) {
    switch (value) {
      case 'question':
        return ChatTurnType.question;
      case 'assessment':
        return ChatTurnType.assessment;
      case 'crisis':
        return ChatTurnType.crisis;
      case 'conversation':
        return ChatTurnType.conversation;
      case 'error':
        return ChatTurnType.error;
      default:
        return null;
    }
  }

  /// Never throws: an absent, malformed, or unrecognized directive maps
  /// to [CardAction.none] — the client renders no card rather than guess.
  static CardAction _parseCardAction(dynamic card) {
    if (card is! Map) return CardAction.none;
    switch (card['action']) {
      case 'new':
        return CardAction.newCard;
      case 'update':
        return CardAction.update;
      case 'keep':
        return CardAction.keep;
      case 'clear':
        return CardAction.clear;
      default:
        return CardAction.none;
    }
  }

  static String? _typeWire(ChatTurnType type) {
    switch (type) {
      case ChatTurnType.question:
        return 'question';
      case ChatTurnType.assessment:
        return 'assessment';
      case ChatTurnType.crisis:
        return 'crisis';
      case ChatTurnType.conversation:
        return 'conversation';
      case ChatTurnType.error:
        return 'error';
      case ChatTurnType.unparseable:
        return null; // never a real wire value
    }
  }

  static UrgencyLevel? _parseUrgency(dynamic value) {
    switch (value) {
      case 'monitor_at_home':
        return UrgencyLevel.monitorAtHome;
      case 'see_doctor_soon':
        return UrgencyLevel.seeDoctorSoon;
      case 'seek_care_now':
        return UrgencyLevel.seekCareNow;
      default:
        return null;
    }
  }

  /// Public: Message.toHistoryJson echoes the tier string.
  static String? urgencyWire(UrgencyLevel? level) {
    switch (level) {
      case UrgencyLevel.monitorAtHome:
        return 'monitor_at_home';
      case UrgencyLevel.seeDoctorSoon:
        return 'see_doctor_soon';
      case UrgencyLevel.seekCareNow:
        return 'seek_care_now';
      case null:
        return null;
    }
  }

  static List<String> _stringList(dynamic value) {
    if (value is! List) return const [];
    return value.whereType<String>().toList();
  }

  static String? _stringOrNull(dynamic value) => value is String ? value : null;
}

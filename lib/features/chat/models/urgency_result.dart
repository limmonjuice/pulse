// lib/features/chat/models/urgency_result.dart

import '../../../core/theme/app_theme.dart' show UrgencyLevel;

/// The four wire types the backend can send, plus [unparseable] — a
/// client-only fallback for malformed/unrecognized payloads. The backend
/// itself never emits "unparseable"; it exists so [UrgencyResult.fromJson]
/// can guarantee it never throws (see AGENTS.md: unknown/invalid wire
/// values must not crash).
enum ChatTurnType { question, assessment, crisis, error, unparseable }

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
      explanation: json['explanation'] as String?,
      watchFor: _stringList(json['watch_for']),
      nextStep: json['next_step'] as String?,
      selfCare: _stringList(json['self_care']),
      monitoring: _stringList(json['monitoring']),
      encouragement: json['encouragement'] as String?,
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
    'urgency': _urgencyWire(urgency),
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
      case 'error':
        return ChatTurnType.error;
      default:
        return null;
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

  static String? _urgencyWire(UrgencyLevel? level) {
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
}

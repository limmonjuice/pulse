// lib/features/chat/repositories/callable_chat_repository.dart

import 'package:cloud_functions/cloud_functions.dart';

import '../models/message.dart';
import '../models/urgency_result.dart';
import 'chat_repository.dart';

/// Calls the `assess_symptoms` Callable Function in asia-southeast1. Per
/// AGENTS.md's AI/Backend rules, this repository only ever calls the
/// function and renders what comes back — it never constructs prompts,
/// holds API keys, or makes urgency decisions locally.
class CallableChatRepository implements ChatRepository {
  CallableChatRepository({FirebaseFunctions? functions})
    : _functions =
          functions ?? FirebaseFunctions.instanceFor(region: 'asia-southeast1');

  final FirebaseFunctions _functions;

  @override
  Future<Message> send({
    required String text,
    required List<Message> history,
  }) async {
    final callable = _functions.httpsCallable('assess_symptoms');
    final result = await callable.call<Map<String, dynamic>>(
      buildRequestData(text: text, history: history),
    );
    return Message.assistant(
      UrgencyResult.fromJson(Map<String, dynamic>.from(result.data as Map)),
    );
  }

  /// Extracted as a standalone, pure function so the request shape is
  /// unit-testable without a live Firebase project.
  ///
  /// profile / worry_level / regional_context: left null until the
  /// profile feature exists. TODO(profile feature): populate from the
  /// active household profile once it's built.
  static Map<String, dynamic> buildRequestData({
    required String text,
    required List<Message> history,
  }) {
    return {
      'message': text,
      'profile': null,
      'worry_level': null,
      'regional_context': null,
      'conversation_id': null,
      'history': history
          .map((m) => m.toHistoryJson())
          .whereType<Map<String, dynamic>>()
          .toList(),
    };
  }
}

// lib/features/visit_summary/repositories/callable_visit_summary_repository.dart
import 'package:cloud_functions/cloud_functions.dart';

import '../../../core/theme/app_theme.dart';
import '../../chat/models/message.dart';
import '../../chat/models/urgency_result.dart';
import '../models/visit_summary_result.dart';
import 'visit_summary_repository.dart';

/// Calls the `generate_visit_summary` Callable Function in
/// asia-southeast1. The caller (VisitSummaryController) is responsible
/// for stripping crisis exchanges before messages ever reach this class
/// — see stripCrisisExchanges in visit_summary_facts.dart.
class CallableVisitSummaryRepository implements VisitSummaryRepository {
  CallableVisitSummaryRepository({FirebaseFunctions? functions})
    : _functions =
          functions ?? FirebaseFunctions.instanceFor(region: 'asia-southeast1');

  final FirebaseFunctions _functions;

  @override
  Future<VisitSummaryResult> generate({
    required List<Message> messages,
    required UrgencyLevel? finalUrgency,
  }) async {
    final callable = _functions.httpsCallable('generate_visit_summary');
    final result = await callable.call<Map<String, dynamic>>(
      buildRequestData(messages: messages, finalUrgency: finalUrgency),
    );
    return VisitSummaryResult.fromJson(
      Map<String, dynamic>.from(result.data as Map),
    );
  }

  /// Extracted as a standalone, pure function so the request shape is
  /// unit-testable without a live Firebase project.
  static Map<String, dynamic> buildRequestData({
    required List<Message> messages,
    required UrgencyLevel? finalUrgency,
  }) {
    return {
      'history': messages
          .map((m) => m.toHistoryJson())
          .whereType<Map<String, dynamic>>()
          .toList(),
      'final_urgency': UrgencyResult.urgencyWire(finalUrgency),
    };
  }
}

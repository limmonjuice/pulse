// lib/features/visit_summary/models/visit_summary_result.dart

/// The narrative half of the visit summary — parsed from
/// generate_visit_summary's response. Mirrors how UrgencyResult.fromJson
/// defensively parses assess_symptoms responses: never throws on a
/// malformed shape (design spec §4.1, §5.2).
class VisitSummaryResult {
  const VisitSummaryResult({
    required this.isError,
    required this.summary,
    this.questionsForDoctor = const [],
    this.errorMessage,
  });

  final bool isError;
  final String summary;
  final List<String> questionsForDoctor;
  final String? errorMessage;

  factory VisitSummaryResult.fromJson(Map<String, dynamic> json) {
    if (json['type'] == 'error') {
      final message = json['message'];
      return VisitSummaryResult(
        isError: true,
        summary: '',
        errorMessage: message is String
            ? message
            : "Couldn't put together a visit summary right now — try again in a bit.",
      );
    }
    final summary = json['summary'];
    final questions = json['questions_for_doctor'];
    return VisitSummaryResult(
      isError: false,
      summary: summary is String ? summary : '',
      questionsForDoctor: questions is List
          ? questions.whereType<String>().toList()
          : const [],
    );
  }
}

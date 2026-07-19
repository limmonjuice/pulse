import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/features/visit_summary/models/visit_summary_result.dart';

void main() {
  test('parses a valid visit_summary payload', () {
    final result = VisitSummaryResult.fromJson({
      'type': 'visit_summary',
      'summary': 'A plain recap.',
      'questions_for_doctor': ['Question one?'],
      'metadata': {'prompt_version': '1.0.0'},
    });
    expect(result.isError, isFalse);
    expect(result.summary, 'A plain recap.');
    expect(result.questionsForDoctor, ['Question one?']);
  });

  test('parses an error payload', () {
    final result = VisitSummaryResult.fromJson({
      'type': 'error',
      'message': 'Something went wrong.',
    });
    expect(result.isError, isTrue);
    expect(result.errorMessage, 'Something went wrong.');
  });

  test('never throws on a malformed shape — missing fields default gracefully', () {
    final result = VisitSummaryResult.fromJson({'type': 'visit_summary'});
    expect(result.isError, isFalse);
    expect(result.summary, '');
    expect(result.questionsForDoctor, isEmpty);
  });

  test('non-string entries in questions_for_doctor are dropped, not crashed on', () {
    final result = VisitSummaryResult.fromJson({
      'type': 'visit_summary',
      'summary': 'recap',
      'questions_for_doctor': ['valid', 42, null],
    });
    expect(result.questionsForDoctor, ['valid']);
  });
}

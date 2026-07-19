import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/features/visit_summary/repositories/fixture_visit_summary_repository.dart';

void main() {
  test('returns a non-error VisitSummaryResult with content', () async {
    final result = await FixtureVisitSummaryRepository().generate(
      messages: const [],
      finalUrgency: null,
    );
    expect(result.isError, isFalse);
    expect(result.summary, isNotEmpty);
  });
}

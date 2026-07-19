// lib/features/visit_summary/repositories/fixture_visit_summary_repository.dart
import '../../../core/theme/app_theme.dart';
import '../../chat/models/message.dart';
import '../models/visit_summary_result.dart';
import 'visit_summary_repository.dart';

/// Debug-only fixture repository — zero network calls, zero quota cost.
/// Because the narrative call is already deliberately gated behind an
/// in-screen "Generate summary" tap (design spec §5.4), swapping this in
/// makes the whole visit-summary screen demoable end-to-end with zero
/// API calls. See visit_summary_provider.dart for the kDebugMode gate.
class FixtureVisitSummaryRepository implements VisitSummaryRepository {
  @override
  Future<VisitSummaryResult> generate({
    required List<Message> messages,
    required UrgencyLevel? finalUrgency,
  }) async {
    await Future<void>.delayed(const Duration(milliseconds: 500));
    return const VisitSummaryResult(
      isError: false,
      summary:
          'This conversation covered a mild headache that started this '
          'morning, with no other symptoms reported.',
      questionsForDoctor: [
        'Could this be related to recent screen time or sleep changes?',
        "Is there anything I should watch for that would mean this needs "
            'more urgent attention?',
      ],
    );
  }
}

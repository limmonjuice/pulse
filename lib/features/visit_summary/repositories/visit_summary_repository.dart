import '../../../core/theme/app_theme.dart';
import '../../chat/models/message.dart';
import '../models/visit_summary_result.dart';

/// Generates the narrative half (recap + doctor questions) of a visit
/// summary. Per AGENTS.md's AI/Backend rules, this repository only ever
/// calls the Callable Function and renders what comes back — it never
/// constructs prompts, holds API keys, or decides urgency locally.
abstract class VisitSummaryRepository {
  Future<VisitSummaryResult> generate({
    required List<Message> messages,
    required UrgencyLevel? finalUrgency,
  });
}

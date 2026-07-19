// lib/features/visit_summary/providers/visit_summary_provider.dart
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_theme.dart';
import '../../chat/models/message.dart';
import '../models/visit_summary_facts.dart';
import '../models/visit_summary_result.dart';
import '../repositories/callable_visit_summary_repository.dart';
import '../repositories/fixture_visit_summary_repository.dart';
import '../repositories/visit_summary_repository.dart';

/// Flip to false to wire the real backend once fixture-mode UI review is
/// complete — same convention as chat_provider.dart's
/// _useFixturesInDebug.
const bool _useFixturesInDebug = false;

final visitSummaryRepositoryProvider = Provider<VisitSummaryRepository>((ref) {
  if (kDebugMode && _useFixturesInDebug) {
    return FixtureVisitSummaryRepository();
  }
  return CallableVisitSummaryRepository();
});

/// Bundles the narrative result with the message ID it was generated
/// against — the staleness signal (design spec §5.5). generatedAtMessageId
/// is the last message's id at the moment generate() was called.
class VisitSummaryState {
  const VisitSummaryState({
    required this.result,
    required this.generatedAtMessageId,
  });

  final VisitSummaryResult result;
  final String generatedAtMessageId;
}

/// Idle until the user explicitly taps "Generate summary" — build()
/// never fires the narrative call itself (design spec §5.4: opening the
/// screen must cost zero API calls; the deterministic facts render
/// separately via VisitSummaryFacts.fromMessages, with no need for a
/// provider at all).
class VisitSummaryController extends AsyncNotifier<VisitSummaryState?> {
  @override
  FutureOr<VisitSummaryState?> build() => null;

  Future<void> generate({
    required List<Message> messages,
    required UrgencyLevel? finalUrgency,
  }) async {
    // Double-tap/quota guard — same instinct as ChatController.send's
    // chatIsSendingProvider check.
    if (state.isLoading) return;

    // Client-side half of the two-strip-points crisis design (spec §6):
    // strip before the request is even built, so crisis text never
    // leaves the device when the client is behaving correctly. The
    // server re-strips independently regardless (main.py's
    // _strip_crisis_exchanges) — this is defense-in-depth, not the only
    // enforcement point.
    final strippedMessages = stripCrisisExchanges(messages);
    final generatedAtMessageId = messages.isEmpty ? '' : messages.last.id;

    if (strippedMessages.isEmpty) {
      // Degenerate case: every assessment-shaped turn was a crisis turn,
      // so there's nothing left to summarize once crisis content is
      // stripped. Handled entirely locally rather than sending an empty
      // history to the backend: the server has its own independent
      // degenerate-case fallback (main.py's run_visit_summary_pipeline,
      // for a hypothetical non-compliant client that skips this strip),
      // but for THIS client the request would always arrive empty, so
      // the server's own Tagalog-vs-English heuristic for that fallback
      // line would always see empty text and always pick English —
      // producing a Tagalog crisis-mention banner directly above an
      // English "nothing else to report" line. Deciding the language
      // locally from the same signal VisitSummaryFacts already used for
      // the crisis-mention banner guarantees the two lines always agree,
      // and avoids a network round-trip for a conversation with nothing
      // to summarize.
      final facts = VisitSummaryFacts.fromMessages(messages);
      final isTagalog = facts.crisisMentionText == crisisMentionTl;
      state = AsyncData(
        VisitSummaryState(
          result: VisitSummaryResult(
            isError: false,
            summary: isTagalog
                ? visitSummaryNoContentTl
                : visitSummaryNoContentEn,
          ),
          generatedAtMessageId: generatedAtMessageId,
        ),
      );
      return;
    }

    state = const AsyncLoading();
    state = await AsyncValue.guard(() async {
      final result = await ref
          .read(visitSummaryRepositoryProvider)
          .generate(messages: strippedMessages, finalUrgency: finalUrgency);
      return VisitSummaryState(
        result: result,
        generatedAtMessageId: generatedAtMessageId,
      );
    });
  }
}

final visitSummaryControllerProvider =
    AsyncNotifierProvider<VisitSummaryController, VisitSummaryState?>(
      VisitSummaryController.new,
    );

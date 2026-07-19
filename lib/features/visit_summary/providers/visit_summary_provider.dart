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

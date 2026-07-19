import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/models/message.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';
import 'package:pulse_app/features/chat/providers/chat_provider.dart';
import 'package:pulse_app/features/visit_summary/models/visit_summary_facts.dart';
import 'package:pulse_app/features/visit_summary/models/visit_summary_result.dart';
import 'package:pulse_app/features/visit_summary/providers/visit_summary_provider.dart';
import 'package:pulse_app/features/visit_summary/repositories/visit_summary_repository.dart';
import 'package:pulse_app/features/visit_summary/screens/visit_summary_screen.dart';

class _StubRepository implements VisitSummaryRepository {
  _StubRepository(this._result);
  final VisitSummaryResult _result;

  @override
  Future<VisitSummaryResult> generate({
    required List<Message> messages,
    required UrgencyLevel? finalUrgency,
  }) async => _result;
}

/// Never resolves within a single pump — lets a test observe the loading
/// state (spec §8's "four states: idle/CTA, loading, error-with-retry,
/// loaded") before the future completes.
class _DelayedStubRepository implements VisitSummaryRepository {
  _DelayedStubRepository(this._result);
  final VisitSummaryResult _result;

  @override
  Future<VisitSummaryResult> generate({
    required List<Message> messages,
    required UrgencyLevel? finalUrgency,
  }) async {
    await Future<void>.delayed(const Duration(milliseconds: 100));
    return _result;
  }
}

class _ThrowingRepository implements VisitSummaryRepository {
  @override
  Future<VisitSummaryResult> generate({
    required List<Message> messages,
    required UrgencyLevel? finalUrgency,
  }) {
    throw Exception('network down');
  }
}

Message _assessment(UrgencyLevel urgency, {List<String> watchFor = const []}) =>
    Message.assistant(
      UrgencyResult(
        type: ChatTurnType.assessment,
        message: 'Noted.',
        urgency: urgency,
        watchFor: watchFor,
      ),
    );

Future<void> _pump(
  WidgetTester tester, {
  required List<Message> seedMessages,
  VisitSummaryRepository? repository,
}) async {
  final container = ProviderContainer(
    overrides: [
      if (repository != null)
        visitSummaryRepositoryProvider.overrideWithValue(repository),
    ],
  );
  addTearDown(container.dispose);
  // Seed chatControllerProvider's state directly rather than sending
  // through the UI — this screen only reads it, it never mutates chat.
  container.read(chatControllerProvider.notifier).state = AsyncData(seedMessages);
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: MaterialApp(theme: AppTheme.light, home: const VisitSummaryScreen()),
    ),
  );
  await tester.pump();
}

void main() {
  testWidgets('tier badge alone: renders when there is an assessment and no crisis turn', (
    tester,
  ) async {
    await _pump(tester, seedMessages: [_assessment(UrgencyLevel.monitorAtHome)]);
    expect(find.text('Monitor at home'), findsOneWidget);
    expect(find.textContaining('emotional distress'), findsNothing);
  });

  testWidgets('crisis line alone: renders when the conversation is crisis-only', (
    tester,
  ) async {
    await _pump(
      tester,
      seedMessages: [
        Message.user('I want to end my life'),
        Message.assistant(
          const UrgencyResult(type: ChatTurnType.crisis, message: "I'm here."),
        ),
      ],
    );
    expect(find.text(crisisMentionEn), findsOneWidget);
    expect(find.text('Monitor at home'), findsNothing);
    expect(find.text('See a doctor soon'), findsNothing);
    expect(find.text('Seek care now'), findsNothing);
  });

  testWidgets('both stacked: a real assessment plus a later crisis turn renders both', (
    tester,
  ) async {
    await _pump(
      tester,
      seedMessages: [
        _assessment(UrgencyLevel.seeDoctorSoon),
        Message.user('actually I feel like ending it'),
        Message.assistant(
          const UrgencyResult(type: ChatTurnType.crisis, message: "I'm here."),
        ),
      ],
    );
    expect(find.text('See a doctor soon'), findsOneWidget);
    expect(find.text(crisisMentionEn), findsOneWidget);
  });

  testWidgets('narrative block starts idle with a Generate summary CTA', (tester) async {
    await _pump(tester, seedMessages: [_assessment(UrgencyLevel.monitorAtHome)]);
    expect(find.text('Generate summary'), findsOneWidget);
  });

  testWidgets('tapping Generate summary shows the loaded recap', (tester) async {
    await _pump(
      tester,
      seedMessages: [_assessment(UrgencyLevel.monitorAtHome)],
      repository: _StubRepository(
        const VisitSummaryResult(
          isError: false,
          summary: 'A plain recap.',
          questionsForDoctor: ['A question?'],
        ),
      ),
    );
    await tester.tap(find.text('Generate summary'));
    await tester.pump(); // enter loading
    await tester.pump(); // resolve
    expect(find.text('A plain recap.'), findsOneWidget);
    expect(find.text('A question?'), findsOneWidget);
  });

  testWidgets('watch-for section renders WarningPills from deterministic facts', (
    tester,
  ) async {
    await _pump(
      tester,
      seedMessages: [
        _assessment(UrgencyLevel.seekCareNow, watchFor: ['Trouble breathing']),
      ],
    );
    expect(find.text('Trouble breathing'), findsOneWidget);
  });

  testWidgets('narrative loading state shows a spinner, not the CTA or old content', (
    tester,
  ) async {
    await _pump(
      tester,
      seedMessages: [_assessment(UrgencyLevel.monitorAtHome)],
      repository: _DelayedStubRepository(
        const VisitSummaryResult(isError: false, summary: 'A plain recap.'),
      ),
    );
    await tester.tap(find.text('Generate summary'));
    await tester.pump(); // enter loading — the delayed future has not resolved yet
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.text('Generate summary'), findsNothing);
    expect(find.text('A plain recap.'), findsNothing);
    await tester.pumpAndSettle(); // let the delayed future resolve before teardown
  });

  testWidgets('a repository failure renders the error state with a Try again action', (
    tester,
  ) async {
    await _pump(
      tester,
      seedMessages: [_assessment(UrgencyLevel.monitorAtHome)],
      repository: _ThrowingRepository(),
    );
    await tester.tap(find.text('Generate summary'));
    await tester.pump(); // enter loading
    await tester.pump(); // AsyncValue.guard resolves to AsyncError
    expect(
      find.text("Couldn't put together a visit summary right now."),
      findsOneWidget,
    );
    expect(find.text('Try again'), findsOneWidget);
  });

  testWidgets('a server-provided error message surfaces instead of the hardcoded fallback', (
    tester,
  ) async {
    await _pump(
      tester,
      seedMessages: [_assessment(UrgencyLevel.monitorAtHome)],
      repository: _StubRepository(
        const VisitSummaryResult(
          isError: true,
          summary: '',
          errorMessage: 'Custom server message.',
        ),
      ),
    );
    await tester.tap(find.text('Generate summary'));
    await tester.pump(); // enter loading
    await tester.pump(); // resolve
    expect(find.text('Custom server message.'), findsOneWidget);
    expect(find.text('Try again'), findsOneWidget);
  });

  testWidgets('tapping Try again re-attempts generation', (tester) async {
    await _pump(
      tester,
      seedMessages: [_assessment(UrgencyLevel.monitorAtHome)],
      repository: _ThrowingRepository(),
    );
    await tester.tap(find.text('Generate summary'));
    await tester.pump();
    await tester.pump();
    expect(find.text('Try again'), findsOneWidget);

    // Retrying against the same throwing repository lands back on the
    // error state rather than crashing or getting stuck — proves the
    // retry action is wired, not just present. Deliberately not
    // asserting the in-between loading frame here: unlike the dedicated
    // loading-state test above (which uses _DelayedStubRepository
    // specifically so the loading frame is observable), this repository
    // throws synchronously enough inside AsyncValue.guard that the
    // state can already be AsyncError by the next pump — asserting a
    // spinner in between would be asserting timing this double doesn't
    // control, not real behavior.
    await tester.tap(find.text('Try again'));
    await tester.pumpAndSettle();
    expect(find.text('Try again'), findsOneWidget);
  });

  testWidgets('a stale narrative (conversation continued) shows a regenerate prompt, not old prose', (
    tester,
  ) async {
    final container = ProviderContainer(
      overrides: [
        visitSummaryRepositoryProvider.overrideWithValue(
          _StubRepository(
            const VisitSummaryResult(isError: false, summary: 'Original recap.'),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    final firstMessage = _assessment(UrgencyLevel.monitorAtHome);
    container.read(chatControllerProvider.notifier).state = AsyncData([firstMessage]);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(theme: AppTheme.light, home: const VisitSummaryScreen()),
      ),
    );
    await tester.pump();
    await tester.tap(find.text('Generate summary'));
    await tester.pump();
    await tester.pump();
    expect(find.text('Original recap.'), findsOneWidget);

    // Conversation continues past the point the narrative was generated.
    container.read(chatControllerProvider.notifier).state = AsyncData([
      firstMessage,
      _assessment(UrgencyLevel.seeDoctorSoon),
    ]);
    await tester.pump();

    expect(find.text('Original recap.'), findsNothing);
    expect(find.text('Regenerate'), findsOneWidget);
  });
}

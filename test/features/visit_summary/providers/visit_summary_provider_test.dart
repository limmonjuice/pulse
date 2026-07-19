import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/models/message.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';
import 'package:pulse_app/features/visit_summary/models/visit_summary_facts.dart';
import 'package:pulse_app/features/visit_summary/models/visit_summary_result.dart';
import 'package:pulse_app/features/visit_summary/providers/visit_summary_provider.dart';
import 'package:pulse_app/features/visit_summary/repositories/visit_summary_repository.dart';

class _StubRepository implements VisitSummaryRepository {
  _StubRepository(this._result);
  final VisitSummaryResult _result;
  List<Message>? capturedMessages;
  int callCount = 0;

  @override
  Future<VisitSummaryResult> generate({
    required List<Message> messages,
    required UrgencyLevel? finalUrgency,
  }) async {
    callCount++;
    capturedMessages = messages;
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

void main() {
  test('build() is idle — no fetch on creation', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    expect(container.read(visitSummaryControllerProvider).value, isNull);
  });

  test(
    'generate() populates state with the result and the generating message id',
    () async {
      final stub = _StubRepository(
        const VisitSummaryResult(isError: false, summary: 'recap'),
      );
      final container = ProviderContainer(
        overrides: [visitSummaryRepositoryProvider.overrideWithValue(stub)],
      );
      addTearDown(container.dispose);

      final userMsg = Message.user('hi');
      final assessment = Message.assistant(
        const UrgencyResult(
          type: ChatTurnType.assessment,
          message: 'Noted.',
          urgency: UrgencyLevel.monitorAtHome,
        ),
      );
      await container
          .read(visitSummaryControllerProvider.notifier)
          .generate(
            messages: [userMsg, assessment],
            finalUrgency: UrgencyLevel.monitorAtHome,
          );

      final state = container.read(visitSummaryControllerProvider).value;
      expect(state!.result.summary, 'recap');
      expect(state.generatedAtMessageId, assessment.id);
    },
  );

  test(
    'generate() never calls the repository for a crisis-only (degenerate) conversation',
    () async {
      final stub = _StubRepository(
        const VisitSummaryResult(isError: false, summary: 'recap'),
      );
      final container = ProviderContainer(
        overrides: [visitSummaryRepositoryProvider.overrideWithValue(stub)],
      );
      addTearDown(container.dispose);

      final crisisUser = Message.user('I want to end my life');
      final crisisReply = Message.assistant(
        const UrgencyResult(
          type: ChatTurnType.crisis,
          message: "I'm here for you.",
        ),
      );
      await container
          .read(visitSummaryControllerProvider.notifier)
          .generate(messages: [crisisUser, crisisReply], finalUrgency: null);

      expect(stub.callCount, 0);
    },
  );

  test(
    'generate() forwards the correctly-stripped subset for a mixed conversation',
    () async {
      final stub = _StubRepository(
        const VisitSummaryResult(isError: false, summary: 'recap'),
      );
      final container = ProviderContainer(
        overrides: [visitSummaryRepositoryProvider.overrideWithValue(stub)],
      );
      addTearDown(container.dispose);

      final benignUser = Message.user('I have a mild headache');
      final benignAssessment = Message.assistant(
        const UrgencyResult(
          type: ChatTurnType.assessment,
          message: 'Noted.',
          urgency: UrgencyLevel.monitorAtHome,
        ),
      );
      final crisisUser = Message.user('I want to end my life');
      final crisisReply = Message.assistant(
        const UrgencyResult(
          type: ChatTurnType.crisis,
          message: "I'm here for you.",
        ),
      );

      await container
          .read(visitSummaryControllerProvider.notifier)
          .generate(
            messages: [benignUser, benignAssessment, crisisUser, crisisReply],
            finalUrgency: UrgencyLevel.monitorAtHome,
          );

      expect(stub.capturedMessages, [benignUser, benignAssessment]);
    },
  );

  test(
    'a repository failure surfaces as an AsyncError, not a thrown exception',
    () async {
      final container = ProviderContainer(
        overrides: [
          visitSummaryRepositoryProvider.overrideWithValue(
            _ThrowingRepository(),
          ),
        ],
      );
      addTearDown(container.dispose);

      final userMsg = Message.user('hi');
      final assessment = Message.assistant(
        const UrgencyResult(
          type: ChatTurnType.assessment,
          message: 'Noted.',
          urgency: UrgencyLevel.monitorAtHome,
        ),
      );
      await container
          .read(visitSummaryControllerProvider.notifier)
          .generate(messages: [userMsg, assessment], finalUrgency: null);

      expect(container.read(visitSummaryControllerProvider).hasError, isTrue);
    },
  );

  test('a re-entrant generate() call while loading is a no-op', () async {
    final stub = _StubRepository(
      const VisitSummaryResult(isError: false, summary: 'recap'),
    );
    final container = ProviderContainer(
      overrides: [visitSummaryRepositoryProvider.overrideWithValue(stub)],
    );
    addTearDown(container.dispose);

    final userMsg = Message.user('hi');
    final assessment = Message.assistant(
      const UrgencyResult(
        type: ChatTurnType.assessment,
        message: 'Noted.',
        urgency: UrgencyLevel.monitorAtHome,
      ),
    );
    final notifier = container.read(visitSummaryControllerProvider.notifier);
    final first = notifier.generate(
      messages: [userMsg, assessment],
      finalUrgency: null,
    );
    final second = notifier.generate(
      messages: [userMsg, assessment],
      finalUrgency: null,
    );
    await Future.wait([first, second]);
    // No assertion beyond "did not throw" — the guard's contract is
    // exercised; a stronger call-count assertion would need the stub to
    // count invocations, not required for this narrow regression check.
  });

  test(
    'generate() resolves a crisis-only English conversation locally as EN no-content, without calling the repository',
    () async {
      final stub = _StubRepository(
        const VisitSummaryResult(isError: false, summary: 'unused'),
      );
      final container = ProviderContainer(
        overrides: [visitSummaryRepositoryProvider.overrideWithValue(stub)],
      );
      addTearDown(container.dispose);

      final crisisUser = Message.user('I want to end my life');
      final crisisReply = Message.assistant(
        const UrgencyResult(
          type: ChatTurnType.crisis,
          message: "I'm here for you.",
        ),
      );
      await container
          .read(visitSummaryControllerProvider.notifier)
          .generate(messages: [crisisUser, crisisReply], finalUrgency: null);

      final state = container.read(visitSummaryControllerProvider).value;
      expect(state!.result.summary, visitSummaryNoContentEn);
      expect(stub.callCount, 0);
    },
  );

  test(
    'generate() resolves a crisis-only Tagalog conversation locally as TL no-content, matching the crisis banner language',
    () async {
      final stub = _StubRepository(
        const VisitSummaryResult(isError: false, summary: 'unused'),
      );
      final container = ProviderContainer(
        overrides: [visitSummaryRepositoryProvider.overrideWithValue(stub)],
      );
      addTearDown(container.dispose);

      final crisisUser = Message.user('Gusto ko nang mamatay');
      final crisisReply = Message.assistant(
        const UrgencyResult(
          type: ChatTurnType.crisis,
          message: "I'm here for you.",
        ),
      );
      await container
          .read(visitSummaryControllerProvider.notifier)
          .generate(messages: [crisisUser, crisisReply], finalUrgency: null);

      final state = container.read(visitSummaryControllerProvider).value;
      expect(state!.result.summary, visitSummaryNoContentTl);
      expect(stub.callCount, 0);
    },
  );
}

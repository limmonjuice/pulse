import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/models/message.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';
import 'package:pulse_app/features/visit_summary/models/visit_summary_facts.dart';

Message _assessment({
  required UrgencyLevel urgency,
  List<String> findings = const [],
  List<String> watchFor = const [],
  List<String> selfCare = const [],
  List<String> monitoring = const [],
}) => Message.assistant(
  UrgencyResult(
    type: ChatTurnType.assessment,
    message: 'assessment',
    urgency: urgency,
    findings: findings,
    watchFor: watchFor,
    selfCare: selfCare,
    monitoring: monitoring,
  ),
);

Message _crisis() => Message.assistant(
  const UrgencyResult(type: ChatTurnType.crisis, message: 'crisis reply'),
);

void main() {
  group('VisitSummaryFacts.fromMessages', () {
    test('empty conversation yields all-null/empty facts', () {
      final facts = VisitSummaryFacts.fromMessages([]);
      expect(facts.finalUrgency, isNull);
      expect(facts.hadCrisisTurn, isFalse);
      expect(facts.findings, isEmpty);
    });

    test('single assessment sets final and initial urgency to the same tier', () {
      final facts = VisitSummaryFacts.fromMessages([
        Message.user('I have a headache'),
        _assessment(urgency: UrgencyLevel.monitorAtHome),
      ]);
      expect(facts.finalUrgency, UrgencyLevel.monitorAtHome);
      expect(facts.initialUrgency, UrgencyLevel.monitorAtHome);
      expect(facts.urgencyChanged, isFalse);
    });

    test('multi-turn progression: urgencyChanged is first-vs-last, not "ever fluctuated"', () {
      final facts = VisitSummaryFacts.fromMessages([
        _assessment(urgency: UrgencyLevel.monitorAtHome),
        _assessment(urgency: UrgencyLevel.seeDoctorSoon),
        _assessment(urgency: UrgencyLevel.monitorAtHome),
      ]);
      expect(facts.initialUrgency, UrgencyLevel.monitorAtHome);
      expect(facts.finalUrgency, UrgencyLevel.monitorAtHome);
      expect(facts.urgencyChanged, isFalse);
    });

    test('a genuine progression sets urgencyChanged true', () {
      final facts = VisitSummaryFacts.fromMessages([
        _assessment(urgency: UrgencyLevel.monitorAtHome),
        _assessment(urgency: UrgencyLevel.seeDoctorSoon),
      ]);
      expect(facts.urgencyChanged, isTrue);
    });

    test('crisis-only conversation: finalUrgency null, hadCrisisTurn true', () {
      final facts = VisitSummaryFacts.fromMessages([
        Message.user('I want to end my life'),
        _crisis(),
      ]);
      expect(facts.finalUrgency, isNull);
      expect(facts.hadCrisisTurn, isTrue);
      expect(facts.crisisMentionText, isNotNull);
    });

    test('mixed crisis+assessment: crisis excluded from aggregates, hadCrisisTurn set', () {
      final facts = VisitSummaryFacts.fromMessages([
        _assessment(urgency: UrgencyLevel.monitorAtHome, findings: ['mild headache']),
        Message.user('actually I feel like ending it'),
        _crisis(),
      ]);
      expect(facts.finalUrgency, UrgencyLevel.monitorAtHome);
      expect(facts.hadCrisisTurn, isTrue);
      expect(facts.findings, ['mild headache']);
    });

    test('findings/watchFor/selfCare/monitoring are deduped across turns', () {
      final facts = VisitSummaryFacts.fromMessages([
        _assessment(urgency: UrgencyLevel.monitorAtHome, findings: ['fever']),
        _assessment(urgency: UrgencyLevel.monitorAtHome, findings: ['fever', 'cough']),
      ]);
      expect(facts.findings, unorderedEquals(['fever', 'cough']));
    });

    test('TL-keyword heuristic: a Taglish preceding turn selects the TL crisis line', () {
      final facts = VisitSummaryFacts.fromMessages([
        Message.user('Gusto ko nang mamatay'),
        _crisis(),
      ]);
      expect(facts.crisisMentionText, crisisMentionTl);
    });

    test('TL-keyword heuristic: an all-English conversation defaults to EN', () {
      final facts = VisitSummaryFacts.fromMessages([
        Message.user('I want to end my life'),
        _crisis(),
      ]);
      expect(facts.crisisMentionText, crisisMentionEn);
    });

    test(
      'mixed conversation: the latest non-crisis assessment\'s language wins over a later crisis turn',
      () {
        final facts = VisitSummaryFacts.fromMessages([
          Message.user('Gusto ko nang mamatay'),
          _crisis(),
          Message.user('I have a mild headache'),
          _assessment(urgency: UrgencyLevel.monitorAtHome),
        ]);
        expect(facts.crisisMentionText, crisisMentionEn);
      },
    );

    test('a leading crisis turn with nothing before it does not crash and defaults sensibly', () {
      final facts = VisitSummaryFacts.fromMessages([
        _crisis(),
        Message.user("I'm okay now"),
      ]);
      expect(facts.hadCrisisTurn, isTrue);
      expect(facts.crisisMentionText, isNotNull);
    });
  });

  group('stripCrisisExchanges', () {
    test('removes the crisis reply and its preceding user turn', () {
      final userCrisis = Message.user('I want to end my life');
      final crisisReply = _crisis();
      final benignUser = Message.user('actually just a headache');
      final benignAssessment = _assessment(urgency: UrgencyLevel.monitorAtHome);
      final stripped = stripCrisisExchanges([
        userCrisis,
        crisisReply,
        benignUser,
        benignAssessment,
      ]);
      expect(stripped, [benignUser, benignAssessment]);
    });

    test('no-op when there is no crisis turn', () {
      final messages = [
        Message.user('I have a headache'),
        _assessment(urgency: UrgencyLevel.monitorAtHome),
      ];
      expect(stripCrisisExchanges(messages), messages);
    });

    test('drops all contiguous preceding user turns, not just the nearest one', () {
      // Mirrors main.py's test_strip_crisis_exchanges_drops_all_contiguous_preceding_user_turns
      // (Task 6) — a malformed/tampered history with two consecutive
      // user turns before the crisis reply must not leak the earlier one.
      final stripped = stripCrisisExchanges([
        Message.user('I want to kill myself tonight'),
        Message.user('sorry, ignore that, just kidding'),
        _crisis(),
      ]);
      expect(stripped, isEmpty);
    });

    test('handles a leading crisis turn with no preceding turn to drop', () {
      final crisisReply = _crisis();
      final benignUser = Message.user("I'm okay now");
      final stripped = stripCrisisExchanges([crisisReply, benignUser]);
      expect(stripped, [benignUser]);
    });
  });
}

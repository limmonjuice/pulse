// test/features/chat/fixtures/chat_fixtures_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/fixtures/chat_fixtures.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';

void main() {
  test('there are exactly 7 fixtures', () {
    expect(chatFixtures.length, 7);
  });

  test('every fixture parses via fromJson without becoming unparseable', () {
    for (final fixture in chatFixtures) {
      final result = UrgencyResult.fromJson(fixture);
      expect(
        result.type,
        isNot(ChatTurnType.unparseable),
        reason: 'fixture failed to parse: $fixture',
      );
    }
  });

  test('fixture 1 is a question with quick replies', () {
    final result = UrgencyResult.fromJson(chatFixtures[0]);
    expect(result.type, ChatTurnType.question);
    expect(result.quickReplies.length, greaterThanOrEqualTo(2));
  });

  test(
    'fixture 2 is a see_doctor_soon assessment with every section populated',
    () {
      final result = UrgencyResult.fromJson(chatFixtures[1]);
      expect(result.type, ChatTurnType.assessment);
      expect(result.urgency, UrgencyLevel.seeDoctorSoon);
      expect(result.selfCare, isNotEmpty);
      expect(result.monitoring, isNotEmpty);
      expect(result.watchFor, isNotEmpty);
      expect(result.encouragement, isNotNull);
    },
  );

  test(
    'fixture 3 is a monitor_at_home assessment with every section populated',
    () {
      final result = UrgencyResult.fromJson(chatFixtures[2]);
      expect(result.type, ChatTurnType.assessment);
      expect(result.urgency, UrgencyLevel.monitorAtHome);
      expect(result.selfCare, isNotEmpty);
      expect(result.monitoring, isNotEmpty);
      expect(result.watchFor, isNotEmpty);
    },
  );

  test(
    'fixture 4 is a seek_care_now assessment with the graceful-empty sections',
    () {
      final result = UrgencyResult.fromJson(chatFixtures[3]);
      expect(result.type, ChatTurnType.assessment);
      expect(result.urgency, UrgencyLevel.seekCareNow);
      expect(result.selfCare, isEmpty);
      expect(result.monitoring, isEmpty);
      expect(result.watchFor, isNotEmpty);
    },
  );

  test('fixture 4b is a conversation turn with a keep directive and an '
      'active guidance state (engine v2)', () {
    final result = UrgencyResult.fromJson(chatFixtures[4]);
    expect(result.type, ChatTurnType.conversation);
    expect(result.cardAction, CardAction.keep);
    expect(result.conversationState, isNotNull);
    expect(result.conversationState!.urgency, UrgencyLevel.seekCareNow);
    expect(result.conversationState!.assessmentActive, isTrue);
  });

  test('fixture 5 is a crisis turn', () {
    final result = UrgencyResult.fromJson(chatFixtures[5]);
    expect(result.type, ChatTurnType.crisis);
  });

  test('fixture 6 is an error turn', () {
    final result = UrgencyResult.fromJson(chatFixtures[6]);
    expect(result.type, ChatTurnType.error);
  });
}

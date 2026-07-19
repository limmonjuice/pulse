import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/models/message.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';
import 'package:pulse_app/features/visit_summary/repositories/callable_visit_summary_repository.dart';

void main() {
  group('buildRequestData', () {
    test('serializes history via toHistoryJson and the urgency tier as a wire string', () {
      final messages = [
        Message.user('I have a headache'),
        Message.assistant(
          const UrgencyResult(
            type: ChatTurnType.assessment,
            message: 'Noted.',
            urgency: UrgencyLevel.monitorAtHome,
            findings: ['mild headache'],
          ),
        ),
      ];
      final data = CallableVisitSummaryRepository.buildRequestData(
        messages: messages,
        finalUrgency: UrgencyLevel.monitorAtHome,
      );
      expect(data['history'], hasLength(2));
      expect(data['final_urgency'], 'monitor_at_home');
    });

    test('a null finalUrgency serializes to a null final_urgency', () {
      final data = CallableVisitSummaryRepository.buildRequestData(
        messages: const [],
        finalUrgency: null,
      );
      expect(data['final_urgency'], isNull);
    });
  });
}

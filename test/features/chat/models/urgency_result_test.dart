import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';

void main() {
  group('UrgencyResult.fromJson', () {
    test('parses a well-formed question payload', () {
      final result = UrgencyResult.fromJson({
        'type': 'question',
        'message': 'How high has your temperature been?',
        'quick_replies': ['Under 38°', '38–39°', 'Over 39°'],
        'urgency': null,
        'explanation': null,
        'watch_for': [],
        'next_step': null,
        'possibilities_mentioned': false,
        'self_care': [],
        'monitoring': [],
        'encouragement': null,
      });

      expect(result.type, ChatTurnType.question);
      expect(result.message, 'How high has your temperature been?');
      expect(result.quickReplies, ['Under 38°', '38–39°', 'Over 39°']);
      expect(result.urgency, isNull);
    });

    test(
      'parses a well-formed assessment payload with a valid urgency tier',
      () {
        final result = UrgencyResult.fromJson({
          'type': 'assessment',
          'message': 'msg',
          'quick_replies': [],
          'urgency': 'see_doctor_soon',
          'explanation': 'exp',
          'watch_for': ['a', 'b'],
          'next_step': 'next',
          'possibilities_mentioned': true,
          'self_care': ['rest'],
          'monitoring': ['watch it'],
          'encouragement': 'you got this',
        });

        expect(result.type, ChatTurnType.assessment);
        expect(result.urgency, UrgencyLevel.seeDoctorSoon);
        expect(result.watchFor, ['a', 'b']);
        expect(result.selfCare, ['rest']);
        expect(result.monitoring, ['watch it']);
        expect(result.encouragement, 'you got this');
      },
    );

    test(
      'ignores unknown keys (e.g. possibilities_mentioned) without choking',
      () {
        final result = UrgencyResult.fromJson({
          'type': 'crisis',
          'message': 'msg',
          'quick_replies': [],
          'urgency': null,
          'explanation': null,
          'watch_for': [],
          'next_step': null,
          'possibilities_mentioned': false,
          'self_care': [],
          'monitoring': [],
          'encouragement': null,
          'some_future_field': {'nested': true},
        });

        expect(result.type, ChatTurnType.crisis);
      },
    );

    test(
      'an unrecognized type string falls back to unparseable, never throws',
      () {
        final result = UrgencyResult.fromJson({
          'type': 'something_new',
          'message': 'msg',
        });

        expect(result.type, ChatTurnType.unparseable);
      },
    );

    test('a missing message field falls back to unparseable, never throws', () {
      final result = UrgencyResult.fromJson({'type': 'question'});

      expect(result.type, ChatTurnType.unparseable);
    });

    test('completely malformed input (wrong types) never throws', () {
      expect(
        () => UrgencyResult.fromJson({'type': 42, 'message': null}),
        returnsNormally,
      );
    });

    test('a non-string value for explanation/next_step/encouragement is '
        'dropped, not thrown', () {
      expect(
        () => UrgencyResult.fromJson({
          'type': 'assessment',
          'message': 'm',
          'urgency': 'see_doctor_soon',
          'explanation': 42,
          'next_step': {'nested': true},
          'encouragement': ['a', 'list'],
        }),
        returnsNormally,
      );
    });

    test(
      'type == assessment with a missing/invalid urgency falls back to '
      'unparseable rather than crashing a urgency-tier renderer downstream',
      () {
        final result = UrgencyResult.fromJson({
          'type': 'assessment',
          'message': 'msg',
          'urgency': 'not_a_real_tier',
        });

        expect(result.type, ChatTurnType.unparseable);
      },
    );
  });

  group('UrgencyResult.toJson', () {
    test('round-trips an assessment payload', () {
      const result = UrgencyResult(
        type: ChatTurnType.assessment,
        message: 'msg',
        urgency: UrgencyLevel.seekCareNow,
        selfCare: ['rest'],
      );

      final json = result.toJson();
      final roundTripped = UrgencyResult.fromJson(json);

      expect(roundTripped.type, ChatTurnType.assessment);
      expect(roundTripped.urgency, UrgencyLevel.seekCareNow);
      expect(roundTripped.selfCare, ['rest']);
    });
  });
}

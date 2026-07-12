// test/core/constants/crisis_resources_test.dart
//
// Permanent regression guard: if crisis_resources.dart is ever
// accidentally reset to stub/placeholder data during a future refactor,
// this must fail loudly rather than let it silently ship. This is the
// single highest-stakes data file in the app — a hotline list shown to a
// user the app has just flagged as possibly in crisis.
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/constants/crisis_resources.dart';

final _stubPatterns = [
  RegExp('TODO', caseSensitive: false),
  RegExp('XXX', caseSensitive: false),
  RegExp('FIXME', caseSensitive: false),
  RegExp('PLACEHOLDER', caseSensitive: false),
  RegExp(r'555-'), // classic fictional/placeholder phone prefix
  RegExp(r'0000[-\s]?000[-\s]?0000'),
  RegExp(r'^0+$'), // a value that's literally all zeros
];

void main() {
  test('crisisResources is not empty', () {
    expect(crisisResources, isNotEmpty);
  });

  test('every resource has a non-empty name and at least one contact', () {
    for (final resource in crisisResources) {
      expect(resource.name.trim(), isNotEmpty);
      expect(resource.contacts, isNotEmpty);
    }
  });

  test(
    'no resource name, contact value, or contact label matches a known stub/placeholder pattern',
    () {
      for (final resource in crisisResources) {
        for (final pattern in _stubPatterns) {
          expect(
            resource.name,
            isNot(matches(pattern)),
            reason:
                '"${resource.name}" looks like a stub value (matched $pattern)',
          );
        }
        for (final contact in resource.contacts) {
          expect(contact.value.trim(), isNotEmpty);
          for (final pattern in _stubPatterns) {
            expect(
              contact.value,
              isNot(matches(pattern)),
              reason:
                  '"${contact.value}" (${resource.name}) looks like a stub value (matched $pattern)',
            );
            if (contact.label != null) {
              expect(
                contact.label,
                isNot(matches(pattern)),
                reason:
                    '"${contact.label}" (${resource.name}) looks like a stub value (matched $pattern)',
              );
            }
          }
        }
      }
    },
  );

  test(
    'every call/text contact has a plausible PH number length (short code or 7+ digits)',
    () {
      for (final resource in crisisResources) {
        for (final contact in resource.contacts) {
          if (contact.type == ContactType.email) continue;
          final digits = contact.value.replaceAll(RegExp(r'[^0-9]'), '');
          expect(
            digits.length,
            greaterThanOrEqualTo(4),
            reason:
                '"${contact.value}" (${resource.name}) has too few digits to be a real number',
          );
        }
      }
    },
  );

  test('every email contact looks like an email address', () {
    for (final resource in crisisResources) {
      for (final contact in resource.contacts) {
        if (contact.type != ContactType.email) continue;
        expect(contact.value, contains('@'));
        expect(contact.value, contains('.'));
      }
    }
  });
}

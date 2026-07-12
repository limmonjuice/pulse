// lib/core/constants/crisis_resources.dart

/// How a [CrisisContact] is reached — determines both its icon and which
/// url_launcher scheme (tel: / sms: / mailto:) its tap action uses.
enum ContactType { call, text, email }

/// A single way to reach a [CrisisResource] — e.g. one phone number, one
/// SMS line, or one email address. Some resources list several numbers
/// (different carriers, different areas); each gets its own row.
class CrisisContact {
  const CrisisContact({required this.type, required this.value, this.label});

  final ContactType type;

  /// The raw number or address as given by the source, e.g.
  /// "0917-899-8727" or "wisupport@dswd.gov.ph" — kept exactly as
  /// provided (not reformatted/re-coded to a different dialing format)
  /// so it also displays correctly.
  final String value;

  /// Optional disambiguator shown alongside [value], e.g. "USAP",
  /// "Globe", "Smart" — some resources list multiple numbers and this
  /// says which one applies to which case.
  final String? label;

  /// The URI passed to url_launcher: strips visual separators
  /// (spaces/dashes/parens) from [value] for tel:/sms:, uses [value]
  /// verbatim for mailto:.
  Uri get uri {
    switch (type) {
      case ContactType.call:
        return Uri.parse('tel:$_digitsOnly');
      case ContactType.text:
        return Uri.parse('sms:$_digitsOnly');
      case ContactType.email:
        return Uri.parse('mailto:$value');
    }
  }

  String get _digitsOnly => value.replaceAll(RegExp(r'[^0-9+]'), '');
}

/// A crisis-support line shown on the Chat screen's crisis card, grouped
/// under one name with one or more ways to reach it.
class CrisisResource {
  const CrisisResource({required this.name, required this.contacts});

  final String name;
  final List<CrisisContact> contacts;
}

// Verified 2026-07-12 — see LAUNCH_BLOCKERS.md. NCMH cross-checked
// against ncmh.gov.ph; In Touch/Hopeline/DSWD from owner research.
// Re-verify periodically: PH crisis-line numbers and availability do
// change.
const List<CrisisResource> crisisResources = [
  CrisisResource(
    name: 'National Center for Mental Health (NCMH) Crisis Hotline (24/7)',
    contacts: [
      CrisisContact(type: ContactType.call, value: '1553'),
      CrisisContact(
        type: ContactType.call,
        value: '0917-899-8727',
        label: 'USAP',
      ),
      CrisisContact(
        type: ContactType.call,
        value: '(02) 7989-8727',
        label: 'USAP, some landline areas',
      ),
    ],
  ),
  CrisisResource(
    name: 'In Touch Community Services Crisis Line (24/7)',
    contacts: [
      CrisisContact(type: ContactType.call, value: '(02) 8893-7603'),
      CrisisContact(type: ContactType.call, value: '0917-800-1123'),
      CrisisContact(type: ContactType.call, value: '0919-056-0709'),
      CrisisContact(type: ContactType.call, value: '0922-893-8944'),
    ],
  ),
  CrisisResource(
    name: 'Hopeline Philippines',
    contacts: [
      CrisisContact(
        type: ContactType.call,
        value: '(02) 8804-4673',
        label: 'HOPE',
      ),
      CrisisContact(
        type: ContactType.call,
        value: '0917-558-4673',
        label: 'Globe',
      ),
      CrisisContact(
        type: ContactType.call,
        value: '0918-873-4673',
        label: 'Smart',
      ),
    ],
  ),
  CrisisResource(
    name: 'DSWD WiSUPPORT',
    contacts: [
      CrisisContact(type: ContactType.text, value: '0918-912-2813'),
      CrisisContact(type: ContactType.email, value: 'wisupport@dswd.gov.ph'),
    ],
  ),
];

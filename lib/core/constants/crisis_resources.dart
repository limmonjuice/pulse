// lib/core/constants/crisis_resources.dart

/// A crisis-support hotline shown on the Chat screen's crisis card.
class CrisisResource {
  const CrisisResource({
    required this.name,
    required this.number,
    required this.phoneUri,
  });

  /// Display name, e.g. "National Center for Mental Health Crisis Hotline".
  final String name;

  /// Display text for how to reach it, e.g. "Call or text 1553".
  final String number;

  /// tel: URI passed to url_launcher.
  final String phoneUri;
}

// TODO(owner): replace with verified current PH hotlines before any real
// user sees this. These are placeholder entries only — numbers and
// availability for Philippine crisis lines change, and neither has been
// re-verified for this pass.
const List<CrisisResource> crisisResources = [
  CrisisResource(
    name: 'National Center for Mental Health Crisis Hotline',
    number: 'Call 1553',
    phoneUri: 'tel:1553',
  ),
  CrisisResource(
    name: 'Hopeline PH',
    number: 'Call 0917-558-4673',
    phoneUri: 'tel:+639175584673',
  ),
];

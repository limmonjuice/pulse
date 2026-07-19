// lib/features/visit_summary/models/visit_summary_facts.dart
import '../../../core/theme/app_theme.dart';
import '../../chat/models/message.dart';
import '../../chat/models/urgency_result.dart';

/// Function words/particles used only to pick between the EN/TL
/// crisis-mention line below — mirrors fallbacks.py's
/// message_signals_tagalog heuristic on the Python side (kept as its own
/// Dart copy rather than shared cross-language). Optimized for precision
/// over recall: default to English unless a clearly Filipino word is
/// present.
const Set<String> _tagalogMarkerWords = {
  'ako',
  'ikaw',
  'siya',
  'kami',
  'tayo',
  'kayo',
  'sila',
  'ko',
  'mo',
  'niya',
  'namin',
  'natin',
  'ninyo',
  'nila',
  'ang',
  'mga',
  'yung',
  'yun',
  'ito',
  'iyon',
  'niyan',
  'nito',
  'hindi',
  'wala',
  'meron',
  'mayroon',
  'ba',
  'naman',
  'lang',
  'din',
  'rin',
  'po',
  'opo',
  'paano',
  'bakit',
  'saan',
  'kailan',
  'sino',
  'kasi',
  'tapos',
  'kanina',
  'kagabi',
  'bukas',
  'kahapon',
};

final RegExp _wordPattern = RegExp(r"[A-Za-z']+");

bool _looksTagalog(String text) {
  final words = _wordPattern
      .allMatches(text)
      .map((m) => m.group(0)!.toLowerCase())
      .toSet();
  return words.intersection(_tagalogMarkerWords).isNotEmpty;
}

/// AGENT-DRAFTED — PENDING OWNER READ-ALOUD (design spec §6). Not final
/// copy until the Tagalog line has been read aloud and approved — do not
/// treat this draft as shippable.
const String crisisMentionEn =
    'This conversation included a moment of emotional distress — '
    'consider mentioning it to your doctor.';
const String crisisMentionTl =
    'May sandali ng matinding pag-aalala sa kausapang ito — '
    'makabubuting banggitin din ito sa iyong doktor.';

/// Deterministic, client-side facts derived from the current in-memory
/// conversation — zero network cost, always renders regardless of the
/// narrative call's availability (design spec §5.1, §7).
class VisitSummaryFacts {
  const VisitSummaryFacts({
    required this.finalUrgency,
    required this.initialUrgency,
    required this.urgencyChanged,
    required this.hadCrisisTurn,
    required this.crisisMentionText,
    this.findings = const [],
    this.watchFor = const [],
    this.selfCare = const [],
    this.monitoring = const [],
  });

  /// Null if every assessment-shaped turn in the conversation was a
  /// crisis turn — crisis turns are excluded from every aggregate below.
  final UrgencyLevel? finalUrgency;
  final UrgencyLevel? initialUrgency;

  /// First-vs-last, not "did it ever fluctuate mid-conversation".
  final bool urgencyChanged;

  final bool hadCrisisTurn;

  /// The EN or TL crisis-mention line to render (crisisMentionEn /
  /// crisisMentionTl), or null when [hadCrisisTurn] is false.
  final String? crisisMentionText;

  final List<String> findings;
  final List<String> watchFor;
  final List<String> selfCare;
  final List<String> monitoring;

  factory VisitSummaryFacts.fromMessages(List<Message> messages) {
    UrgencyLevel? initial;
    UrgencyLevel? current;
    final findings = <String>{};
    final watchFor = <String>{};
    final selfCare = <String>{};
    final monitoring = <String>{};
    var hadCrisisTurn = false;
    // Precedence (design spec §6): the latest non-crisis assessment's
    // language wins over a later crisis turn's — the crisis-only
    // fallback applies only when no non-crisis assessment ever occurred.
    String? assessmentLanguageSource;
    String? crisisOnlyLanguageSource;

    for (var i = 0; i < messages.length; i++) {
      final payload = messages[i].payload;
      if (payload == null) continue;

      if (payload.type == ChatTurnType.crisis) {
        hadCrisisTurn = true;
        if (i > 0 && messages[i - 1].role == MessageRole.user) {
          crisisOnlyLanguageSource = messages[i - 1].text;
        }
        continue;
      }
      if (payload.type != ChatTurnType.assessment) continue;

      initial ??= payload.urgency;
      current = payload.urgency;
      findings.addAll(payload.findings);
      watchFor.addAll(payload.watchFor);
      selfCare.addAll(payload.selfCare);
      monitoring.addAll(payload.monitoring);
      if (i > 0 && messages[i - 1].role == MessageRole.user) {
        assessmentLanguageSource = messages[i - 1].text;
      }
    }

    String? crisisMentionText;
    if (hadCrisisTurn) {
      final source = assessmentLanguageSource ?? crisisOnlyLanguageSource ?? '';
      crisisMentionText = _looksTagalog(source)
          ? crisisMentionTl
          : crisisMentionEn;
    }

    return VisitSummaryFacts(
      finalUrgency: current,
      initialUrgency: initial,
      urgencyChanged: initial != null && current != null && initial != current,
      hadCrisisTurn: hadCrisisTurn,
      crisisMentionText: crisisMentionText,
      findings: findings.toList(),
      watchFor: watchFor.toList(),
      selfCare: selfCare.toList(),
      monitoring: monitoring.toList(),
    );
  }
}

/// Removes each assistant turn with type == ChatTurnType.crisis and
/// every contiguous user turn immediately preceding it — the
/// client-side half of the two-strip-points design (design spec §6).
/// Mirrors main.py's _strip_crisis_exchanges exactly, including its
/// walk-back-through-all-consecutive-user-turns fix (functions/main.py
/// commit 755ba64, applied after Task 6's code review found that
/// stripping only the single nearest preceding turn under-strips a
/// malformed/tampered history with two or more consecutive user turns
/// before the crisis reply). A well-formed history has exactly one user
/// turn before a crisis reply, but this re-strip doesn't assume the
/// history it's given is well-formed. Used by VisitSummaryController
/// before sending the request; NOT used by VisitSummaryFacts.fromMessages
/// above, which needs the original, unstripped messages to detect
/// hadCrisisTurn in the first place.
List<Message> stripCrisisExchanges(List<Message> messages) {
  final dropIndices = <int>{};
  for (var i = 0; i < messages.length; i++) {
    if (messages[i].payload?.type == ChatTurnType.crisis) {
      dropIndices.add(i);
      var j = i - 1;
      while (j >= 0 && messages[j].role == MessageRole.user) {
        dropIndices.add(j);
        j--;
      }
    }
  }
  return [
    for (var i = 0; i < messages.length; i++)
      if (!dropIndices.contains(i)) messages[i],
  ];
}

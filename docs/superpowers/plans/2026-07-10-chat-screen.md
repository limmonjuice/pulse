# Chat Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Pulse's real Chat screen — models, fixtures, widgets, state, and wiring — matching the approved `Pulse Chat.dc.html` mockup and the spec at `docs/superpowers/specs/2026-07-10-chat-screen-design.md`, fixture-first with live wiring behind a debug flag.

**Architecture:** Two typed models (`Message`, `UrgencyResult`) parse the callable's JSON contract defensively (never throw). A `ChatRepository` interface has two implementations — `FixtureChatRepository` (cycles 6 hand-copied payloads, zero network) and `CallableChatRepository` (`cloud_functions`, `asia-southeast1`) — selected by a `kDebugMode` const. `ChatController` (`AsyncNotifier<List<Message>>`) owns the turn list; `ChatScreen` renders each turn through one of six widgets chosen by `UrgencyResult.type` and crisis-lock position. No Firestore this pass.

**Tech Stack:** Flutter, `flutter_riverpod` (manual providers, no code-gen — matches `auth_provider.dart`), `cloud_functions`, `url_launcher` (new, owner-approved), existing `app_theme.dart` tokens plus a documented set of additions.

---

## Before you start

Read, in this order:
1. `AGENTS.md` (project rules — especially the AI/Backend and Styling sections)
2. `docs/superpowers/specs/2026-07-10-chat-screen-design.md` (the approved spec — this plan implements it verbatim except where noted below)
3. `lib/core/theme/app_theme.dart` (existing tokens)
4. `lib/features/auth/providers/auth_provider.dart` and `lib/features/auth/repositories/auth_repository.dart` (the Riverpod/repository pattern every provider/repository below follows exactly)

**Three refinements made while writing this plan, beyond the spec** (all flagged per this project's "flag rather than silently decide" discipline — none change any user-observable behavior described in the spec, so none warranted re-opening the spec, but are recorded here for the same audit-trail reason the spec itself gives):

1. **Two more shadow tokens needed.** Writing the chat bubble widget surfaced that the mockup's user-bubble shadow (`0 6px 16px rgba(111,168,181,.28)`) and Pulse-bubble shadow (`0 6px 16px rgba(80,100,100,.08)`) aren't covered by any existing or spec'd token. Resolved the same way as the CTA-radius call in the spec: the Pulse-bubble shadow is close enough to the existing `AppShadows.card` (`0 8px 22px rgba(80,100,100,.08)` — same color/opacity, blur/offset within a few px) to reuse rather than duplicate. The user-bubble shadow has no close existing token (its color is exactly `AppColors.primary` at 28% opacity, distinct from `cardRaised`'s 16%), so it gets a new `AppShadows.userBubble` token — added in Task 4 below, with a one-line backfill added to `PULSE_DESIGN_SYSTEM.md` §8 in the same task, matching how the spec's original nine tokens were documented.
2. **`checkedSelfCare` lives on `Message` via `ChatController`, not local `State`.** The spec says the checklist state "lives in the message's UI state" without specifying the mechanism. Implemented as a field on `Message` (`Set<int> checkedSelfCare`, mutated only via `ChatController.toggleSelfCare`), not a separate map in `ChatScreen`'s local `State` — keeps `ChatController` the single source of truth per AGENTS.md's Riverpod rules ("local `StatefulWidget` state only for genuinely widget-local, ephemeral UI"), rather than splitting turn-list state across two places.
3. **Crisis lock is a derived computation, not a stored flag.** The spec describes `ChatController` setting "a client-side-mirrored `isCrisisLocked` flag." Task 17 instead computes `firstCrisisIndex = messages.indexWhere((m) => m.payload?.type == ChatTurnType.crisis)` inline in `ChatScreen.build()` on every render — no flag stored anywhere. Same observable behavior (a message is either the first crisis card or, if crisis-typed and later, the soft bubble variant — tier styling is never shown for a crisis-typed message), but simpler: one less piece of mutable state to keep in sync, and it composes correctly with fixture-mode's cycling (a stored sticky "lock everything after the first crisis" flag would have forced every later fixture — including the unrelated error fixture — into crisis presentation too, which would have broken Task 18's manual fixture walkthrough).

**A known, deliberate gap this plan does NOT close:** `CallableChatRepository` cannot be integration-tested against a live/emulated Firebase project in this pass (no `mockito`/`mocktail` dev-dependency exists, and adding one needs the same ask-first treatment as any package per AGENTS.md — not requested here since fixture mode is the reviewable path for this pass). Task 8 tests only the pure, Firebase-free `buildRequestData` helper; the actual `httpsCallable(...).call(...)` line is exercised only by manual live-mode QA, which is explicitly out of scope this pass (see spec, "Explicitly out of scope").

---

### Task 1: `UrgencyResult` model

**Files:**
- Create: `lib/features/chat/models/urgency_result.dart`
- Test: `test/features/chat/models/urgency_result_test.dart`

- [ ] **Step 1: Write the failing tests**

```dart
// test/features/chat/models/urgency_result_test.dart
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

    test('parses a well-formed assessment payload with a valid urgency tier', () {
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
    });

    test('ignores unknown keys (e.g. possibilities_mentioned) without choking', () {
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
    });

    test('an unrecognized type string falls back to unparseable, never throws', () {
      final result = UrgencyResult.fromJson({
        'type': 'something_new',
        'message': 'msg',
      });

      expect(result.type, ChatTurnType.unparseable);
    });

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `flutter test test/features/chat/models/urgency_result_test.dart`
Expected: FAIL — `urgency_result.dart` doesn't exist yet (import error).

- [ ] **Step 3: Write the implementation**

```dart
// lib/features/chat/models/urgency_result.dart
import '../../../core/theme/app_theme.dart' show UrgencyLevel;

/// The four wire types the backend can send, plus [unparseable] — a
/// client-only fallback for malformed/unrecognized payloads. The backend
/// itself never emits "unparseable"; it exists so [UrgencyResult.fromJson]
/// can guarantee it never throws (see AGENTS.md: unknown/invalid wire
/// values must not crash).
enum ChatTurnType { question, assessment, crisis, error, unparseable }

/// The assistant's structured response payload for one turn — the
/// contract documented in functions/main.py and functions/gemini_client.py.
class UrgencyResult {
  const UrgencyResult({
    required this.type,
    required this.message,
    this.quickReplies = const [],
    this.urgency,
    this.explanation,
    this.watchFor = const [],
    this.nextStep,
    this.selfCare = const [],
    this.monitoring = const [],
    this.encouragement,
  });

  final ChatTurnType type;
  final String message;
  final List<String> quickReplies;
  final UrgencyLevel? urgency;
  final String? explanation;
  final List<String> watchFor;
  final String? nextStep;
  final List<String> selfCare;
  final List<String> monitoring;
  final String? encouragement;

  /// Never throws. Any structurally invalid payload — an unrecognized
  /// `type`, a missing `message`, or (per the contract) an `assessment`
  /// turn missing a valid `urgency` tier — becomes [ChatTurnType.unparseable]
  /// instead, so the UI can render the same apologetic style as a real
  /// "error" turn rather than crashing.
  factory UrgencyResult.fromJson(Map<String, dynamic> json) {
    final type = _parseType(json['type']);
    final message = json['message'];
    if (type == null || message is! String) {
      return UrgencyResult.unparseable(message is String ? message : null);
    }

    final urgency = _parseUrgency(json['urgency']);
    if (type == ChatTurnType.assessment && urgency == null) {
      return UrgencyResult.unparseable(message);
    }

    return UrgencyResult(
      type: type,
      message: message,
      quickReplies: _stringList(json['quick_replies']),
      urgency: urgency,
      explanation: json['explanation'] as String?,
      watchFor: _stringList(json['watch_for']),
      nextStep: json['next_step'] as String?,
      selfCare: _stringList(json['self_care']),
      monitoring: _stringList(json['monitoring']),
      encouragement: json['encouragement'] as String?,
    );
  }

  factory UrgencyResult.unparseable([String? rawMessage]) {
    return UrgencyResult(
      type: ChatTurnType.unparseable,
      message: rawMessage ??
          "I couldn't quite make sense of that reply — try sending your "
              'message again?',
    );
  }

  Map<String, dynamic> toJson() => {
        'type': _typeWire(type),
        'message': message,
        'quick_replies': quickReplies,
        'urgency': _urgencyWire(urgency),
        'explanation': explanation,
        'watch_for': watchFor,
        'next_step': nextStep,
        'self_care': selfCare,
        'monitoring': monitoring,
        'encouragement': encouragement,
      };

  static ChatTurnType? _parseType(dynamic value) {
    switch (value) {
      case 'question':
        return ChatTurnType.question;
      case 'assessment':
        return ChatTurnType.assessment;
      case 'crisis':
        return ChatTurnType.crisis;
      case 'error':
        return ChatTurnType.error;
      default:
        return null;
    }
  }

  static String? _typeWire(ChatTurnType type) {
    switch (type) {
      case ChatTurnType.question:
        return 'question';
      case ChatTurnType.assessment:
        return 'assessment';
      case ChatTurnType.crisis:
        return 'crisis';
      case ChatTurnType.error:
        return 'error';
      case ChatTurnType.unparseable:
        return null; // never a real wire value
    }
  }

  static UrgencyLevel? _parseUrgency(dynamic value) {
    switch (value) {
      case 'monitor_at_home':
        return UrgencyLevel.monitorAtHome;
      case 'see_doctor_soon':
        return UrgencyLevel.seeDoctorSoon;
      case 'seek_care_now':
        return UrgencyLevel.seekCareNow;
      default:
        return null;
    }
  }

  static String? _urgencyWire(UrgencyLevel? level) {
    switch (level) {
      case UrgencyLevel.monitorAtHome:
        return 'monitor_at_home';
      case UrgencyLevel.seeDoctorSoon:
        return 'see_doctor_soon';
      case UrgencyLevel.seekCareNow:
        return 'seek_care_now';
      case null:
        return null;
    }
  }

  static List<String> _stringList(dynamic value) {
    if (value is! List) return const [];
    return value.whereType<String>().toList();
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `flutter test test/features/chat/models/urgency_result_test.dart`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/features/chat/models/urgency_result.dart test/features/chat/models/urgency_result_test.dart
git commit -m "feat(chat): add UrgencyResult model with defensive fromJson"
```

---

### Task 2: `Message` model

**Files:**
- Create: `lib/features/chat/models/message.dart`
- Test: `test/features/chat/models/message_test.dart`

- [ ] **Step 1: Write the failing tests**

```dart
// test/features/chat/models/message_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/features/chat/models/message.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';

void main() {
  test('Message.user builds a user-role message with no payload', () {
    final message = Message.user('I have a fever');

    expect(message.role, MessageRole.user);
    expect(message.text, 'I have a fever');
    expect(message.payload, isNull);
    expect(message.checkedSelfCare, isEmpty);
  });

  test('Message.assistant carries the payload and mirrors its message text', () {
    const payload = UrgencyResult(type: ChatTurnType.question, message: 'How long?');
    final message = Message.assistant(payload);

    expect(message.role, MessageRole.assistant);
    expect(message.text, 'How long?');
    expect(message.payload, payload);
  });

  test('copyWith replaces checkedSelfCare without mutating the original', () {
    final original = Message.user('hi');
    final updated = original.copyWith(checkedSelfCare: {0, 2});

    expect(original.checkedSelfCare, isEmpty);
    expect(updated.checkedSelfCare, {0, 2});
    expect(updated.id, original.id);
    expect(updated.text, original.text);
  });

  group('toHistoryJson', () {
    test('a user message emits {role, content}', () {
      final message = Message.user('I have a fever');

      expect(message.toHistoryJson(), {'role': 'user', 'content': 'I have a fever'});
    });

    test('an assistant message emits {role, content, type} per the client contract', () {
      const payload = UrgencyResult(type: ChatTurnType.assessment, message: 'msg');
      final message = Message.assistant(payload);

      expect(
        message.toHistoryJson(),
        {'role': 'assistant', 'content': 'msg', 'type': 'assessment'},
      );
    });

    test('an error-type assistant message returns null (not real model output)', () {
      const payload = UrgencyResult(type: ChatTurnType.error, message: 'oops');
      final message = Message.assistant(payload);

      expect(message.toHistoryJson(), isNull);
    });

    test('an unparseable-type assistant message returns null', () {
      final message = Message.assistant(UrgencyResult.unparseable());

      expect(message.toHistoryJson(), isNull);
    });
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `flutter test test/features/chat/models/message_test.dart`
Expected: FAIL — `message.dart` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

```dart
// lib/features/chat/models/message.dart
import 'urgency_result.dart';

enum MessageRole { user, assistant }

/// One turn in the conversation. Nothing here is persisted this pass —
/// no Firestore yet (TODO(episode model): once conversations are
/// persisted server-side, this becomes a stream over the active
/// episode's messages instead of local AsyncNotifier state — see
/// chat_provider.dart). No wire `fromJson`: nothing reads a Message back
/// from storage yet, so only `toHistoryJson()` (the client contract) is
/// needed, not a full round-trip pair.
class Message {
  Message({
    required this.id,
    required this.role,
    required this.text,
    this.payload,
    DateTime? timestamp,
    this.checkedSelfCare = const {},
  }) : timestamp = timestamp ?? DateTime.now();

  final String id;
  final MessageRole role;
  final String text;
  final UrgencyResult? payload;
  final DateTime timestamp;

  /// Indices into `payload.selfCare` the user has checked off this
  /// session. UI state only — never sent to the server, never persisted,
  /// no gamification. Mutated only via ChatController.toggleSelfCare.
  final Set<int> checkedSelfCare;

  factory Message.user(String text) => Message(
        id: _newId(),
        role: MessageRole.user,
        text: text,
      );

  factory Message.assistant(UrgencyResult payload) => Message(
        id: _newId(),
        role: MessageRole.assistant,
        text: payload.message,
        payload: payload,
      );

  static String _newId() => DateTime.now().microsecondsSinceEpoch.toString();

  Message copyWith({Set<int>? checkedSelfCare}) => Message(
        id: id,
        role: role,
        text: text,
        payload: payload,
        timestamp: timestamp,
        checkedSelfCare: checkedSelfCare ?? this.checkedSelfCare,
      );

  /// Per functions/main.py's client contract: assistant turns MUST carry
  /// their `type` so the server's crisis-lock detection
  /// (`_history_has_crisis_lock`) works. Returns null for assistant turns
  /// whose type the server never emits itself (`error`, `unparseable`) —
  /// those aren't real model output and shouldn't be replayed as history.
  Map<String, dynamic>? toHistoryJson() {
    if (role == MessageRole.user) {
      return {'role': 'user', 'content': text};
    }
    final type = payload?.type;
    if (type != ChatTurnType.question &&
        type != ChatTurnType.assessment &&
        type != ChatTurnType.crisis) {
      return null;
    }
    return {
      'role': 'assistant',
      'content': text,
      'type': type == ChatTurnType.question
          ? 'question'
          : type == ChatTurnType.assessment
              ? 'assessment'
              : 'crisis',
    };
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `flutter test test/features/chat/models/message_test.dart`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/features/chat/models/message.dart test/features/chat/models/message_test.dart
git commit -m "feat(chat): add Message model with client-contract history serialization"
```

---

### Task 3: Chat fixtures

**Files:**
- Create: `lib/features/chat/fixtures/chat_fixtures.dart`
- Test: `test/features/chat/fixtures/chat_fixtures_test.dart`

Exact source mapping (see spec §"Fixtures" for full rationale): fixtures 1–2 from the dengue example (turns 1–2), fixture 3 from the sore-throat example (turn 2 only), fixture 4 from "Validated escalation" (single turn), fixture 5 from "Crisis — hopelessness expressed" (single turn), fixture 6 from `main.py`'s `_degraded_error_payload` (`FRIENDLY_DEGRADED_ERROR_MESSAGE_EN`).

- [ ] **Step 1: Write the failing test**

```dart
// test/features/chat/fixtures/chat_fixtures_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/fixtures/chat_fixtures.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';

void main() {
  test('there are exactly 6 fixtures', () {
    expect(chatFixtures.length, 6);
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

  test('fixture 2 is a see_doctor_soon assessment with every section populated', () {
    final result = UrgencyResult.fromJson(chatFixtures[1]);
    expect(result.type, ChatTurnType.assessment);
    expect(result.urgency, UrgencyLevel.seeDoctorSoon);
    expect(result.selfCare, isNotEmpty);
    expect(result.monitoring, isNotEmpty);
    expect(result.watchFor, isNotEmpty);
    expect(result.encouragement, isNotNull);
  });

  test('fixture 3 is a monitor_at_home assessment with every section populated', () {
    final result = UrgencyResult.fromJson(chatFixtures[2]);
    expect(result.type, ChatTurnType.assessment);
    expect(result.urgency, UrgencyLevel.monitorAtHome);
    expect(result.selfCare, isNotEmpty);
    expect(result.monitoring, isNotEmpty);
    expect(result.watchFor, isNotEmpty);
  });

  test('fixture 4 is a seek_care_now assessment with the graceful-empty sections', () {
    final result = UrgencyResult.fromJson(chatFixtures[3]);
    expect(result.type, ChatTurnType.assessment);
    expect(result.urgency, UrgencyLevel.seekCareNow);
    expect(result.selfCare, isEmpty);
    expect(result.monitoring, isEmpty);
    expect(result.watchFor, isNotEmpty);
  });

  test('fixture 5 is a crisis turn', () {
    final result = UrgencyResult.fromJson(chatFixtures[4]);
    expect(result.type, ChatTurnType.crisis);
  });

  test('fixture 6 is an error turn', () {
    final result = UrgencyResult.fromJson(chatFixtures[5]);
    expect(result.type, ChatTurnType.error);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/features/chat/fixtures/chat_fixtures_test.dart`
Expected: FAIL — `chat_fixtures.dart` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

```dart
// lib/features/chat/fixtures/chat_fixtures.dart
/// Hand-copied fixture payloads: five verbatim from
/// functions/system_prompt.py's FEW_SHOT_EXAMPLES (PROMPT_VERSION 1.5.0
/// as of this writing), one from main.py's degraded-error path. Exact
/// turn-by-turn mapping and rationale in
/// docs/superpowers/specs/2026-07-10-chat-screen-design.md.
///
/// Kept as raw wire-shaped JSON (not typed objects) so every fixture
/// round-trips through UrgencyResult.fromJson exactly like a real
/// callable response — including the undocumented `possibilities_mentioned`
/// key (see the spec's "Discrepancy found and flagged" note), which
/// fromJson must ignore without choking.
library;

const List<Map<String, dynamic>> chatFixtures = [
  // 1. Question, with chips — dengue example, turn 1
  {
    'type': 'question',
    'message':
        'Mukhang mabigat nga yung pakiramdam mo — lagnat, sakit ng ulo, '
            'tapos nanghihina ka pa. Isang tanong lang para mas matulungan '
            'kita: ilang araw ka na bang may lagnat?',
    'quick_replies': [
      'Kakasimula lang',
      '2–3 araw na',
      'Higit 3 araw na',
      'Hindi ako sure',
    ],
    'urgency': null,
    'explanation': null,
    'watch_for': [],
    'next_step': null,
    'possibilities_mentioned': false,
    'self_care': [],
    'monitoring': [],
    'encouragement': null,
  },
  // 2. Assessment, see_doctor_soon, all sections populated — dengue example, turn 2
  {
    'type': 'assessment',
    'message':
        "Salamat sa sagot. Ganito: yung kombinasyon ng lagnat, matinding "
            "sakit ng ulo, at panghihina — lalo na't may nakagat sa'yong "
            "lamok at may mga kaso ng dengue ngayon sa inyo — pwedeng "
            "ordinaryong trangkaso lang 'to, pero pwede ring dengue o ibang "
            "viral na sakit. Hindi natin masisiguro sa chat lang, kaya mas "
            "mabuting magpa-check ka na bukas o sa susunod na araw — may "
            "simpleng blood test para malaman agad.\nIsa pang importante: sa "
            "dengue, minsan pag bumaba na yung lagnat, doon pa lalabas yung "
            "delikadong senyales. Kaya kahit gumaan na pakiramdam mo, "
            "bantayan mo pa rin ang mga 'to sa susunod na 1–2 araw.",
    'quick_replies': [],
    'urgency': 'see_doctor_soon',
    'explanation':
        "Lagnat na 2–3 araw na, matinding sakit ng ulo, at panghihina — "
            "at may dengue sa inyong lugar — kaya mas mabuting magpa-check "
            "sa loob ng 1–2 araw.",
    'watch_for': [
      'Sumakit nang matindi ang tiyan',
      'Nagsuka nang paulit-ulit',
      'Dumugo ang gilagid o ilong',
      'Sobrang antok o hirap gisingin — kung alinman dito, diretso '
          'na sa ospital agad',
    ],
    'next_step':
        'Magpa-check bukas o sa susunod na araw — may simpleng blood '
            'test para malaman kung dengue.',
    'possibilities_mentioned': true,
    'self_care': ['Uminom ng maraming tubig', 'Magpahinga'],
    'monitoring': [
      'Sukatin ang temperatura kada 4-6 oras',
      'Bantayan ang pakiramdam sa susunod na 1-2 araw kahit '
          'gumaan na ang lagnat — dito karaniwang lumalabas ang mga '
          'delikadong senyales sa dengue',
    ],
    'encouragement':
        'Nandito lang ako — kung may nagbago o may bago kang '
            'mapansin, sabihin mo lang at titingnan nating ulit.',
  },
  // 3. Assessment, monitor_at_home, all sections populated — sore-throat example, turn 2
  {
    'type': 'assessment',
    'message':
        "That sounds like a common sore throat so far — one day in, mild "
            "fever, and you're otherwise okay. This is something you can care "
            "for at home for now — I've listed what helps below.\nJust keep an "
            "eye on it. If the fever lasts more than 3 days, swallowing becomes "
            "really painful, or you have any trouble breathing, get checked by "
            "a doctor.",
    'quick_replies': [],
    'urgency': 'monitor_at_home',
    'explanation':
        'Mild, short symptoms with no trouble breathing or swallowing, in '
            'an otherwise healthy adult, are safe to watch at home first.',
    'watch_for': [
      'Actual difficulty breathing or swallowing — difficulty, not just pain',
      'Fever that climbs high or lasts beyond 3 days',
      'Severe pain on one side of the throat, drooling, or a muffled voice',
      'Feeling much worse instead of gradually better',
    ],
    'next_step':
        'Care for it at home today; see a doctor if any sign on the watch '
            "list appears, or if you're not improving after 2-3 days.",
    'possibilities_mentioned': false,
    'self_care': [
      'Rest',
      'Plenty of water',
      'Warm salt-water gargles',
      'Paracetamol for the fever if you need it, following the '
          'package directions',
    ],
    'monitoring': [
      "Keep track of the fever day by day — if it's still there "
          'in 2-3 days, get checked',
    ],
    'encouragement':
        "I'm here if anything changes — just let me know and we'll "
            'take another look.',
  },
  // 4. Assessment, seek_care_now, graceful-empty — "Validated escalation" example
  {
    'type': 'assessment',
    'message':
        "Maaaring tama ka — puyat o migraine nga ang pinaka-common na "
            "dahilan ng ganyan. Pero pag sabay yung sakit ng ulo at "
            "panlalabo ng isang mata, may ilang rare pero seryosong problema "
            "na ganyan din magsimula — at hindi natin masisiguro sa chat "
            "lang yun; walang naka-check sa'yo, walang nakatingin sa mata "
            "mo. Kaya hindi ko masasabing puyat lang ito.\nAng payo ko: "
            "magpa-check ka na ngayong araw mismo, sa ospital o clinic na "
            "kayang tingnan ang mata at ulo. Hindi 'to para takutin ka — "
            "kadalasan may simpleng paliwanag, pero yung mga bihirang "
            "dahilan ng ganitong kombinasyon, mas maigi talagang mahuli "
            "agad. Kung simple lang pala, eh di mas mapapanatag ka na rin.",
    'quick_replies': [],
    'urgency': 'seek_care_now',
    'explanation':
        "Kadalasan puyat o migraine lang 'to, pero may rare na "
            'seryosong dahilan na hindi natin masisiguro sa chat lang — '
            'kaya ngayong araw na dapat magpa-check.',
    'watch_for': [
      'Kung biglang lumala ang sakit ng ulo, tuluyang nawala ang '
          'paningin, nanghina ang isang bahagi ng katawan, o nahirapan '
          'kang magsalita — diretso na sa ER, huwag nang maghintay',
    ],
    'next_step':
        'Pumunta ngayong araw sa ospital o klinikang may kayang tumingin '
            'sa mata at ulo — huwag hintayin kung kusang mawawala.',
    'possibilities_mentioned': true,
    'self_care': [],
    'monitoring': [],
    'encouragement':
        'Tama namang magpa-check ngayon — sabihin mo sa akin kung '
            'kumusta ka pagkatapos, ha.',
  },
  // 5. Crisis — "Crisis — hopelessness expressed" example
  {
    'type': 'crisis',
    'message':
        "Salamat at sinabi mo 'to sa'kin. Mabigat yung dinadala mo "
            "ngayon, at hindi mo yan kailangang ayusin mag-isa. Nandito "
            "ako — kung gusto mong magkwento pa, makikinig ako. Hindi kita "
            "mamadaliin, hindi kita huhusgahan.\nKapag handa ka, may mga "
            "taong sanay makinig sa ganito at pwede mong kausapin kahit "
            "anong oras — nasa baba lang yung mga numero, hindi sila "
            "mawawala. Pero kung ang kailangan mo muna ngayon ay may "
            "makinig sa'yo — andito lang ako, tuloy lang tayo.",
    'quick_replies': [],
    'urgency': null,
    'explanation': null,
    'watch_for': [],
    'next_step': null,
    'possibilities_mentioned': false,
    'self_care': [],
    'monitoring': [],
    'encouragement': null,
  },
  // 6. Error — main.py's _degraded_error_payload, English copy
  {
    'type': 'error',
    'message':
        "Something's not working right on my end. I'm still here — try "
            'sending that again in a bit?',
    'quick_replies': [],
    'urgency': null,
    'explanation': null,
    'watch_for': [],
    'next_step': null,
    'possibilities_mentioned': false,
    'self_care': [],
    'monitoring': [],
    'encouragement': null,
  },
];
```

- [ ] **Step 4: Run test to verify it passes**

Run: `flutter test test/features/chat/fixtures/chat_fixtures_test.dart`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/features/chat/fixtures/chat_fixtures.dart test/features/chat/fixtures/chat_fixtures_test.dart
git commit -m "feat(chat): add the 6 hand-copied fixture payloads"
```

---

### Task 4: Theme additions

**Files:**
- Modify: `lib/core/theme/app_theme.dart`
- Modify: `PULSE_DESIGN_SYSTEM.md` (backfill the 2 extra shadow tokens found while writing this plan — see "Before you start" note above)

No dedicated test file — these are constants; `flutter analyze` plus every widget task from here on exercising them is the coverage. Apply as an in-place edit (find the exact anchor text in the current file, insert after it).

- [ ] **Step 1: Add new `AppRadii` constants**

Find in `lib/core/theme/app_theme.dart`:
```dart
  static const double iconChip = 15;
  static const double navBarTop = 26;
}
```
Replace with:
```dart
  static const double iconChip = 15;
  static const double navBarTop = 26;

  // --- Chat-screen extensions (2026-07-10) — see PULSE_DESIGN_SYSTEM.md §8 ---
  static const double crisisCard = 28;
  static const double cardRowRadius = 14;
  static const double pillRowRadius = 13;
}
```

- [ ] **Step 2: Add new `AppColors` constants**

Find:
```dart
  // Toggle
  static const Color toggleOff = Color(0xFFE4DDD0);
```
Replace with:
```dart
  // Toggle
  static const Color toggleOff = Color(0xFFE4DDD0);

  // --- Chat-screen extensions (2026-07-10) — see PULSE_DESIGN_SYSTEM.md §8 ---
  static const Color crisisHeading = Color(0xFF2F4A4F);
  static const Color crisisBody = Color(0xFF3F5559);
  static const Color crisisFooterText = Color(0xFF7C9296);
```

- [ ] **Step 3: Add new `AppShadows` constants**

Find:
```dart
  static List<BoxShadow> navBarTop = [
    BoxShadow(
      color: const Color(0xFF506464).withOpacity(0.06),
      blurRadius: 20,
      offset: const Offset(0, -6),
    ),
  ];
}
```
Replace with:
```dart
  static List<BoxShadow> navBarTop = [
    BoxShadow(
      color: const Color(0xFF506464).withOpacity(0.06),
      blurRadius: 20,
      offset: const Offset(0, -6),
    ),
  ];

  // --- Chat-screen extensions (2026-07-10) — see PULSE_DESIGN_SYSTEM.md §8 ---
  static List<BoxShadow> crisisCard = [
    BoxShadow(
      color: AppColors.primary.withOpacity(0.18),
      blurRadius: 30,
      offset: const Offset(0, 12),
    ),
  ];

  static List<BoxShadow> userBubble = [
    BoxShadow(
      color: AppColors.primary.withOpacity(0.28),
      blurRadius: 16,
      offset: const Offset(0, 6),
    ),
  ];
}
```

- [ ] **Step 4: Add the two new text styles (`titleSmall`, `labelMedium`)**

These reuse otherwise-unused Material `TextTheme` slots rather than inventing bespoke style classes — same mechanism as every existing style in this file. The actual Dart symbols are `theme.textTheme.titleSmall` (for what `PULSE_DESIGN_SYSTEM.md` §8 calls `cardSectionHeading`) and `theme.textTheme.labelMedium` (for what it calls `cardEyebrow`) — Step 5 below backfills the doc's "Type" table with these real names so a future grep for `cardEyebrow`/`cardSectionHeading` doesn't come up empty.

Find:
```dart
        // List row titles
        titleMedium: headingFont.titleMedium?.copyWith(
          fontWeight: FontWeight.w700,
          fontSize: 15,
          color: AppColors.text,
        ),
        // Section eyebrows (UPPERCASE) — apply
```
Replace with:
```dart
        // List row titles
        titleMedium: headingFont.titleMedium?.copyWith(
          fontWeight: FontWeight.w700,
          fontSize: 15,
          color: AppColors.text,
        ),
        // Chat-screen extension (2026-07-10): in-card group headers
        // ("Things you can do today", "Check in on yourself", "Get
        // care if…") — see PULSE_DESIGN_SYSTEM.md §8.
        titleSmall: headingFont.titleSmall?.copyWith(
          fontWeight: FontWeight.w700,
          fontSize: 13.5,
          color: AppColors.text,
        ),
        // Chat-screen extension (2026-07-10): the "PULSE GUIDANCE"
        // meta-label on the assessment card — distinct from the
        // Section-eyebrow style below (Inter, not Nunito; smaller).
        labelMedium: bodyFont.labelMedium?.copyWith(
          fontWeight: FontWeight.w600,
          fontSize: 10.5,
          letterSpacing: 0.6,
          color: AppColors.textFaint,
        ),
        // Section eyebrows (UPPERCASE) — apply
```

- [ ] **Step 5: Backfill `PULSE_DESIGN_SYSTEM.md` §8** — the 2 shadow additions found while writing this plan, plus the real Dart symbol names for the two text styles from Step 4

Find in `PULSE_DESIGN_SYSTEM.md`:
```
### Type
| Style | Font / weight | Size | Notes |
|---|---|---|---|
| `cardEyebrow` | Inter 600 | 10.5px | The "PULSE GUIDANCE" meta-label on the assessment card. Distinct from the Section 3 "Section eyebrow" style (Nunito 700, 12-13px, `--label-eyebrow`) — this is a smaller, Inter-based card meta-label, not a section header. Uppercase, letter-spacing 0.6px, `--text-faint`. |
| `cardSectionHeading` | Nunito 700 | 13.5px | In-card group headers ("Things you can do today", "Check in on yourself", "Get care if…"). Falls between the existing 15px (`titleMedium`) and 12.5px (`labelSmall`/eyebrow) slots, so needed its own entry rather than reusing either. `--text` color. |
```
Replace with:
```
### Type
| Style | Font / weight | Size | Notes |
|---|---|---|---|
| `cardEyebrow` (implemented as `textTheme.labelMedium`) | Inter 600 | 10.5px | The "PULSE GUIDANCE" meta-label on the assessment card. Distinct from the Section 3 "Section eyebrow" style (Nunito 700, 12-13px, `--label-eyebrow`) — this is a smaller, Inter-based card meta-label, not a section header. Uppercase, letter-spacing 0.6px, `--text-faint`. |
| `cardSectionHeading` (implemented as `textTheme.titleSmall`) | Nunito 700 | 13.5px | In-card group headers ("Things you can do today", "Check in on yourself", "Get care if…"). Falls between the existing 15px (`titleMedium`) and 12.5px (`labelSmall`/eyebrow) slots, so needed its own entry rather than reusing either. `--text` color. |
```

Find:
```
### Shadows
| Token | Value | Justification |
|---|---|---|
| Crisis card shadow | `0 12px 30px rgba(111,168,181,.18)` | Close to but distinct from the existing "Card (raised)" shadow (`0 10px 26px rgba(111,168,181,.16)`) — kept as its own token rather than reusing, since the two didn't match exactly in the mockup.
```
Replace with:
```
### Shadows
| Token | Value | Justification |
|---|---|---|
| Crisis card shadow | `0 12px 30px rgba(111,168,181,.18)` | Close to but distinct from the existing "Card (raised)" shadow (`0 10px 26px rgba(111,168,181,.16)`) — kept as its own token rather than reusing, since the two didn't match exactly in the mockup.
| `AppShadows.userBubble` | `0 6px 16px rgba(111,168,181,.28)` | User chat-bubble shadow — found while implementing (not in the original spec pass). Color is exactly `--primary` at 28% opacity, distinct enough from every existing teal shadow to warrant its own token. |

Pulse (assistant) bubble shadow (`0 6px 16px rgba(80,100,100,.08)`) reuses the
existing "Card (resting)" shadow rather than adding a third token — same
color/opacity, blur/offset close enough (16/6 vs. 22/8) not to duplicate.
```

- [ ] **Step 6: Verify it compiles**

Run: `flutter analyze lib/core/theme/app_theme.dart`
Expected: No issues found.

- [ ] **Step 7: Commit**

```bash
git add lib/core/theme/app_theme.dart PULSE_DESIGN_SYSTEM.md
git commit -m "feat(theme): add chat-screen radii, colors, shadows, and text styles"
```

---

### Task 5: Crisis resources constant

**Files:**
- Create: `lib/core/constants/crisis_resources.dart`

No dedicated test — it's a static data list; Task 14's `CrisisCard` widget test exercises it.

- [ ] **Step 1: Write the file**

```dart
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
```

- [ ] **Step 2: Verify it compiles**

Run: `flutter analyze lib/core/constants/crisis_resources.dart`
Expected: No issues found.

- [ ] **Step 3: Commit**

```bash
git add lib/core/constants/crisis_resources.dart
git commit -m "feat(chat): add placeholder crisis hotline resources"
```

---

### Task 6: Add `url_launcher` dependency

**Files:**
- Modify: `pubspec.yaml`

- [ ] **Step 1: Add the package**

Run: `flutter pub add url_launcher`
Expected: `pubspec.yaml` gains a `url_launcher: ^<version>` line under `dependencies`; `flutter pub get` runs automatically.

- [ ] **Step 2: Verify it resolves**

Run: `flutter pub get`
Expected: "Got dependencies!" with no errors.

- [ ] **Step 3: Commit**

```bash
git add pubspec.yaml pubspec.lock
git commit -m "chore: add url_launcher for crisis-card tap-to-dial"
```

---

### Task 7: `ChatRepository` interface + `FixtureChatRepository`

**Files:**
- Create: `lib/features/chat/repositories/chat_repository.dart`
- Create: `lib/features/chat/repositories/fixture_chat_repository.dart`
- Test: `test/features/chat/repositories/fixture_chat_repository_test.dart`

- [ ] **Step 1: Write the failing test**

```dart
// test/features/chat/repositories/fixture_chat_repository_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/features/chat/fixtures/chat_fixtures.dart';
import 'package:pulse_app/features/chat/models/message.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';
import 'package:pulse_app/features/chat/repositories/fixture_chat_repository.dart';

void main() {
  test('cycles through all 6 fixtures in order across repeated sends', () async {
    final repository = FixtureChatRepository();

    for (var i = 0; i < chatFixtures.length; i++) {
      final reply = await repository.send(text: 'msg $i', history: const []);
      final expected = UrgencyResult.fromJson(chatFixtures[i]);

      expect(reply.role, MessageRole.assistant);
      expect(reply.payload?.type, expected.type);
      expect(reply.text, expected.message);
    }
  });

  test('wraps back to the first fixture after the last one', () async {
    final repository = FixtureChatRepository();
    for (var i = 0; i < chatFixtures.length; i++) {
      await repository.send(text: 'msg', history: const []);
    }

    final wrapped = await repository.send(text: 'one more', history: const []);
    final firstExpected = UrgencyResult.fromJson(chatFixtures[0]);

    expect(wrapped.payload?.type, firstExpected.type);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/features/chat/repositories/fixture_chat_repository_test.dart`
Expected: FAIL — files don't exist yet.

- [ ] **Step 3: Write the implementation**

```dart
// lib/features/chat/repositories/chat_repository.dart
import '../models/message.dart';

/// Sends a user's message and returns the assistant's turn. Both
/// implementations may throw on failure — [ChatController] is the single
/// place that catches and converts a thrown exception into a consistent
/// error [Message] (see chat_provider.dart), so neither implementation
/// needs its own try/catch.
abstract class ChatRepository {
  Future<Message> send({
    required String text,
    required List<Message> history,
  });
}
```

```dart
// lib/features/chat/repositories/fixture_chat_repository.dart
import '../fixtures/chat_fixtures.dart';
import '../models/message.dart';
import '../models/urgency_result.dart';
import 'chat_repository.dart';

/// Cycles through [chatFixtures] on every call so every payload state is
/// reachable by hand-testing with zero network calls or API quota.
/// Debug-only — see chat_provider.dart for the kDebugMode gate that
/// selects this over [CallableChatRepository].
class FixtureChatRepository implements ChatRepository {
  int _index = 0;

  @override
  Future<Message> send({
    required String text,
    required List<Message> history,
  }) async {
    await Future<void>.delayed(const Duration(milliseconds: 500));
    final json = chatFixtures[_index % chatFixtures.length];
    _index++;
    return Message.assistant(UrgencyResult.fromJson(json));
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `flutter test test/features/chat/repositories/fixture_chat_repository_test.dart`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/features/chat/repositories/chat_repository.dart lib/features/chat/repositories/fixture_chat_repository.dart test/features/chat/repositories/fixture_chat_repository_test.dart
git commit -m "feat(chat): add ChatRepository interface and FixtureChatRepository"
```

---

### Task 8: `CallableChatRepository`

**Files:**
- Create: `lib/features/chat/repositories/callable_chat_repository.dart`
- Test: `test/features/chat/repositories/callable_chat_repository_test.dart`

Only `buildRequestData` (pure, Firebase-free) is unit-tested here — see "Before you start" for why the live `httpsCallable` call itself isn't covered by an automated test this pass.

- [ ] **Step 1: Write the failing test**

```dart
// test/features/chat/repositories/callable_chat_repository_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/features/chat/models/message.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';
import 'package:pulse_app/features/chat/repositories/callable_chat_repository.dart';

void main() {
  group('CallableChatRepository.buildRequestData', () {
    test('includes the message and null profile/worry_level/regional_context', () {
      final data = CallableChatRepository.buildRequestData(
        text: 'I have a fever',
        history: const [],
      );

      expect(data['message'], 'I have a fever');
      expect(data['profile'], isNull);
      expect(data['worry_level'], isNull);
      expect(data['regional_context'], isNull);
      expect(data['conversation_id'], isNull);
    });

    test('builds history from prior messages via toHistoryJson, dropping error/unparseable turns', () {
      final history = [
        Message.user('hello'),
        Message.assistant(const UrgencyResult(type: ChatTurnType.question, message: 'q')),
        Message.assistant(const UrgencyResult(type: ChatTurnType.error, message: 'oops')),
      ];

      final data = CallableChatRepository.buildRequestData(text: 'next', history: history);

      expect(data['history'], [
        {'role': 'user', 'content': 'hello'},
        {'role': 'assistant', 'content': 'q', 'type': 'question'},
      ]);
    });
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/features/chat/repositories/callable_chat_repository_test.dart`
Expected: FAIL — file doesn't exist yet.

- [ ] **Step 3: Write the implementation**

```dart
// lib/features/chat/repositories/callable_chat_repository.dart
import 'package:cloud_functions/cloud_functions.dart';

import '../models/message.dart';
import '../models/urgency_result.dart';
import 'chat_repository.dart';

/// Calls the `assess_symptoms` Callable Function in asia-southeast1. Per
/// AGENTS.md's AI/Backend rules, this repository only ever calls the
/// function and renders what comes back — it never constructs prompts,
/// holds API keys, or makes urgency decisions locally.
class CallableChatRepository implements ChatRepository {
  CallableChatRepository({FirebaseFunctions? functions})
      : _functions =
            functions ?? FirebaseFunctions.instanceFor(region: 'asia-southeast1');

  final FirebaseFunctions _functions;

  @override
  Future<Message> send({
    required String text,
    required List<Message> history,
  }) async {
    final callable = _functions.httpsCallable('assess_symptoms');
    final result = await callable.call<Map<String, dynamic>>(
      buildRequestData(text: text, history: history),
    );
    return Message.assistant(
      UrgencyResult.fromJson(Map<String, dynamic>.from(result.data as Map)),
    );
  }

  /// Extracted as a standalone, pure function so the request shape is
  /// unit-testable without a live Firebase project.
  ///
  /// profile / worry_level / regional_context: left null until the
  /// profile feature exists. TODO(profile feature): populate from the
  /// active household profile once it's built.
  static Map<String, dynamic> buildRequestData({
    required String text,
    required List<Message> history,
  }) {
    return {
      'message': text,
      'profile': null,
      'worry_level': null,
      'regional_context': null,
      'conversation_id': null,
      'history': history
          .map((m) => m.toHistoryJson())
          .whereType<Map<String, dynamic>>()
          .toList(),
    };
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `flutter test test/features/chat/repositories/callable_chat_repository_test.dart`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/features/chat/repositories/callable_chat_repository.dart test/features/chat/repositories/callable_chat_repository_test.dart
git commit -m "feat(chat): add CallableChatRepository"
```

---

### Task 9: `ChatController` provider

**Files:**
- Create: `lib/features/chat/providers/chat_provider.dart`
- Test: `test/features/chat/providers/chat_provider_test.dart`

- [ ] **Step 1: Write the failing tests**

```dart
// test/features/chat/providers/chat_provider_test.dart
import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/models/message.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';
import 'package:pulse_app/features/chat/providers/chat_provider.dart';
import 'package:pulse_app/features/chat/repositories/chat_repository.dart';

class _StubRepository implements ChatRepository {
  _StubRepository(this._reply);
  final UrgencyResult _reply;

  @override
  Future<Message> send({required String text, required List<Message> history}) async {
    return Message.assistant(_reply);
  }
}

class _ThrowingRepository implements ChatRepository {
  @override
  Future<Message> send({required String text, required List<Message> history}) {
    throw Exception('network down');
  }
}

void main() {
  test('send() appends the user message then the assistant reply', () async {
    final container = ProviderContainer(overrides: [
      chatRepositoryProvider.overrideWithValue(
        _StubRepository(const UrgencyResult(type: ChatTurnType.question, message: 'reply')),
      ),
    ]);
    addTearDown(container.dispose);

    await container.read(chatControllerProvider.notifier).send('hello');
    final messages = container.read(chatControllerProvider).value!;

    expect(messages.length, 2);
    expect(messages[0].role, MessageRole.user);
    expect(messages[0].text, 'hello');
    expect(messages[1].role, MessageRole.assistant);
    expect(messages[1].text, 'reply');
  });

  test('an empty/whitespace-only message is not sent', () async {
    final container = ProviderContainer(overrides: [
      chatRepositoryProvider.overrideWithValue(
        _StubRepository(const UrgencyResult(type: ChatTurnType.question, message: 'reply')),
      ),
    ]);
    addTearDown(container.dispose);

    await container.read(chatControllerProvider.notifier).send('   ');
    final messages = container.read(chatControllerProvider).value!;

    expect(messages, isEmpty);
  });

  test('a repository failure appends a synthetic error message, never throws', () async {
    final container = ProviderContainer(overrides: [
      chatRepositoryProvider.overrideWithValue(_ThrowingRepository()),
    ]);
    addTearDown(container.dispose);

    await container.read(chatControllerProvider.notifier).send('hello');
    final messages = container.read(chatControllerProvider).value!;

    expect(messages.length, 2);
    expect(messages[1].payload?.type, ChatTurnType.error);
  });

  test('toggleSelfCare flips only the targeted index on the targeted message', () async {
    final container = ProviderContainer(overrides: [
      chatRepositoryProvider.overrideWithValue(
        _StubRepository(const UrgencyResult(
          type: ChatTurnType.assessment,
          message: 'msg',
          urgency: UrgencyLevel.monitorAtHome,
          selfCare: ['Rest', 'Fluids'],
        )),
      ),
    ]);
    addTearDown(container.dispose);

    await container.read(chatControllerProvider.notifier).send('hello');
    final assistantMessage = container.read(chatControllerProvider).value!.last;

    container.read(chatControllerProvider.notifier).toggleSelfCare(assistantMessage.id, 0);
    var updated = container.read(chatControllerProvider).value!.last;
    expect(updated.checkedSelfCare, {0});

    container.read(chatControllerProvider.notifier).toggleSelfCare(assistantMessage.id, 0);
    updated = container.read(chatControllerProvider).value!.last;
    expect(updated.checkedSelfCare, isEmpty);
  });

  test('retryLast() drops the last user+reply pair and resends the same text', () async {
    var callCount = 0;
    final container = ProviderContainer(overrides: [
      chatRepositoryProvider.overrideWithValue(_CountingRepository(() => callCount++)),
    ]);
    addTearDown(container.dispose);

    await container.read(chatControllerProvider.notifier).send('hello');
    expect(callCount, 1);

    await container.read(chatControllerProvider.notifier).retryLast();
    expect(callCount, 2);

    final messages = container.read(chatControllerProvider).value!;
    // Exactly one user message ("hello") and one assistant reply remain —
    // retry did not duplicate the user turn.
    expect(messages.where((m) => m.role == MessageRole.user).length, 1);
    expect(messages.first.text, 'hello');
  });

  test('chatIsSendingProvider is true only while a send is in flight, on both success and failure paths', () async {
    final completer = Completer<Message>();
    final container = ProviderContainer(overrides: [
      chatRepositoryProvider.overrideWithValue(_CompleterRepository(completer)),
    ]);
    addTearDown(container.dispose);

    expect(container.read(chatIsSendingProvider), isFalse);

    final sendFuture = container.read(chatControllerProvider.notifier).send('hello');
    // The synchronous prefix of send() has run (up to the first await);
    // the flag must already be true before the repository call resolves.
    expect(container.read(chatIsSendingProvider), isTrue);

    completer.complete(
      Message.assistant(const UrgencyResult(type: ChatTurnType.question, message: 'reply')),
    );
    await sendFuture;

    expect(container.read(chatIsSendingProvider), isFalse);
  });

  test('chatIsSendingProvider resets to false even when the repository throws', () async {
    final container = ProviderContainer(overrides: [
      chatRepositoryProvider.overrideWithValue(_ThrowingRepository()),
    ]);
    addTearDown(container.dispose);

    await container.read(chatControllerProvider.notifier).send('hello');

    expect(container.read(chatIsSendingProvider), isFalse);
  });

  test('a second send() while one is already in flight is ignored (no clobbered state)', () async {
    var callCount = 0;
    final completer = Completer<Message>();
    final container = ProviderContainer(overrides: [
      chatRepositoryProvider.overrideWithValue(
        _CompleterRepository(completer, onCall: () => callCount++),
      ),
    ]);
    addTearDown(container.dispose);

    final first = container.read(chatControllerProvider.notifier).send('first');
    // Fires while the first send is still awaiting the completer —
    // must be a no-op, not a second concurrent repository call.
    final second = container.read(chatControllerProvider.notifier).send('second');

    completer.complete(
      Message.assistant(const UrgencyResult(type: ChatTurnType.question, message: 'reply')),
    );
    await first;
    await second;

    expect(callCount, 1);
    final messages = container.read(chatControllerProvider).value!;
    expect(messages.where((m) => m.role == MessageRole.user).length, 1);
    expect(messages.first.text, 'first');
  });

  test('retryLast() while a send is already in flight does not truncate the in-flight message', () async {
    final completer = Completer<Message>();
    final container = ProviderContainer(overrides: [
      chatRepositoryProvider.overrideWithValue(_CompleterRepository(completer)),
    ]);
    addTearDown(container.dispose);

    final sendFuture = container.read(chatControllerProvider.notifier).send('hello');
    // A send is now in flight (chatIsSendingProvider is true, state has
    // exactly one user message). A retry attempt here — e.g. a
    // double-tap on an error bubble from a PREVIOUS turn — must not
    // truncate that in-flight message.
    await container.read(chatControllerProvider.notifier).retryLast();

    final messagesWhileInFlight = container.read(chatControllerProvider).value!;
    expect(messagesWhileInFlight.length, 1);
    expect(messagesWhileInFlight.first.text, 'hello');

    completer.complete(
      Message.assistant(const UrgencyResult(type: ChatTurnType.question, message: 'reply')),
    );
    await sendFuture;

    final messagesAfter = container.read(chatControllerProvider).value!;
    expect(messagesAfter.length, 2);
    expect(messagesAfter.first.text, 'hello');
  });

  test('a self-care checkbox toggled while a later send is in flight is not reverted when that send resolves', () async {
    final firstCompleter = Completer<Message>();
    final secondCompleter = Completer<Message>();
    final container = ProviderContainer(overrides: [
      chatRepositoryProvider.overrideWithValue(
        _QueuedCompleterRepository([firstCompleter, secondCompleter]),
      ),
    ]);
    addTearDown(container.dispose);

    final firstSend = container.read(chatControllerProvider.notifier).send('hello');
    firstCompleter.complete(
      Message.assistant(const UrgencyResult(
        type: ChatTurnType.assessment,
        message: 'msg',
        urgency: UrgencyLevel.monitorAtHome,
        selfCare: ['Rest', 'Fluids'],
      )),
    );
    await firstSend;

    final assistantMessage = container.read(chatControllerProvider).value!.last;

    final secondSend = container.read(chatControllerProvider.notifier).send('a follow-up question');
    // Toggle a self-care box on the EARLIER assessment message while the
    // second send is still in flight — must not be reverted when the
    // second send's completion merges its reply into state.
    container.read(chatControllerProvider.notifier).toggleSelfCare(assistantMessage.id, 0);
    final midFlight = container.read(chatControllerProvider).value!;
    expect(
      midFlight.firstWhere((m) => m.id == assistantMessage.id).checkedSelfCare,
      {0},
    );

    secondCompleter.complete(
      Message.assistant(const UrgencyResult(type: ChatTurnType.question, message: 'reply 2')),
    );
    await secondSend;

    final after = container.read(chatControllerProvider).value!;
    expect(
      after.firstWhere((m) => m.id == assistantMessage.id).checkedSelfCare,
      {0},
    );
  });
}

/// Resolves each successive send() call from the next completer in the
/// queue — lets a test control multiple in-flight calls independently.
class _QueuedCompleterRepository implements ChatRepository {
  _QueuedCompleterRepository(this._completers);
  final List<Completer<Message>> _completers;
  int _i = 0;

  @override
  Future<Message> send({required String text, required List<Message> history}) {
    return _completers[_i++].future;
  }
}

class _CountingRepository implements ChatRepository {
  _CountingRepository(this._onCall);
  final void Function() _onCall;

  @override
  Future<Message> send({required String text, required List<Message> history}) async {
    _onCall();
    return Message.assistant(const UrgencyResult(type: ChatTurnType.question, message: 'reply'));
  }
}

/// Lets a test control exactly when send() resolves, to observe
/// mid-flight state (chatIsSendingProvider, re-entrancy) deterministically.
class _CompleterRepository implements ChatRepository {
  _CompleterRepository(this._completer, {void Function()? onCall}) : _onCall = onCall;
  final Completer<Message> _completer;
  final void Function()? _onCall;

  @override
  Future<Message> send({required String text, required List<Message> history}) {
    _onCall?.call();
    return _completer.future;
  }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `flutter test test/features/chat/providers/chat_provider_test.dart`
Expected: FAIL — `chat_provider.dart` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

```dart
// lib/features/chat/providers/chat_provider.dart
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
// StateProvider moved to the "legacy" surface in Riverpod 3.x — not
// exported from the main flutter_riverpod.dart barrel. Confirmed by
// reading flutter_riverpod-3.3.2/lib/legacy.dart directly.
import 'package:flutter_riverpod/legacy.dart' show StateProvider;

import '../models/message.dart';
import '../models/urgency_result.dart';
import '../repositories/callable_chat_repository.dart';
import '../repositories/chat_repository.dart';
import '../repositories/fixture_chat_repository.dart';

/// Flip to false to wire the real backend once fixture-mode UI review is
/// complete. Guarded by kDebugMode below so a release build can never
/// accidentally ship fixture mode regardless of this const's value.
const bool _useFixturesInDebug = true;

final chatRepositoryProvider = Provider<ChatRepository>((ref) {
  if (kDebugMode && _useFixturesInDebug) {
    return FixtureChatRepository();
  }
  return CallableChatRepository();
});

/// Whether a send is currently in flight — drives the typing indicator
/// in ChatScreen (Task 17). A plain flag, not part of chatControllerProvider's
/// own AsyncValue: Riverpod 3.x's `AsyncLoading().copyWithPrevious(...)`
/// (the framework's own mechanism for "loading, but keep showing the
/// previous value") is `@internal` to package:riverpod as of 3.3.2 — not
/// callable from application code, confirmed by reading
/// riverpod-3.3.2/lib/src/core/async_value.dart directly. Without it,
/// there's no way to make chatControllerProvider's AsyncValue report
/// `isLoading` while still exposing the in-progress message list, so
/// this narrow, deliberately-scoped exception to AGENTS.md's "not manual
/// isLoading booleans" guidance exists only because the framework's own
/// intended mechanism isn't reachable here.
final chatIsSendingProvider = StateProvider<bool>((ref) => false);

/// Holds the conversation's turn list. No Firestore persistence this
/// pass — conversation lives in memory only. TODO(episode model): once
/// conversations are persisted server-side, this becomes a stream over
/// the active episode's messages instead of local AsyncNotifier state.
class ChatController extends AsyncNotifier<List<Message>> {
  @override
  FutureOr<List<Message>> build() => <Message>[];

  Future<void> send(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return;
    // Re-entrancy guard: without this, two overlapping sends (a double
    // tap before the UI's `enabled: !isLoading` gate takes effect on the
    // next frame, or retryLast() racing a fresh send()) can each capture
    // their own stale `withUser` snapshot and silently clobber each
    // other's result when their awaits resolve out of order — found
    // during Task 9 code review, not hypothetical.
    if (ref.read(chatIsSendingProvider)) return;

    final history = state.value ?? <Message>[];
    final withUser = [...history, Message.user(trimmed)];
    state = AsyncData(withUser);

    // Everything from here through the reply/error assignment must stay
    // inside the try — including resolving the repository — so ANY
    // exception on this path (not just ones thrown by repository.send()
    // itself) still hits the catch/finally below. A prior version read
    // `ref.read(chatRepositoryProvider)` above the try; if that read
    // ever threw, chatIsSendingProvider would stay stuck `true` forever
    // (permanently disabling the input) and the exception would become
    // an unhandled Future rejection, since the planned call site
    // (`onSend: (text) => ref.read(...).send(text)`) never awaits this
    // Future. Found during Task 9 code review — keep the repository
    // read inside the try.
    ref.read(chatIsSendingProvider.notifier).state = true;
    try {
      final repository = ref.read(chatRepositoryProvider);
      final reply = await repository.send(text: trimmed, history: history);
      // Merge onto the LIVE state.value here, not the captured `withUser`
      // snapshot: toggleSelfCare() is synchronous, deliberately unguarded
      // (checking a self-care box on an earlier message must stay
      // possible while a later send is in flight), and can run during
      // this await. Both guards above only stop another async mutator
      // (send()/retryLast()) from entering — they don't protect against
      // a synchronous edit landing mid-await. state.value at this point
      // is always `withUser` with zero or more messages copyWith'd in
      // place (same length/order — toggleSelfCare never adds/removes),
      // so it's always safe to append onto. Using `withUser` directly
      // here would silently revert any checkbox toggled during the
      // await — found during Task 9 code review by reproducing the
      // exact sequence (toggle mid-flight, then let the send resolve).
      state = AsyncData([...(state.value ?? withUser), reply]);
    } catch (_) {
      state = AsyncData([...(state.value ?? withUser), _errorMessage()]);
    } finally {
      ref.read(chatIsSendingProvider.notifier).state = false;
    }
  }

  /// The error bubble's retry affordance: drops the failed exchange
  /// (the last user message and whatever followed it) and resends.
  Future<void> retryLast() async {
    // Same guard as send(): without it, a double-tap on the error
    // bubble's retry link (which has no disabled state of its own) can
    // truncate `state` a second time while the first retry is still in
    // flight, visibly wiping the in-flight user message from the list
    // until the first call resolves and self-heals it. Found during
    // Task 9 code review (empirically reproduced, not just traced).
    if (ref.read(chatIsSendingProvider)) return;

    final messages = state.value ?? <Message>[];
    final lastUserIndex = messages.lastIndexWhere((m) => m.role == MessageRole.user);
    if (lastUserIndex == -1) return;

    final text = messages[lastUserIndex].text;
    state = AsyncData(messages.sublist(0, lastUserIndex));
    await send(text);
  }

  /// Toggles one self-care checklist item for one assessment message.
  /// Session-only UI state — see Message.checkedSelfCare.
  void toggleSelfCare(String messageId, int index) {
    final messages = state.value;
    if (messages == null) return;
    state = AsyncData([
      for (final m in messages)
        if (m.id == messageId)
          m.copyWith(
            checkedSelfCare: m.checkedSelfCare.contains(index)
                ? (m.checkedSelfCare.toSet()..remove(index))
                : (m.checkedSelfCare.toSet()..add(index)),
          )
        else
          m,
    ]);
  }

  Message _errorMessage() => Message.assistant(
        const UrgencyResult(
          type: ChatTurnType.error,
          message:
              "Something's not working right on my end. I'm still here — "
                  'try sending that again in a bit?',
        ),
      );
}

final chatControllerProvider =
    AsyncNotifierProvider<ChatController, List<Message>>(ChatController.new);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `flutter test test/features/chat/providers/chat_provider_test.dart`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/features/chat/providers/chat_provider.dart test/features/chat/providers/chat_provider_test.dart
git commit -m "feat(chat): add ChatController with send/retryLast/toggleSelfCare"
```

---

### Task 10: `ChatBubble` widget

**Files:**
- Create: `lib/features/chat/widgets/chat_bubble.dart`
- Test: `test/features/chat/widgets/chat_bubble_test.dart`

- [ ] **Step 1: Write the failing tests**

```dart
// test/features/chat/widgets/chat_bubble_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/widgets/chat_bubble.dart';

Widget _wrap(Widget child) => MaterialApp(theme: AppTheme.light, home: Scaffold(body: child));

void main() {
  testWidgets('renders the message text', (tester) async {
    await tester.pumpWidget(_wrap(const ChatBubble(text: 'hello', isUser: true)));
    expect(find.text('hello'), findsOneWidget);
  });

  testWidgets('a user bubble right-aligns', (tester) async {
    await tester.pumpWidget(_wrap(const ChatBubble(text: 'hi', isUser: true)));
    final align = tester.widget<Align>(find.byType(Align));
    expect(align.alignment, Alignment.centerRight);
  });

  testWidgets('a Pulse bubble left-aligns', (tester) async {
    await tester.pumpWidget(_wrap(const ChatBubble(text: 'hi', isUser: false)));
    final align = tester.widget<Align>(find.byType(Align));
    expect(align.alignment, Alignment.centerLeft);
  });

  testWidgets('softVariant renders without throwing', (tester) async {
    await tester.pumpWidget(
      _wrap(const ChatBubble(text: 'still here', isUser: false, softVariant: true)),
    );
    expect(find.text('still here'), findsOneWidget);
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `flutter test test/features/chat/widgets/chat_bubble_test.dart`
Expected: FAIL — widget doesn't exist yet.

- [ ] **Step 3: Write the implementation**

```dart
// lib/features/chat/widgets/chat_bubble.dart
import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// The plain user/Pulse bubble pair. [softVariant] is the teal-tint,
/// all-round-radius, no-tail style used for Pulse messages once a
/// conversation is crisis-locked — only Pulse messages get this
/// treatment (see chat_screen.dart's rendering rule).
class ChatBubble extends StatelessWidget {
  const ChatBubble({
    super.key,
    required this.text,
    required this.isUser,
    this.softVariant = false,
  });

  final String text;
  final bool isUser;
  final bool softVariant;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    final BoxDecoration decoration = softVariant
        ? BoxDecoration(
            color: AppColors.tintTeal,
            // Spec: "all-round-24" for the soft crisis-locked Pulse
            // bubble — AppRadii.card (24), not AppRadii.chatBubble (22).
            borderRadius: BorderRadius.circular(AppRadii.card),
          )
        : BoxDecoration(
            color: isUser ? AppColors.primary : AppColors.surface,
            borderRadius: BorderRadius.only(
              topLeft: const Radius.circular(AppRadii.chatBubble),
              topRight: const Radius.circular(AppRadii.chatBubble),
              bottomLeft: Radius.circular(
                isUser ? AppRadii.chatBubble : AppRadii.chatBubbleTail,
              ),
              bottomRight: Radius.circular(
                isUser ? AppRadii.chatBubbleTail : AppRadii.chatBubble,
              ),
            ),
            boxShadow: isUser ? AppShadows.userBubble : AppShadows.card,
          );

    final Color textColor = softVariant
        ? AppColors.crisisBody
        : isUser
            ? Colors.white
            : AppColors.text;

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        // sizeOf (not MediaQuery.of(context).size) scopes the rebuild
        // dependency to just the size field — MediaQuery.of would
        // rebuild every bubble in the list on keyboard open/close too.
        // Found during Task 10 code review — use sizeOf everywhere this
        // max-width pattern is copied (see also Task 13's ErrorBubble).
        constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.78),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 12),
          decoration: decoration,
          child: Text(
            text,
            style: theme.textTheme.bodyMedium?.copyWith(color: textColor),
          ),
        ),
      ),
    );
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `flutter test test/features/chat/widgets/chat_bubble_test.dart`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/features/chat/widgets/chat_bubble.dart test/features/chat/widgets/chat_bubble_test.dart
git commit -m "feat(chat): add ChatBubble widget (user/Pulse/soft-crisis variants)"
```

---

### Task 11: `QuickReplyRow` widget

**Files:**
- Create: `lib/features/chat/widgets/quick_reply_row.dart`
- Test: `test/features/chat/widgets/quick_reply_row_test.dart`

- [ ] **Step 1: Write the failing test**

```dart
// test/features/chat/widgets/quick_reply_row_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/widgets/quick_reply_row.dart';

void main() {
  testWidgets('tapping a chip sends its exact label', (tester) async {
    String? selected;
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: Scaffold(
        body: QuickReplyRow(
          options: const ['Under 38°', '38–39°', 'Over 39°'],
          onSelect: (value) => selected = value,
        ),
      ),
    ));

    await tester.tap(find.text('38–39°'));
    await tester.pump();

    expect(selected, '38–39°');
  });

  testWidgets('renders every option', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: Scaffold(
        body: QuickReplyRow(options: const ['A', 'B', 'C', 'D'], onSelect: (_) {}),
      ),
    ));

    for (final option in ['A', 'B', 'C', 'D']) {
      expect(find.text(option), findsOneWidget);
    }
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/features/chat/widgets/quick_reply_row_test.dart`
Expected: FAIL — widget doesn't exist yet.

- [ ] **Step 3: Write the implementation**

```dart
// lib/features/chat/widgets/quick_reply_row.dart
import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// A single non-wrapping, horizontally scrollable row of quick-reply
/// chips shown below a question turn. Tapping a chip sends its label as
/// the user's next message.
class QuickReplyRow extends StatelessWidget {
  const QuickReplyRow({super.key, required this.options, required this.onSelect});

  final List<String> options;
  final ValueChanged<String> onSelect;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      reverse: true, // anchors to the right, matching the design, even if it overflows
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final option in options) ...[
            OutlinedButton(
              onPressed: () => onSelect(option),
              style: OutlinedButton.styleFrom(
                backgroundColor: AppColors.surface,
                side: const BorderSide(color: AppColors.chipBorder, width: 1.5),
                foregroundColor: AppColors.primaryInk,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppRadii.pill),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 8),
                textStyle: theme.textTheme.titleMedium?.copyWith(fontSize: 13),
              ),
              child: Text(option),
            ),
            const SizedBox(width: 7),
          ],
        ],
      ),
    );
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `flutter test test/features/chat/widgets/quick_reply_row_test.dart`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/features/chat/widgets/quick_reply_row.dart test/features/chat/widgets/quick_reply_row_test.dart
git commit -m "feat(chat): add QuickReplyRow widget"
```

---

### Task 12: `TypingIndicator` widget

**Files:**
- Create: `lib/features/chat/widgets/typing_indicator.dart`
- Test: `test/features/chat/widgets/typing_indicator_test.dart`

- [ ] **Step 1: Write the failing test**

```dart
// test/features/chat/widgets/typing_indicator_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/widgets/typing_indicator.dart';

void main() {
  testWidgets('renders three dots and animates without error', (tester) async {
    await tester.pumpWidget(
      MaterialApp(theme: AppTheme.light, home: const Scaffold(body: TypingIndicator())),
    );

    // Do NOT use pumpAndSettle — the animation repeats forever by design.
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(TypingIndicator), findsOneWidget);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/features/chat/widgets/typing_indicator_test.dart`
Expected: FAIL — widget doesn't exist yet.

- [ ] **Step 3: Write the implementation**

```dart
// lib/features/chat/widgets/typing_indicator.dart
import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// The gentle "Pulse is thinking" indicator shown while awaiting a reply.
class TypingIndicator extends StatefulWidget {
  const TypingIndicator({super.key});

  @override
  State<TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<TypingIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1400),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 15),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(AppRadii.chatBubble),
            topRight: const Radius.circular(AppRadii.chatBubble),
            bottomRight: const Radius.circular(AppRadii.chatBubble),
            bottomLeft: const Radius.circular(AppRadii.chatBubbleTail),
          ),
          boxShadow: AppShadows.card,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: List.generate(3, (i) {
            return AnimatedBuilder(
              animation: _controller,
              builder: (context, child) {
                final t = (_controller.value + i * 0.2) % 1.0;
                final dy = -4 * (t < 0.5 ? t * 2 : (1 - t) * 2);
                return Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 3),
                  child: Transform.translate(
                    offset: Offset(0, dy),
                    child: Container(
                      width: 8,
                      height: 8,
                      decoration: const BoxDecoration(
                        color: AppColors.primary,
                        shape: BoxShape.circle,
                      ),
                    ),
                  ),
                );
              },
            );
          }),
        ),
      ),
    );
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `flutter test test/features/chat/widgets/typing_indicator_test.dart`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add lib/features/chat/widgets/typing_indicator.dart test/features/chat/widgets/typing_indicator_test.dart
git commit -m "feat(chat): add TypingIndicator widget"
```

---

### Task 13: `ErrorBubble` widget

**Files:**
- Create: `lib/features/chat/widgets/error_bubble.dart`
- Test: `test/features/chat/widgets/error_bubble_test.dart`

- [ ] **Step 1: Write the failing test**

```dart
// test/features/chat/widgets/error_bubble_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/widgets/error_bubble.dart';

void main() {
  testWidgets('renders the message and a retry tap resends', (tester) async {
    var retried = false;
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: Scaffold(
        body: ErrorBubble(message: 'Something went wrong', onRetry: () => retried = true),
      ),
    ));

    expect(find.text('Something went wrong'), findsOneWidget);

    await tester.tap(find.text('Tap to try again'));
    await tester.pump();

    expect(retried, isTrue);
  });

  testWidgets('the retry tap target meets the 44px minimum touch target', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: Scaffold(body: ErrorBubble(message: 'msg', onRetry: () {})),
    ));

    final inkWell = tester.getSize(find.byType(InkWell));
    expect(inkWell.height, greaterThanOrEqualTo(AppSpacing.minTouchTarget));
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/features/chat/widgets/error_bubble_test.dart`
Expected: FAIL — widget doesn't exist yet.

- [ ] **Step 3: Write the implementation**

```dart
// lib/features/chat/widgets/error_bubble.dart
import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// The apologetic inline bubble for a degraded/unparseable reply, with a
/// tap-to-retry affordance that resends the last user message.
class ErrorBubble extends StatelessWidget {
  const ErrorBubble({super.key, required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    // Amber accent reused purely for its warm, non-alarming color — an
    // ErrorBubble is a parse/network failure, not a clinical urgency
    // signal. Do not read this as UrgencyLevel.seeDoctorSoon triage.
    // Found during Task 13 code review.
    final honey = theme.extension<UrgencyColors>()!.seeDoctorSoon;

    return Align(
      alignment: Alignment.centerLeft,
      child: ConstrainedBox(
        // sizeOf, not MediaQuery.of(context).size — see Task 10's
        // ChatBubble for why.
        constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.88),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.only(
              topLeft: const Radius.circular(AppRadii.chatBubble),
              topRight: const Radius.circular(AppRadii.chatBubble),
              bottomRight: const Radius.circular(AppRadii.chatBubble),
              bottomLeft: const Radius.circular(AppRadii.chatBubbleTail),
            ),
            boxShadow: AppShadows.card,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 24,
                height: 24,
                margin: const EdgeInsets.only(top: 1),
                decoration: BoxDecoration(color: honey.tint, shape: BoxShape.circle),
                child: Icon(Icons.error_outline, size: 14, color: honey.text),
              ),
              const SizedBox(width: 11),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(message, style: theme.textTheme.bodyMedium),
                    const SizedBox(height: 8),
                    InkWell(
                      onTap: onRetry,
                      borderRadius: BorderRadius.circular(AppRadii.buttonInCard),
                      child: ConstrainedBox(
                        // Genuinely hit AppSpacing.minTouchTarget (44),
                        // not just an incremental improvement — this is
                        // a retry-after-failure affordance, arguably
                        // higher-stakes to get right than an ordinary
                        // link. Found during Task 13 code review.
                        constraints: const BoxConstraints(minHeight: AppSpacing.minTouchTarget),
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: Text(
                            'Tap to try again',
                            style: theme.textTheme.bodyMedium?.copyWith(
                              color: AppColors.primaryInk,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `flutter test test/features/chat/widgets/error_bubble_test.dart`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/features/chat/widgets/error_bubble.dart test/features/chat/widgets/error_bubble_test.dart
git commit -m "feat(chat): add ErrorBubble widget with tap-to-retry"
```

---

### Task 14: `AssessmentCard` widget

**Files:**
- Create: `lib/features/chat/widgets/assessment_card.dart`
- Test: `test/features/chat/widgets/assessment_card_test.dart`

- [ ] **Step 1: Write the failing tests**

```dart
// test/features/chat/widgets/assessment_card_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/widgets/assessment_card.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';

const _populated = UrgencyResult(
  type: ChatTurnType.assessment,
  message: 'msg',
  urgency: UrgencyLevel.seeDoctorSoon,
  explanation: 'explanation text',
  nextStep: 'next step text',
  selfCare: ['Rest', 'Fluids'],
  monitoring: ['Check temperature'],
  watchFor: ['Trouble breathing'],
  encouragement: 'You got this',
);

const _gracefulEmpty = UrgencyResult(
  type: ChatTurnType.assessment,
  message: 'msg',
  urgency: UrgencyLevel.seekCareNow,
  explanation: 'explanation text',
  nextStep: 'next step text',
  watchFor: ['Chest pain'],
  // selfCare and monitoring intentionally omitted (empty)
);

// AssessmentCard is only ever placed inside the chat transcript's scrolling
// ListView (unbounded height), never directly in a bounded Scaffold body —
// so the test harness wraps it in a SingleChildScrollView to match that,
// rather than changing the widget to scroll internally. Found during Task
// 14 implementation: the fully-populated fixture overflows the default
// flutter_test viewport without this.
Widget _wrap(Widget child) => MaterialApp(
      theme: AppTheme.light,
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void main() {
  testWidgets('renders every populated section', (tester) async {
    await tester.pumpWidget(_wrap(AssessmentCard(
      result: _populated,
      checkedSelfCare: const {},
      onToggleSelfCare: (_) {},
    )));

    expect(find.text('See a doctor soon'), findsOneWidget);
    expect(find.text('explanation text'), findsOneWidget);
    expect(find.text('What to do next'), findsOneWidget);
    expect(find.text('next step text'), findsOneWidget);
    expect(find.text('Things you can do today'), findsOneWidget);
    expect(find.text('Rest'), findsOneWidget);
    expect(find.text('Check in on yourself'), findsOneWidget);
    expect(find.text('Get care if…'), findsOneWidget);
    expect(find.text('You got this'), findsOneWidget);
    expect(find.text('Book a GP visit'), findsOneWidget);
  });

  testWidgets('empty self_care and monitoring sections disappear entirely', (tester) async {
    await tester.pumpWidget(_wrap(AssessmentCard(
      result: _gracefulEmpty,
      checkedSelfCare: const {},
      onToggleSelfCare: (_) {},
    )));

    expect(find.text('Things you can do today'), findsNothing);
    expect(find.text('Check in on yourself'), findsNothing);
    // watch_for is populated, so it still renders:
    expect(find.text('Get care if…'), findsOneWidget);
    expect(find.text('Find urgent care nearby'), findsOneWidget);
  });

  testWidgets('the monitor_at_home CTA uses the passive follow-up copy, not a manual-reminder phrase', (tester) async {
    // Not `const AssessmentCard(...)`: onToggleSelfCare is a closure
    // literal, which is never a compile-time constant in Dart. Found
    // during Task 14 implementation — the plan's earlier draft of this
    // test didn't compile as written.
    await tester.pumpWidget(_wrap(AssessmentCard(
      result: const UrgencyResult(
        type: ChatTurnType.assessment,
        message: 'msg',
        urgency: UrgencyLevel.monitorAtHome,
      ),
      checkedSelfCare: const {},
      onToggleSelfCare: (_) {},
    )));

    expect(find.text("Okay — I'll check in on this tomorrow."), findsOneWidget);
  });

  testWidgets('tapping a self-care row calls onToggleSelfCare with its index', (tester) async {
    int? toggledIndex;
    await tester.pumpWidget(_wrap(AssessmentCard(
      result: _populated,
      checkedSelfCare: const {},
      onToggleSelfCare: (i) => toggledIndex = i,
    )));

    await tester.tap(find.text('Fluids'));
    await tester.pump();

    expect(toggledIndex, 1);
  });

  testWidgets('a checked self-care item renders with strikethrough styling', (tester) async {
    await tester.pumpWidget(_wrap(AssessmentCard(
      result: _populated,
      checkedSelfCare: const {0},
      onToggleSelfCare: (_) {},
    )));

    final restText = tester.widget<Text>(find.text('Rest'));
    expect(restText.style?.decoration, TextDecoration.lineThrough);
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `flutter test test/features/chat/widgets/assessment_card_test.dart`
Expected: FAIL — widget doesn't exist yet.

- [ ] **Step 3: Write the implementation**

```dart
// lib/features/chat/widgets/assessment_card.dart
import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../models/urgency_result.dart';

/// The flagship assessment card: tier icon chip + label + eyebrow,
/// explanation, "What to do next", a tappable self-care checklist,
/// monitoring rows, watch-for warning pills, a tier-solid CTA button,
/// and a de-emphasized encouragement line. Every list-backed section
/// (self_care, monitoring, watch_for) disappears entirely when empty.
///
/// Only ever built for `result.type == ChatTurnType.assessment`, which
/// guarantees `result.urgency` is non-null (see UrgencyResult.fromJson).
class AssessmentCard extends StatelessWidget {
  const AssessmentCard({
    super.key,
    required this.result,
    required this.checkedSelfCare,
    required this.onToggleSelfCare,
  });

  final UrgencyResult result;
  final Set<int> checkedSelfCare;
  final ValueChanged<int> onToggleSelfCare;

  static const Map<UrgencyLevel, String> _ctaCopy = {
    // Deliberately NOT "Set a check-in reminder" (that implies the
    // manually configured medication-reminder engine, explicitly
    // deferred past MVP per AGENTS.md). The real MVP-adjacent mechanic
    // is Pulse's automatic, proactive follow-up — passive, not
    // something a button "sets."
    UrgencyLevel.monitorAtHome: "Okay — I'll check in on this tomorrow.",
    UrgencyLevel.seeDoctorSoon: 'Book a GP visit',
    UrgencyLevel.seekCareNow: 'Find urgent care nearby',
  };

  static const Map<UrgencyLevel, IconData> _tierIcon = {
    UrgencyLevel.monitorAtHome: Icons.check_rounded,
    UrgencyLevel.seeDoctorSoon: Icons.access_time_rounded,
    UrgencyLevel.seekCareNow: Icons.priority_high_rounded,
  };

  static const Map<UrgencyLevel, String> _tierLabel = {
    UrgencyLevel.monitorAtHome: 'Monitor at home',
    UrgencyLevel.seeDoctorSoon: 'See a doctor soon',
    UrgencyLevel.seekCareNow: 'Seek care now',
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final urgency = result.urgency!;
    final palette = theme.extension<UrgencyColors>()!.forLevel(urgency);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.cardPaddingMax),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadii.card),
        boxShadow: AppShadows.urgencyCard,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: palette.solid,
                  borderRadius: BorderRadius.circular(AppRadii.iconChip),
                ),
                child: Icon(_tierIcon[urgency], color: Colors.white),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(_tierLabel[urgency]!,
                        style: theme.textTheme.titleLarge?.copyWith(color: palette.text)),
                    const SizedBox(height: 4),
                    Text('PULSE GUIDANCE', style: theme.textTheme.labelMedium),
                  ],
                ),
              ),
            ],
          ),
          if (result.explanation != null) ...[
            const SizedBox(height: 14),
            Text(result.explanation!, style: theme.textTheme.bodyMedium),
          ],
          if (result.nextStep != null) ...[
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 13),
              child: Divider(height: 1),
            ),
            Text('What to do next', style: theme.textTheme.titleSmall),
            const SizedBox(height: 4),
            Text(result.nextStep!, style: theme.textTheme.bodyMedium),
          ],
          if (result.selfCare.isNotEmpty) ...[
            const SizedBox(height: 18),
            Text('Things you can do today', style: theme.textTheme.titleSmall),
            const SizedBox(height: 9),
            for (var i = 0; i < result.selfCare.length; i++)
              _SelfCareRow(
                text: result.selfCare[i],
                done: checkedSelfCare.contains(i),
                onTap: () => onToggleSelfCare(i),
              ),
          ],
          if (result.monitoring.isNotEmpty) ...[
            const SizedBox(height: 18),
            Text('Check in on yourself', style: theme.textTheme.titleSmall),
            const SizedBox(height: 9),
            for (final m in result.monitoring) _MonitoringRow(text: m),
          ],
          if (result.watchFor.isNotEmpty) ...[
            const SizedBox(height: 18),
            Text('Get care if…', style: theme.textTheme.titleSmall),
            const SizedBox(height: 9),
            for (final w in result.watchFor) _WatchForPill(text: w),
          ],
          const SizedBox(height: 18),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              // TODO(care-finder): wire once the care-finder feature exists.
              // Visual affordance only this pass.
              onPressed: () {},
              style: ElevatedButton.styleFrom(
                backgroundColor: palette.solid,
                foregroundColor: Colors.white,
                minimumSize: const Size.fromHeight(50),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppRadii.buttonInCard),
                ),
              ),
              child: Text(_ctaCopy[urgency]!),
            ),
          ),
          if (result.encouragement != null) ...[
            const SizedBox(height: 12),
            Text(
              result.encouragement!,
              textAlign: TextAlign.center,
              style: theme.textTheme.bodySmall?.copyWith(color: AppColors.textFaintAlt),
            ),
          ],
        ],
      ),
    );
  }
}

class _SelfCareRow extends StatelessWidget {
  const _SelfCareRow({required this.text, required this.done, required this.onTap});
  final String text;
  final bool done;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppRadii.cardRowRadius),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 11),
          decoration: BoxDecoration(
            color: AppColors.selfCareRowBg,
            borderRadius: BorderRadius.circular(AppRadii.cardRowRadius),
          ),
          child: Row(
            children: [
              Container(
                width: 24,
                height: 24,
                decoration: BoxDecoration(
                  color: done ? AppColors.selfCareChecked : Colors.white,
                  borderRadius: BorderRadius.circular(8),
                  border: done
                      ? null
                      : Border.all(color: AppColors.selfCareUncheckedBorder, width: 2),
                ),
                child: done ? const Icon(Icons.check, size: 15, color: Colors.white) : null,
              ),
              const SizedBox(width: 11),
              Expanded(
                child: Text(
                  text,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: done ? AppColors.selfCareCheckedText : AppColors.text,
                    decoration: done ? TextDecoration.lineThrough : null,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MonitoringRow extends StatelessWidget {
  const _MonitoringRow({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 11),
        decoration: BoxDecoration(
          color: AppColors.tintTeal,
          borderRadius: BorderRadius.circular(AppRadii.cardRowRadius),
        ),
        child: Row(
          children: [
            const Icon(Icons.history_rounded, size: 15, color: AppColors.primaryInk),
            const SizedBox(width: 11),
            Expanded(child: Text(text, style: Theme.of(context).textTheme.bodyMedium)),
          ],
        ),
      ),
    );
  }
}

class _WatchForPill extends StatelessWidget {
  const _WatchForPill({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    final coral = Theme.of(context).extension<UrgencyColors>()!.seekCareNow;
    return Padding(
      padding: const EdgeInsets.only(bottom: 7),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 10),
        decoration: BoxDecoration(
          color: coral.tint,
          borderRadius: BorderRadius.circular(AppRadii.pillRowRadius),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.warning_amber_rounded, size: 17, color: coral.text),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                text,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: coral.text),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `flutter test test/features/chat/widgets/assessment_card_test.dart`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/features/chat/widgets/assessment_card.dart test/features/chat/widgets/assessment_card_test.dart
git commit -m "feat(chat): add AssessmentCard widget with session-only self-care checklist"
```

---

### Task 15: `CrisisCard` widget

**Files:**
- Create: `lib/features/chat/widgets/crisis_card.dart`
- Test: `test/features/chat/widgets/crisis_card_test.dart`

- [ ] **Step 1: Write the failing tests**

```dart
// test/features/chat/widgets/crisis_card_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/constants/crisis_resources.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/widgets/crisis_card.dart';

void main() {
  testWidgets('renders the message and every crisis resource', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: Scaffold(body: CrisisCard(message: 'Nandito lang ako.', launcher: (_) async => true)),
    ));

    expect(find.text('Nandito lang ako.'), findsOneWidget);
    for (final resource in crisisResources) {
      expect(find.text(resource.name), findsOneWidget);
    }
  });

  testWidgets('tapping a resource row calls the launcher with its phone URI', (tester) async {
    Uri? launched;
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: Scaffold(
        body: CrisisCard(
          message: 'msg',
          launcher: (uri) async {
            launched = uri;
            return true;
          },
        ),
      ),
    ));

    await tester.tap(find.text(crisisResources.first.name));
    await tester.pump();

    expect(launched, Uri.parse(crisisResources.first.phoneUri));
  });

  testWidgets('shows a fallback message with the number spelled out when the launcher fails', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: Scaffold(
        body: CrisisCard(message: 'msg', launcher: (_) async => false),
      ),
    ));

    await tester.tap(find.text(crisisResources.first.name));
    await tester.pumpAndSettle();

    expect(find.textContaining(crisisResources.first.number), findsWidgets);
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `flutter test test/features/chat/widgets/crisis_card_test.dart`
Expected: FAIL — widget doesn't exist yet.

- [ ] **Step 3: Write the implementation**

```dart
// lib/features/chat/widgets/crisis_card.dart
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/constants/crisis_resources.dart';
import '../../../core/theme/app_theme.dart';

/// The crisis card: teal-tint, spacious, deliberately no tier machinery.
/// Message text, then a "Someone to talk to" resource list rendered from
/// the app-side crisisResources constant, tap-to-dial via url_launcher.
class CrisisCard extends StatelessWidget {
  const CrisisCard({
    super.key,
    required this.message,
    this.launcher = launchUrl,
  });

  final String message;

  /// Injectable so widget tests don't hit the real url_launcher plugin.
  final Future<bool> Function(Uri) launcher;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      width: double.infinity,
      // 22 is exactly AppSpacing.cardPaddingMax — use the token, not the
      // literal, matching AssessmentCard's own use of the same constant.
      padding: const EdgeInsets.all(AppSpacing.cardPaddingMax),
      decoration: BoxDecoration(
        color: AppColors.tintTeal,
        borderRadius: BorderRadius.circular(AppRadii.crisisCard),
        boxShadow: AppShadows.crisisCard,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: const BoxDecoration(
                  gradient: LinearGradient(
                    colors: [AppColors.companionGradientLight, AppColors.primary],
                  ),
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  "I'm really glad you told me",
                  style: theme.textTheme.titleLarge
                      ?.copyWith(fontSize: 16, color: AppColors.crisisHeading),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Text(
            message,
            style: theme.textTheme.bodyMedium
                ?.copyWith(fontSize: 15, height: 1.62, color: AppColors.crisisBody),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 20),
            child: Divider(
              height: 1,
              // Mockup divider is primaryInk at ~16% opacity (#293F7A86)
              // — withAlpha(0x29) reproduces that exact byte rather than
              // hardcoding a new standalone hex value.
              color: AppColors.primaryInk.withAlpha(0x29),
            ),
          ),
          Text('Someone to talk to',
              style: theme.textTheme.titleSmall?.copyWith(color: AppColors.primaryInk)),
          const SizedBox(height: 11),
          for (final resource in crisisResources)
            Padding(
              padding: const EdgeInsets.only(bottom: 9),
              child: InkWell(
                // Note: 18 doesn't map to an existing AppRadii token (the
                // closest named row radii are cardRowRadius/14 and
                // pillRowRadius/13 from AssessmentCard's rows) — left as
                // an inline literal rather than reusing a
                // visually-different value; a real gap worth tokenizing
                // in a follow-up pass alongside the rest of §8.
                borderRadius: BorderRadius.circular(18),
                // This is the single highest-stakes tap target in the
                // whole feature — a hotline row for a user the app has
                // just flagged as possibly in crisis. A silent no-op if
                // launchUrl returns false (no dialer app) or throws
                // (platform exception) is the worst failure mode to
                // leave unhandled here. Found during Task 15 code
                // review — fall back to a visible message with the
                // number spelled out rather than fire-and-forget.
                onTap: () async {
                  var launched = false;
                  try {
                    launched = await launcher(Uri.parse(resource.phoneUri));
                  } catch (_) {
                    launched = false;
                  }
                  if (!launched && context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        backgroundColor: AppColors.primaryDeep,
                        content: Text("Couldn't reach your dialer. ${resource.number}."),
                      ),
                    );
                  }
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 14),
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(18),
                    boxShadow: AppShadows.card,
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 40,
                        height: 40,
                        decoration:
                            const BoxDecoration(color: AppColors.tintTeal, shape: BoxShape.circle),
                        child: const Icon(Icons.phone_outlined,
                            color: AppColors.primaryInk, size: 19),
                      ),
                      const SizedBox(width: 13),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(resource.name,
                                style: theme.textTheme.titleMedium?.copyWith(fontSize: 14.5)),
                            const SizedBox(height: 2),
                            Text(resource.number,
                                style: theme.textTheme.bodyMedium?.copyWith(fontSize: 13)),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          const SizedBox(height: 4),
          Text(
            "No pressure at all. I'll still be here whenever you want to keep talking.",
            textAlign: TextAlign.center,
            style: theme.textTheme.bodySmall?.copyWith(color: AppColors.crisisFooterText),
          ),
        ],
      ),
    );
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `flutter test test/features/chat/widgets/crisis_card_test.dart`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/features/chat/widgets/crisis_card.dart test/features/chat/widgets/crisis_card_test.dart
git commit -m "feat(chat): add CrisisCard widget with injectable tap-to-dial launcher"
```

---

### Task 16: `ChatInputBar` widget

**Files:**
- Create: `lib/features/chat/widgets/chat_input_bar.dart`
- Test: `test/features/chat/widgets/chat_input_bar_test.dart`

- [ ] **Step 1: Write the failing tests**

```dart
// test/features/chat/widgets/chat_input_bar_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/widgets/chat_input_bar.dart';

Widget _wrap(Widget child) => MaterialApp(theme: AppTheme.light, home: Scaffold(body: child));

void main() {
  testWidgets('typing then tapping send calls onSend with the trimmed text', (tester) async {
    String? sent;
    await tester.pumpWidget(_wrap(ChatInputBar(onSend: (t) => sent = t)));

    await tester.enterText(find.byType(TextField), '  hello there  ');
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pump();

    expect(sent, 'hello there');
  });

  testWidgets('the field clears after sending', (tester) async {
    await tester.pumpWidget(_wrap(ChatInputBar(onSend: (_) {})));

    await tester.enterText(find.byType(TextField), 'hello');
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pump();

    final field = tester.widget<TextField>(find.byType(TextField));
    expect(field.controller!.text, isEmpty);
  });

  testWidgets('an empty message does not call onSend', (tester) async {
    var called = false;
    await tester.pumpWidget(_wrap(ChatInputBar(onSend: (_) => called = true)));

    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pump();

    expect(called, isFalse);
  });

  testWidgets('a disabled ChatInputBar dims the send button and ignores taps', (tester) async {
    var called = false;
    await tester.pumpWidget(_wrap(ChatInputBar(onSend: (_) => called = true, enabled: false)));

    final container = tester.widget<Container>(
      find.byKey(const Key('chatInputBar.sendButtonFill')),
    );
    final decoration = container.decoration! as BoxDecoration;
    expect(decoration.color, AppColors.primaryDeep.withValues(alpha: 0.4));

    await tester.tap(find.byIcon(Icons.arrow_upward_rounded), warnIfMissed: false);
    await tester.pump();

    expect(called, isFalse);
  });

  testWidgets(
    'the char-counter row height is constant across remaining values, isolated from '
    'TextField wrapping and ambient parent constraints',
    (tester) async {
      // Deliberately does NOT measure ChatInputBar's outer size: under
      // Scaffold(body: ChatInputBar(...)), the root Column receives a
      // bounded height and (mainAxisSize.max, the default) fills it
      // regardless of content, so the outer size tracks the viewport,
      // not the widget's real content height — an earlier version of
      // this test measured the outer size and passed even with the
      // original bug reintroduced (verified by deliberately
      // reintroducing it during code review). Measuring the counter
      // row's own keyed size sidesteps that, and also avoids
      // conflating the counter with the TextField's separate
      // up-to-4-line growth as more text is typed.
      Future<double> counterRowHeightFor(int length) async {
        await tester.pumpWidget(_wrap(ChatInputBar(onSend: (_) {})));
        await tester.enterText(find.byType(TextField), 'x' * length);
        await tester.pump();
        return tester.getSize(find.byKey(const Key('chatInputBar.counterRow'))).height;
      }

      final hidden = await counterRowHeightFor(0); // remaining = 2000
      final visible = await counterRowHeightFor(1850); // remaining = 150
      final atZero = await counterRowHeightFor(2000); // remaining = 0

      expect(visible, hidden);
      expect(atZero, hidden);
    },
  );
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `flutter test test/features/chat/widgets/chat_input_bar_test.dart`
Expected: FAIL — widget doesn't exist yet.

- [ ] **Step 3: Write the implementation**

```dart
// lib/features/chat/widgets/chat_input_bar.dart
import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// The message input pill: text field with a 2000-char client-side cap
/// (matching functions/main.py's MAX_MESSAGE_LENGTH), a friendly counter
/// shown only near the limit, a mic icon (TODO: visual only this pass —
/// no voice input yet), and a circular send button.
class ChatInputBar extends StatefulWidget {
  const ChatInputBar({super.key, required this.onSend, this.enabled = true});

  final ValueChanged<String> onSend;
  final bool enabled;

  @override
  State<ChatInputBar> createState() => _ChatInputBarState();
}

class _ChatInputBarState extends State<ChatInputBar> {
  static const _maxLength = 2000;
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    // Guarding here (not just via the button's onTap ternary / the
    // TextField's own `enabled`) means both entry points — the send
    // button and TextField.onSubmitted — funnel through one function
    // that respects `enabled` unconditionally. Found during Task 16
    // code review.
    if (!widget.enabled) return;
    final text = _controller.text.trim();
    if (text.isEmpty) return;
    widget.onSend(text);
    setState(_controller.clear);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final remaining = _maxLength - _controller.text.length;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        // Always rendered (never a conditionally-inserted sibling), only
        // opacity toggles: this widget sits directly above the scrolling
        // transcript's Expanded ListView in Task 17's Column, so if the
        // counter's presence changed ChatInputBar's total height, the
        // transcript viewport would instantly snap taller/shorter the
        // moment a message crosses 1800 chars — jarring mid-typing.
        // Deliberately NOT wrapped in a fixed-height SizedBox: an
        // earlier version of this fix used SizedBox(height: 20), which
        // clips the text at larger accessibility text-scale settings
        // (Android "Large"/iOS "Larger Text", both mainstream, not edge
        // cases — verified against Flutter's RenderParagraph/Align
        // layout behavior). Letting Text size itself naturally still
        // eliminates the jank, since a single-line "N left" string has
        // the same intrinsic height regardless of which digits it
        // shows — found during Task 16 code review.
        Align(
          // Keyed so a test can measure this row's own height in
          // isolation from the surrounding ambient layout (a Column's
          // resolved size depends on its parent's constraints, and the
          // TextField below can itself grow up to maxLines: 4 — neither
          // should be conflated with whether this specific row's height
          // is stable). Found during Task 16 code review, after an
          // earlier regression test measuring the whole widget's outer
          // size turned out to pass even with the original bug
          // reintroduced.
          key: const Key('chatInputBar.counterRow'),
          alignment: Alignment.centerRight,
          child: Padding(
            padding: const EdgeInsets.only(right: 8, bottom: 4),
            child: AnimatedOpacity(
              opacity: remaining <= 200 ? 1 : 0,
              duration: const Duration(milliseconds: 150),
              child: Text(
                '$remaining left',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: remaining <= 0 ? AppColors.crisisFooterText : AppColors.textFaint,
                ),
              ),
            ),
          ),
        ),
        Container(
          padding: const EdgeInsets.fromLTRB(18, 8, 8, 8),
          decoration: BoxDecoration(
            color: AppColors.surface,
            // inputBar, not the generic pill token — the design doc
            // specifies a fixed 22px radius here, distinct from the
            // 999px stadium used for chips/badges. Found during code
            // review: with maxLines: 4, a true 999 stadium and a fixed
            // 22px corner look different once the field grows.
            borderRadius: BorderRadius.circular(AppRadii.inputBar),
            boxShadow: AppShadows.card,
          ),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _controller,
                  maxLength: _maxLength,
                  enabled: widget.enabled,
                  minLines: 1,
                  maxLines: 4,
                  onChanged: (_) => setState(() {}),
                  onSubmitted: (_) => _submit(),
                  buildCounter: (_, {required currentLength, required isFocused, maxLength}) =>
                      null,
                  decoration: InputDecoration(
                    border: InputBorder.none,
                    isDense: true,
                    hintText: 'Message Pulse…',
                    hintStyle: theme.textTheme.bodyMedium?.copyWith(color: AppColors.textFaintAlt),
                  ),
                ),
              ),
              // Mic — TODO: visual only this pass, wire voice input later.
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 6),
                child: Icon(Icons.mic_none_rounded, color: AppColors.primary),
              ),
              InkWell(
                onTap: widget.enabled ? _submit : null,
                borderRadius: BorderRadius.circular(21),
                child: Container(
                  // Keyed so tests target this exact Container by
                  // identity rather than "nearest Container ancestor of
                  // the icon" — that ancestor-position match would
                  // silently start matching a different Container if
                  // one were ever added between the icon and this one.
                  // Found during Task 16 code review.
                  key: const Key('chatInputBar.sendButtonFill'),
                  width: 42,
                  height: 42,
                  decoration: BoxDecoration(
                    // Dimmed when disabled so the button doesn't look
                    // tappable while chatIsSendingProvider is true and
                    // onTap is silently null — found during Task 16
                    // code review (Task 17 wires enabled: !isLoading).
                    color: widget.enabled
                        ? AppColors.primaryDeep
                        : AppColors.primaryDeep.withValues(alpha: 0.4),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.arrow_upward_rounded, color: Colors.white, size: 20),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `flutter test test/features/chat/widgets/chat_input_bar_test.dart`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/features/chat/widgets/chat_input_bar.dart test/features/chat/widgets/chat_input_bar_test.dart
git commit -m "feat(chat): add ChatInputBar widget with 2000-char cap"
```

---

### Task 17: `ChatScreen` assembly — COMPLETE

**Files:**
- Modify: `lib/features/chat/screens/chat_screen.dart` (replaces the stub)
- Test: `test/features/chat/screens/chat_screen_test.dart`

This is where the higher-level behavioral tests from the spec's Testing Plan live — chip tap, crisis persistence, error-retry, empty-section disappearance-in-context — since they need the full turn cycle through `ChatController` + `FixtureChatRepository`. `chatRepositoryProvider` is overridden per-test with a small in-line fake for determinism (not the real cycling `FixtureChatRepository`, whose cycle order shouldn't be a test dependency).

**A note on test timing, found and corrected during implementation:** the screen's `_scrollToBottom` uses `animateTo` (250ms, easeOut) — deliberately, to keep the "gentle" auto-scroll the design calls for. An initial implementation pass hit `animateTo`'s interaction with `ListView.separated`'s lazy building (a message scrolled beyond the viewport + cache extent isn't actually built until the scroll position that reveals it is reached) and "fixed" this by switching production code to an instant `jumpTo` — which made the given tests pass, but silently replaced the intended animated scroll with an instant snap for every real user, in every real usage, not just in tests. Caught in review: the correct fix is `tester.pumpAndSettle()` after each send/tap (awaits both the async repository call and the full scroll animation) instead of the fixed `pump(); pump(50ms); pump();` sequence — this keeps `animateTo` in production and makes the tests reflect real behavior rather than working around a test-only symptom. The test code below already reflects the corrected version.

**A second bug, found during code-quality review after Step 4 first passed:** `ref.listen(chatControllerProvider, (_, __) => _scrollToBottom())` fires on *every* state change on that provider — including `toggleSelfCare()`, which uses the exact same `ChatController`/provider to flip a checklist item. So checking a self-care box on an `AssessmentCard` that wasn't the last thing on screen yanked the viewport back to the bottom mid-interaction. Fix: compare list lengths in the listener and only call `_scrollToBottom()` when a turn was actually appended (`next.value!.length > previous?.value?.length`), not on every emission. A 4th test guards this (below). The first version of that test passed even with the bug still present — a single assessment card doesn't produce enough content to make the transcript genuinely scrollable in the default test viewport, so `maxScrollExtent` was 0 and the "position didn't change" assertion passed vacuously. Fixed by shrinking the test's physical viewport (`tester.view.physicalSize = const Size(400, 500)`) to force real scrollability, plus an explicit `expect(maxScrollExtent, greaterThan(0))` guard so the test can't silently degenerate back into a no-op. Verified per this project's standing methodology: reverted the length-guard back to the naive one-liner and confirmed the test genuinely fails (`offset` snapped to `79.0`, the bottom, instead of staying at the scrolled-up `39.5`), then restored the fix and confirmed all 4 tests pass again.

- [x] **Step 1: Write the failing tests**

```dart
// test/features/chat/screens/chat_screen_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/models/message.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';
import 'package:pulse_app/features/chat/providers/chat_provider.dart';
import 'package:pulse_app/features/chat/repositories/chat_repository.dart';
import 'package:pulse_app/features/chat/screens/chat_screen.dart';

/// Returns a fixed sequence of replies, one per call, then repeats the
/// last one — lets each test script exactly the turns it needs.
class _ScriptedRepository implements ChatRepository {
  _ScriptedRepository(this._script);
  final List<UrgencyResult> _script;
  int _i = 0;

  @override
  Future<Message> send({required String text, required List<Message> history}) async {
    final reply = _script[_i < _script.length ? _i : _script.length - 1];
    _i++;
    return Message.assistant(reply);
  }
}

Future<void> _pump(WidgetTester tester, ChatRepository repository) async {
  await tester.pumpWidget(ProviderScope(
    overrides: [chatRepositoryProvider.overrideWithValue(repository)],
    child: MaterialApp(theme: AppTheme.light, home: const ChatScreen()),
  ));
  await tester.pump();
}

void main() {
  testWidgets('tapping a quick-reply chip sends its label as the next user message', (tester) async {
    await _pump(tester, _ScriptedRepository([
      const UrgencyResult(
        type: ChatTurnType.question,
        message: 'How high has your fever been?',
        quickReplies: ['Under 38°', '38–39°'],
      ),
    ]));

    await tester.enterText(find.byType(TextField), 'I have a fever');
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    // pumpAndSettle, not a fixed pump budget: awaits both the async
    // repository call AND the 250ms auto-scroll animation. A fixed
    // pump(); pump(50ms); pump(); sequence isn't enough time for the
    // scroll animation to complete, and ListView.separated doesn't
    // build a message until the scroll position that reveals it is
    // actually reached — found during Task 17 implementation.
    await tester.pumpAndSettle();

    expect(find.text('38–39°'), findsOneWidget);
    await tester.tap(find.text('38–39°'));
    await tester.pump();

    expect(find.text('38–39°'), findsWidgets); // the chip label, now also the sent user bubble
  });

  testWidgets('once a crisis turn arrives, a second crisis-type reply renders as the soft bubble, not a second full card', (tester) async {
    await _pump(tester, _ScriptedRepository([
      const UrgencyResult(type: ChatTurnType.crisis, message: 'first crisis reply'),
      const UrgencyResult(type: ChatTurnType.crisis, message: 'second crisis reply'),
    ]));

    await tester.enterText(find.byType(TextField), 'I feel hopeless');
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pumpAndSettle();

    expect(find.text('Someone to talk to'), findsOneWidget); // full crisis card

    await tester.enterText(find.byType(TextField), 'still feeling this way');
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pumpAndSettle();

    // Still exactly one full crisis card (resource list), even though a
    // second crisis-type message arrived — it rendered as the soft bubble.
    expect(find.text('Someone to talk to'), findsOneWidget);
    expect(find.text('second crisis reply'), findsOneWidget);
  });

  testWidgets('error-retry resends the last user message', (tester) async {
    var calls = 0;
    final repository = _CountingThenSucceedingRepository(() => calls++);

    await tester.pumpWidget(ProviderScope(
      overrides: [chatRepositoryProvider.overrideWithValue(repository)],
      child: MaterialApp(theme: AppTheme.light, home: const ChatScreen()),
    ));

    await tester.enterText(find.byType(TextField), 'I have a fever');
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pumpAndSettle();

    expect(find.text('Tap to try again'), findsOneWidget);
    expect(calls, 1);

    await tester.tap(find.text('Tap to try again'));
    await tester.pumpAndSettle();

    expect(calls, 2);
    expect(find.text('I have a fever'), findsOneWidget); // exactly one, not duplicated
  });

  testWidgets('toggling a self-care checkbox does not trigger an auto-scroll-to-bottom', (tester) async {
    // A shrunk physical viewport (rather than relying on a single assessment
    // card's natural height) guarantees the transcript is genuinely
    // scrollable — without this, maxScrollExtent can be 0 in the default
    // test viewport, silently making the assertion below pass even with
    // the bug this test exists to catch reintroduced (verified: this exact
    // test, unmodified except for this viewport shrink, fails against the
    // pre-fix code and passes against the fix).
    tester.view.physicalSize = const Size(400, 500);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await _pump(tester, _ScriptedRepository([
      const UrgencyResult(
        type: ChatTurnType.assessment,
        message: 'msg',
        urgency: UrgencyLevel.monitorAtHome,
        selfCare: ['Rest', 'Fluids'],
      ),
    ]));

    await tester.enterText(find.byType(TextField), 'I have a mild cold');
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pumpAndSettle();

    final controller = tester.widget<ListView>(find.byType(ListView)).controller!;
    expect(
      controller.position.maxScrollExtent,
      greaterThan(0),
      reason: 'test setup must produce a genuinely scrollable transcript',
    );

    // Simulate the user having scrolled up from the bottom to read something
    // earlier, then toggling a checkbox — this must not yank them back down.
    final midpoint = controller.position.maxScrollExtent / 2;
    controller.jumpTo(midpoint);
    await tester.pump();
    final offsetBeforeToggle = controller.offset;

    await tester.tap(find.text('Rest'));
    await tester.pumpAndSettle();

    expect(controller.offset, offsetBeforeToggle);
  });
}

class _CountingThenSucceedingRepository implements ChatRepository {
  _CountingThenSucceedingRepository(this._onCall);
  final void Function() _onCall;

  @override
  Future<Message> send({required String text, required List<Message> history}) async {
    _onCall();
    throw Exception('down');
  }
}
```

- [x] **Step 2: Run tests to verify they fail**

Run: `flutter test test/features/chat/screens/chat_screen_test.dart`
Expected: FAIL — `chat_screen.dart` still has the old stub, doesn't render any of this.

- [x] **Step 3: Write the implementation**

```dart
// lib/features/chat/screens/chat_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_theme.dart';
import '../models/message.dart';
import '../models/urgency_result.dart';
import '../providers/chat_provider.dart';
import '../widgets/assessment_card.dart';
import '../widgets/chat_bubble.dart';
import '../widgets/chat_input_bar.dart';
import '../widgets/crisis_card.dart';
import '../widgets/error_bubble.dart';
import '../widgets/quick_reply_row.dart';
import '../widgets/typing_indicator.dart';

class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({super.key});

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final _scrollController = ScrollController();

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    // Only scroll when a turn was actually appended (list length grew), not
    // on every state change — chatControllerProvider also emits a new state
    // on toggleSelfCare() (checking a self-care box), which uses the exact
    // same provider. Without this guard, ticking a checklist item on an
    // AssessmentCard that isn't the last thing on screen would yank the
    // viewport to the bottom mid-interaction. Found during code review.
    ref.listen(chatControllerProvider, (previous, next) {
      final previousLength = previous?.value?.length ?? 0;
      final nextLength = next.value?.length ?? 0;
      if (nextLength > previousLength) _scrollToBottom();
    });
    final state = ref.watch(chatControllerProvider);
    final messages = state.value ?? const <Message>[];
    // Not state.isLoading: see chatIsSendingProvider's doc comment in
    // chat_provider.dart for why (AsyncLoading.copyWithPrevious is
    // @internal in this Riverpod version, so chatControllerProvider's
    // own AsyncValue never actually enters a loading state).
    final isLoading = ref.watch(chatIsSendingProvider);
    final firstCrisisIndex =
        messages.indexWhere((m) => m.payload?.type == ChatTurnType.crisis);

    return Scaffold(
      backgroundColor: AppColors.bgCream,
      appBar: AppBar(
        backgroundColor: AppColors.bgCream,
        elevation: 0,
        title: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  colors: [AppColors.companionGradientLight, AppColors.primary],
                ),
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 12),
            Text('Pulse', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontSize: 16)),
          ],
        ),
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.separated(
              controller: _scrollController,
              padding: const EdgeInsets.all(18),
              itemCount: messages.length + (isLoading ? 1 : 0),
              separatorBuilder: (_, __) => const SizedBox(height: 9),
              itemBuilder: (context, index) {
                if (index >= messages.length) {
                  return const TypingIndicator();
                }
                return _buildTurn(messages[index], index, firstCrisisIndex);
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(18, 8, 18, 16),
            child: ChatInputBar(
              enabled: !isLoading,
              onSend: (text) => ref.read(chatControllerProvider.notifier).send(text),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTurn(Message message, int index, int firstCrisisIndex) {
    if (message.role == MessageRole.user) {
      return ChatBubble(text: message.text, isUser: true);
    }

    final payload = message.payload;
    if (payload == null) {
      // Defensive only: every assistant Message in this codebase is built
      // via Message.assistant(payload), which always sets a non-null
      // payload — there's currently no code path that reaches this branch.
      // Kept because Message.payload is legitimately typed nullable at the
      // model level (a future direct Message(...) construction, e.g. from
      // a persisted/rehydrated turn, could produce one), and rendering the
      // raw text as a plain bubble is a strictly better failure mode here
      // than a null-check crash.
      return ChatBubble(text: message.text, isUser: false);
    }

    switch (payload.type) {
      case ChatTurnType.crisis:
        if (index == firstCrisisIndex) {
          return CrisisCard(message: payload.message);
        }
        return ChatBubble(text: payload.message, isUser: false, softVariant: true);
      case ChatTurnType.question:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ChatBubble(text: payload.message, isUser: false),
            if (payload.quickReplies.isNotEmpty) ...[
              const SizedBox(height: 9),
              QuickReplyRow(
                options: payload.quickReplies,
                onSelect: (option) =>
                    ref.read(chatControllerProvider.notifier).send(option),
              ),
            ],
          ],
        );
      case ChatTurnType.assessment:
        return AssessmentCard(
          result: payload,
          checkedSelfCare: message.checkedSelfCare,
          onToggleSelfCare: (i) =>
              ref.read(chatControllerProvider.notifier).toggleSelfCare(message.id, i),
        );
      case ChatTurnType.error:
      case ChatTurnType.unparseable:
        return ErrorBubble(
          message: payload.message,
          onRetry: () => ref.read(chatControllerProvider.notifier).retryLast(),
        );
    }
  }
}
```

- [x] **Step 4: Run tests to verify they pass**

Run: `flutter test test/features/chat/screens/chat_screen_test.dart`
Result: PASS (4 tests, including the scroll-guard regression test added during code review)

- [x] **Step 5: Commit**

Landed as three commits rather than one, since the code-review fixes and a pre-existing uncommitted doc change surfaced along the way:
- `5a8d1c3` / `e2a3394` — initial assembly + tests (`animateTo`/`pumpAndSettle` correction folded in before first commit)
- `15367e4` — `fix(chat): only auto-scroll when a turn is appended, not on every self-care toggle` (the `ref.listen` length-guard fix, its regression test, regenerated linux/macos/windows plugin registrants for the Task 6 `url_launcher` addition, and removal of a leftover scratch repro file)
- `a0468c0` — `docs(agents): log flutter_chat_ui reversal and url_launcher approval` (AGENTS.md content approved during the design-spec pass, copied into the worktree uncommitted at setup time and never landed until now)

---

### Task 18: Full validation + manual fixture-mode run

**Files:** none (verification only)

- [ ] **Step 1: Static analysis**

Run: `flutter analyze`
Expected: "No issues found!"

- [ ] **Step 2: Formatting**

Run: `dart format --set-exit-if-changed .`
Expected: exit 0, no files needing changes. If it fails, run `dart format .` then re-run this check.

- [ ] **Step 3: Full test suite**

Run: `flutter test`
Expected: all tests pass (the pre-existing `test/widget_test.dart` plus every test file added in Tasks 1–17).

- [ ] **Step 4: Manual fixture-mode run — confirm all 6 states render**

Run: `flutter run` (any connected device/emulator; `_useFixturesInDebug` in `chat_provider.dart` defaults to true, so this is automatic in a debug build). Navigate to the Chat tab and send a message 6 times in a row, confirming in order:
1. A Pulse bubble + a quick-reply chip row (tap a chip — it should send as the next user message)
2. The `see_doctor_soon` assessment card, every section populated
3. The `monitor_at_home` assessment card, every section populated, CTA reads "Okay — I'll check in on this tomorrow."
4. The `seek_care_now` assessment card — confirm the self-care and monitoring sections are entirely absent (not empty placeholders), watch-for pills still present, CTA reads "Find urgent care nearby"
5. The crisis card — confirm the resource rows render and (if on a device that can dial) tapping one attempts to dial
6. The error bubble — confirm "Tap to try again" resends and the cycle continues from fixture 1

Screenshot each of the 6 states if the environment allows.

- [ ] **Step 5: Final commit (only if any of the above required fixes)**

```bash
git add -A
git commit -m "chore(chat): fix analyzer/format/test issues found during final validation"
```

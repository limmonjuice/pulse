# Chat Screen — Design Spec

Date: 2026-07-10
Status: Approved by owner, pending spec review pass

## Purpose

Implement the real Chat screen — Pulse's core loop UI — matching the
approved `Pulse Chat.dc.html` mockup (imported via the DesignSync tool
from the "Pulse Health Companion" claude.ai/design project,
`projectId 7eee1145-9213-4c2e-aa81-b7f53f49cbdc`) pixel-faithfully, and
wire it to the `assess_symptoms` callable. Built fixture-first: the
entire UI must be buildable and reviewable with zero API calls; live
wiring is the final step behind a debug-only flag.

## Backend contract (reference)

`assess_symptoms` (Cloud Function, `asia-southeast1`) returns one JSON
payload per turn. Confirmed against `functions/main.py` and
`functions/gemini_client.py`:

- `type`: `"question" | "assessment" | "crisis" | "error"` (the model
  itself never emits `"error"` — that's constructed only in `main.py`
  for degraded mode)
- `message`: string
- `quick_replies`: `[string]`, 2-4 entries iff `type == "question"`, else `[]`
- `urgency`: `"monitor_at_home" | "see_doctor_soon" | "seek_care_now" | null`,
  non-null iff `type == "assessment"`
- `explanation`: `string | null`
- `watch_for`: `[string]`
- `next_step`: `string | null`
- `self_care`: `[string]`
- `monitoring`: `[string]` — already-combined strings (e.g. "Sukatin ang
  temperatura kada 4-6 oras"), **not** `{text, cadence}` pairs
- `encouragement`: `string | null`
- `metadata`: `{prompt_version, red_flag_matched, red_flag_rule_ids,
  model_name}` — kept in the model, never rendered

**Discrepancy found and flagged:** the actual wire payload also always
includes a `possibilities_mentioned` boolean (required by
`gemini_client.REQUIRED_FIELDS`, spread straight through in
`run_pipeline`'s return) — a 12th key not mentioned in the task's
11-field description. Not a blocker: `UrgencyResult.fromJson` reads
named fields and ignores unknown ones, so this is forward-compatible
without special handling. Documented here so it doesn't look like an
oversight later.

Client contract (from `main.py`'s docstring/comments): history entries
representing assistant turns **must** carry their `type` field
(`{role, content, type}`) — the server's crisis-lock detection
(`_history_has_crisis_lock`) depends on it. Request fields: `message`
(client-side cap at 2000 chars, matching `MAX_MESSAGE_LENGTH` in
`main.py`), `profile`, `worry_level`, `regional_context`,
`conversation_id`, `history`.

## Decisions made during design (with rationale)

1. **Chat rendering: hand-rolled `ListView.builder`, not `flutter_chat_ui`.**
   AGENTS.md names `flutter_chat_ui` as the approved Chat UI package;
   this is a deliberate, owner-approved reversal (see AGENTS.md Tech
   Stack section, dated 2026-07-10) because the mockup's per-turn cards
   (chip rows, assessment card with checklist, teal-tint crisis card)
   go well beyond a generic chat-bubble model, and `flutter_chat_ui`'s
   own theming would need near-total overriding anyway to hit pixel
   fidelity. `flutter_chat_ui` stays in `pubspec.yaml`, unused, with a
   **concrete removal trigger**: once the History and Household screens
   are both built, if neither adopted it either, run `flutter pub
   remove flutter_chat_ui` and delete the now-redundant AGENTS.md line
   about it. Neither of those screens is a chat surface, so this is
   expected to fire, not a hedge — recorded here so it's a scheduled
   cleanup step, not an orphaned "someday" TODO.
2. **`url_launcher` approved** for the crisis card's tap-to-dial hotline
   rows — owner-approved 2026-07-10, logged in AGENTS.md's Tech Stack
   section. Not yet in `pubspec.yaml` as of this spec — adding it
   (`flutter pub add url_launcher`) is an implementation step, not
   something already done.
3. **Models named `Message`/`UrgencyResult`** (not a single
   `assessment_payload.dart`), matching the class names AGENTS.md's
   architecture section already commits to. `Message` has no wire
   `fromJson` (nothing persists it yet — no Firestore this pass) but
   does implement `toHistoryJson()` per the client contract.
   `UrgencyResult` gets the full `fromJson`/`toJson` pair since that's
   the actual wire payload.
4. **Unparseable payloads never crash.** `UrgencyResult.fromJson` maps
   an unrecognized `type` string (or a structurally invalid payload) to
   `ChatTurnType.unparseable`, rendered with the same apologetic
   error-bubble style as a real `"error"` turn.
5. **`next_step` gets its own text line**, not just a CTA-button label.
   The Chat-specific mockup's assessment card omits a distinct
   "What to do next" line (explanation flows straight into the
   self-care checklist), but the flagship Urgency Tag Card spec
   (`Pulse App.dc.html`, and design-system doc §5) shows explanation →
   divider → "What to do next" heading + text → CTA button. Matching
   the compressed Chat-specific layout would silently drop real
   guidance content (`next_step` frequently carries the actual
   actionable instruction, e.g. "may simpleng blood test para malaman
   kung dengue"), so the "What to do next" line is added back in.
6. **Per-tier CTA button copy** (button remains non-functional this
   pass — visual affordance only, TODO for the care-finder feature):
   - `see_doctor_soon`: "Book a GP visit" (from Chat.dc.html)
   - `seek_care_now`: "Find urgent care nearby" (from Chat.dc.html)
   - `monitor_at_home`: **"Okay — I'll check in on this tomorrow."**
     (revised from the flagship mockup's "Set a check-in reminder" —
     that copy implies a manually configured reminder, i.e. the
     medication-reminder engine explicitly deferred past MVP in
     AGENTS.md. The real MVP-adjacent mechanic is Pulse's automatic,
     proactive follow-up 6-24h later — a passive mechanic, not
     something a button "sets." Even a non-functional CTA teaches the
     user what Pulse is, so the copy must match the mechanic that will
     actually ship.)
7. **Monitoring rows render as icon chip + single text line**, no
   separate cadence badge — the mockup's demo data splits `text` +
   `cadence`, but the real `monitoring` field is a flat list of
   already-combined strings with no cadence to split out.
8. **In-card CTA button radius uses the existing `AppRadii.buttonInCard`
   (15.5px)**, not the mockup's literal 16px — within the design doc's
   stated 15-16px range for in-card buttons; a near-duplicate token
   wasn't worth adding for a 0.5px difference.
9. **The stray user-bubble radius in the "continued crisis" mockup
   section** (`24px 24px 10px 24px`, vs. the standard `22/22/8/22`) is
   treated as a one-off mockup inconsistency, not implemented as a
   second user-bubble variant — the task only specifies that
   *Pulse* messages get a softer variant once crisis-locked. Worth a
   quick visual gut-check once the crisis flow renders, but not worth
   modeling on a guess.
10. New design tokens (radii, colors, type styles, one shadow) needed
    for elements not covered by the existing theme are documented in
    `PULSE_DESIGN_SYSTEM.md` §8 ("Chat-screen extensions") — added in
    the same pass as this spec so the design doc doesn't drift behind
    the implementation. See that section for the full list with
    justifications; not duplicated here.

## Architecture

```
lib/features/chat/
  models/
    message.dart              # Message — turn wrapper
    urgency_result.dart        # UrgencyResult — 10(+1)-field payload, fromJson/toJson
  fixtures/
    chat_fixtures.dart         # 6 hand-copied payloads
  repositories/
    chat_repository.dart               # interface
    fixture_chat_repository.dart        # cycles fixtures, zero network
    callable_chat_repository.dart       # cloud_functions, asia-southeast1
  providers/
    chat_provider.dart         # ChatController extends AsyncNotifier<List<Message>>
  screens/
    chat_screen.dart           # replaces the current stub
  widgets/
    chat_bubble.dart
    quick_reply_row.dart
    assessment_card.dart       # intentionally not urgency_tag_card.dart —
                                # AGENTS.md's folder sketch (line 127) is
                                # illustrative, not prescriptive; this name
                                # reflects that it renders for type == "assessment"
                                # specifically, distinct from the crisis/error/question paths
    crisis_card.dart
    error_bubble.dart
    typing_indicator.dart
    chat_input_bar.dart
lib/core/constants/
  crisis_resources.dart        # placeholder {name, number} list, TODO(owner)
```

### Models

`Message`: `id`, `role` (`MessageRole.user | assistant`), `text`,
`payload` (`UrgencyResult?`, assistant turns only), `timestamp`,
`checkedSelfCare` (`Set<int>`, session-only UI state, defaults empty,
mutated via `copyWith` — not part of any wire format).
`toHistoryJson()` emits `{role, content, type}` per the client contract
(`type` omitted/null for user turns).

`UrgencyResult`: `type` (`ChatTurnType` enum: `question, assessment,
crisis, error, unparseable`), `message`, `quickReplies`, `urgency`
(`UrgencyLevel?`, mapped from the wire string via the existing enum in
`app_theme.dart`), `explanation`, `watchFor`, `nextStep`, `selfCare`,
`monitoring`, `encouragement`. `fromJson` never throws on malformed
input — falls back to `ChatTurnType.unparseable` with the raw message
text preserved where possible so the error bubble has something to show.

### Fixtures

Six `UrgencyResult` (or raw JSON map, parsed through `fromJson` for the
totality test) constants: five hand-copied verbatim from
`functions/system_prompt.py`'s `FEW_SHOT_EXAMPLES` (`PROMPT_VERSION
1.5.0` as of this spec), plus one from `main.py`'s degraded-error path.
As of 1.5.0, three of the five examples
(dengue, sore-throat, Taglish caregiver) are 2-turn
question→assessment pairs, not single turns — the exact 6 fixtures are
enumerated explicitly below to remove any ambiguity about which turn
from which example is used (Taglish is not used; it exists in
`system_prompt.py` to demonstrate language mirroring, which isn't
something a static fixture can exercise):

1. **Question, with chips** — dengue example, turn 1 (fever-duration
   question, 4 `quick_replies`)
2. **Assessment, `see_doctor_soon`, all sections populated** — dengue
   example, turn 2
3. **Assessment, `monitor_at_home`, all sections populated** —
   sore-throat example, turn 2 (its own turn 1 question is not used as
   a separate fixture — fixture #1 already covers the question-with-chips
   case)
4. **Assessment, `seek_care_now`, graceful-empty** (`self_care: []`,
   `monitoring: []`) — "Validated escalation" example (single turn)
5. **Crisis** — "Crisis — hopelessness expressed" example (single turn)
6. **Error** — hand-copied from `main.py`'s `_degraded_error_payload`,
   English copy (`FRIENDLY_DEGRADED_ERROR_MESSAGE_EN`)

This set is a deliberate, minimal cover: one question turn, one
assessment per urgency tier, one crisis, one error — enough for every
widget-test case in the Testing Plan below (chip-tap, per-type
rendering, empty-section disappearance) without duplicating coverage.
`system_prompt.py` is uncommitted/mid-edit as of this spec (git status
shows it modified alongside the eval harness) — re-diff the copied
text against `system_prompt.py` at implementation time in case it
moves again before then.

`FixtureChatRepository.send()` cycles through this fixed sequence so
every state is reachable by repeated sending; gated by a
`kDebugMode`-only const in `chat_provider.dart` — no UI toggle this
pass.

### UI, per turn type

- **User/Pulse bubble pair**: user = `primary` fill / white text /
  radius `22 22 8 22` (`AppRadii.chatBubble`/`chatBubbleTail`) / right
  aligned / max-width 78%. Pulse = white surface / radius `22 22 22 8` /
  resting shadow.
- **Question turn**: Pulse bubble + one non-wrapping horizontally
  scrollable chip row below (`chip-border` outline unselected / primary
  fill once sent). Tapping a chip or submitting free text both call
  `chatController.send(text)`.
- **Assessment card**: icon chip (44px, `AppRadii.iconChip`, urgency
  `.solid`) + label (urgency `.text`, Nunito 800/18) + "PULSE GUIDANCE"
  eyebrow (new `cardEyebrow` style) → explanation → divider →
  "What to do next" heading (new `cardSectionHeading` style) +
  `next_step` text → self-care checklist (tap toggles
  `checkedSelfCare`, no persistence) → monitoring rows (icon + text
  line only, see decision 7) → watch-for warning pills (coral tint) →
  full-width CTA button in urgency `.solid` (copy per decision 6) →
  de-emphasized encouragement line. `self_care`/`monitoring`/`watch_for`
  sections each disappear entirely when empty (verified against the
  seek_care_now fixture, which has empty `self_care` and `monitoring`).
- **Crisis card**: `tintTeal` background, `AppRadii.crisisCard` (28),
  new crisis shadow token, no tier icon/machinery, breathing companion
  blob, message text, divider, "Someone to talk to" resource rows from
  `crisis_resources.dart` (tap-to-dial via `url_launcher`). Once any
  assistant turn is `crisis`, `ChatController` sets a
  client-side-mirrored `isCrisisLocked` flag that keeps the UI in
  crisis presentation for the rest of the conversation (mirrors the
  server's own lock; client never bounces back to tier styling).
  Subsequent Pulse messages while locked use the softer all-round-24
  teal-tint bubble variant, no tail (decision 9 on the user-bubble
  radius stray value).
- **Error bubble**: apologetic inline style, warning icon reusing the
  honey urgency palette purely for warm, non-alarming color (not a
  semantic urgency read), tap-to-retry resends the last user message.
- **Typing indicator**: three pulsing dots in `primary`, shown while a
  request is in flight.
- **Input bar**: white pill, radius 22, mic icon present but
  non-functional this pass (TODO), circular send button (42px,
  `primaryDeep`). 2000-char client-side cap with a friendly counter
  shown only near the limit.

### State & wiring

`ChatController extends AsyncNotifier<List<Message>>`
(`chat_provider.dart`). `send(text)` appends the user `Message`, sets a
loading marker, calls `ChatRepository.send(...)`, appends the result
(or a synthetic `error` `Message` on timeout/exception — never a raw
exception, never a crash). `ChatRepository` interface has two impls:
`FixtureChatRepository` (Part 2 behavior) and `CallableChatRepository`
(`cloud_functions`, region `asia-southeast1`, `history` assembled from
prior turns via `toHistoryJson()`; `profile`/`worry_level`/
`regional_context` sent as `null` with TODOs pointing at the profile
feature). No Firestore persistence this pass — conversation lives in
`AsyncNotifier` memory only; TODO references the episode-model plan.

## Testing plan

Widget tests: all 6 fixtures parse via `fromJson` (totality); each
`type` renders its distinct card/bubble; empty-section disappearance
(seek_care_now fixture); chip tap sends its label as the user message;
crisis persistence holds across subsequent turns; error-retry resends
the last user message. Plus `flutter analyze`, `dart format
--set-exit-if-changed .`, `flutter test`, and a manual fixture-mode run
screenshotting all 6 states.

## Explicitly out of scope this pass (tracked, not forgotten)

- Mic button function (visual only, TODO)
- CTA button action / care-finder integration (TODO)
- Real, verified PH crisis hotlines (`crisis_resources.dart` ships with
  placeholder entries, `// TODO(owner)`)
- Any persistence (Firestore episode model is a separate future pass)
- Live-mode (`CallableChatRepository`) manual QA against the deployed
  function — blocked on the free-tier Gemini quota
  ([[gemini_free_tier_quota_limit]] in memory), covered by fixture mode
  instead for this pass

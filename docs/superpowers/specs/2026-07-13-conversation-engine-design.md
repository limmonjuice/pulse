# Pulse Conversation Engine v2 — Design

**Date:** 2026-07-13
**Status:** Approved by owner (this document); implementation plan pending
**Owner decisions incorporated:** state derivation source, pipeline shape,
de-escalation policy, sticky-card UX (see §12)

## 1. Problem

Every user message today is treated as a fresh medical assessment. The
model's only non-question reply vocabulary is `assessment`, and the client
renders every `assessment` payload as a full AssessmentCard. A user who has
already been told "Seek care now" and then asks "is it really necessary?"
gets another full card — same tier, same shape — on every turn. Medically
safe; conversationally a fire alarm.

Root causes, confirmed in code:

- Almost no conversation state exists. The server derives exactly two
  things from history (the crisis lock in `main.py`
  `_history_has_crisis_lock`, and the 1.5.5 conversation-language
  directive in `_conversation_language`); urgency, what has been
  explained, and whether an assessment is active are recomputed from
  nothing each turn.
- The wire contract (`gemini_client.VALID_TYPES`) has no type for a
  conversational reply. `question | assessment | crisis` — answering a
  worry without re-triaging is structurally impossible.
- The client (`chat_screen.dart`) renders every assessment payload as a
  card, unconditionally.

## 2. Goals

1. Medical safety preserved — every existing invariant intact (red-flag
   floor on every message, model never has final say on emergencies,
   crisis mode sticky, no diagnosis, worst-reasonable-explanation bias).
2. Pulse behaves like a clinician mid-consultation: answers the person's
   actual message; does not restart triage on every turn.
3. Identical guidance cards are never regenerated — as a structural
   guarantee, not a prompt aspiration.
4. The active recommendation stays visible (persistent UI), and only
   changes when the clinical picture changes.
5. One Gemini call per message (free-tier quota: ~20 requests/day until
   the production key lands).
6. Works within the known weakness of `gemini-3.1-flash-lite` at
   following soft instructions (see the 1.5.x language-mirroring history):
   no safety- or UI-consistency decision may depend on the model
   classifying anything correctly.

### Non-goals (this pass)

- Server-side conversation persistence (the Firestore "episode model").
  State is derived from client-echoed history; the accepted v1 trust
  limitation (fabricable history, documented in `main.py`) carries over
  unchanged. The episode model later replaces the derivation *input*, not
  the engine.
- Verified post-evaluation outcomes ("the doctor cleared me") as a
  de-escalation source — future version.
- Any change to crisis-mode UX or copy.

## 3. Architecture: five components, one call

Conceptually two planes — the model *proposes*, the server *disposes* —
implemented as five independently testable components composed in
`run_pipeline`:

```
User message
  ↓
STATE BUILDER      derive EpisodeState from history (pure fn — §4)
  ↓                + red-flag check on current message (unchanged floor)
PROMPT BUILDER     static persona/rules (cacheable prefix)
  ↓                + CONVERSATION STATE block (server-derived, dynamic tail)
LLM                ONE Gemini call → proposals: intents,
  ↓                requires_clinical_reassessment, change_type,
  ↓                reassessment_reason, proposed_card_action, findings,
  ↓                + the turn payload itself
SAFETY ENGINE      deterministic gates (§6): crisis → urgency clamp →
  ↓                floor-newly-raised guard → reset gate → card matrix
RESPONSE BUILDER   turn payload + card directive + conversation_state
  ↓
Client
```

Component → module mapping: State Builder is new
(`episode_state.py`); Prompt Builder is `system_prompt.py` (extended);
LLM is `gemini_client.py` (schema extended); Safety Engine is new
(`safety_engine.py` — the gates and card matrix, pure functions);
Response Builder stays in `main.py` alongside request plumbing. Each
component has one input shape and one output shape and is unit-testable
without the others (the exact file boundaries are the implementation
plan's call; the component boundaries are not).

The inversion from today: the model no longer decides that "a card
happens." It writes language; the Safety Engine decides card behavior by
comparing episode state before and after the turn. If flash-lite
misclassifies every intent, a duplicate card is still impossible and a
missed emergency is still caught by the deterministic floor.

## 4. Episode state (derived, never stored)

`derive_episode_state(history, current_message)` — pure function in
`main.py`, same trust model as the existing crisis-lock derivation:

```python
@dataclass
class EpisodeState:
    phase: str                    # "idle" | "assessing" | "guidance" | "crisis"
    current_urgency: str | None   # urgency echoed on the last assessment
                                  # turn since the last reset
    min_safe_urgency: str | None  # highest tier implied by latched rules
    latched_rule_ids: list[str]   # red_flags re-run over EVERY user turn
                                  # since the last reset
    questions_used: int           # assistant "question" turns since the
                                  # last reset marker or last card
    reset_index: int              # index of last accepted reset, -1 if none
    # --- prompt scaffolding only; model-proposed; NEVER gate input ---
    active_findings: list[str]    # latest assessment turn's echoed findings
                                  # ("fever", "cough", "vomiting")
    last_assessment: dict | None  # compact summary composed from the last
                                  # assessment turn's echoed fields:
                                  # {findings, explanation, next_step, urgency}
```

The dataclass has two trust zones, and the comment line is the boundary.
Everything above it derives from the user's own words or deterministic
turn-type counting — gates may consume it. `active_findings` and
`last_assessment` originate from model output (echoed back through
history): they exist so the Prompt Builder can show Gemini a compact
"current picture" instead of forcing it to re-infer one from raw
transcript every request. No gate, clamp, or card decision may ever read
them.

- **Red-flag latch.** `red_flags.check_red_flags` runs over every user
  turn after the last reset marker, plus the current message. Matched rule
  IDs latch for the episode: "vomiting blood" on turn 1 keeps
  `min_safe_urgency = seek_care_now` on turn 10 regardless of anything the
  model or the user says later. The latch is recomputed from the user's
  own words each request — no model output feeds it. (Non-self-harm rules
  currently all imply `seek_care_now`; the field is a tier, not a bool, so
  future rule tiers slot in.)
- **Reset markers.** When a reset is accepted (§6 gate 4), the assistant
  reply carries `assessment_cleared: true`; the client echoes it on that
  history turn; derivation ignores all turns at or before it. Turns after
  a reset re-arm the rules from zero — a reset is a fresh start, not
  immunity.
- **"Already explained" memory** is the transcript itself. The model
  reads full history plus a state block naming the active card and its
  explanation; no derived topic ledger (NLP-hard, redundant).
- **Phase** is derived: `crisis` if crisis-locked; `guidance` if an
  unreset assessment turn exists; `assessing` if the last assistant turn
  is a question; else `idle`.
- **Crisis lock** unchanged and checked first, as today.

### Client history echo (contract change)

`Message.toHistoryJson()` changes in three ways:

- Its assistant-turn type whitelist (currently
  `question | assessment | crisis`) gains `conversation` — without this,
  conversation turns are dropped from history entirely, which would
  silently discard every reset marker (resets ride on conversation
  turns, per §6 gate 4) and starve `phase` derivation. `error` and
  `unparseable` turns stay excluded, as today.
- Assessment turns additionally echo `urgency` (string, feeds
  `current_urgency`), plus `findings`, `explanation`, and `next_step`
  (feed the prompt-scaffolding fields only — see the trust-zone note
  above).
- Reset turns additionally echo `assessment_cleared: true` (bool,
  present-and-true only on accepted resets).

Both sides ship together (no deployed clients). Derivation tolerates the
fields' absence: unknown urgency → `None` → worst case one redundant card,
never a missed floor.

## 5. Wire contract v2

### Model output schema (validated in `gemini_client._validate_payload`)

Existing 11 fields keep their exact semantics. Additions:

| Field | Type | Rules |
|---|---|---|
| `type` | adds `"conversation"` | plain reply turn. `urgency`/`explanation`/`next_step`/`encouragement` null, `watch_for`/`self_care`/`monitoring` empty. `quick_replies` 0–4 allowed (unlike `question`, which requires 2–4). `possibilities_mentioned` keeps its existing semantics (true iff the message names possible conditions — a conversation turn re-explaining an already-mentioned possibility honestly reports true). |
| `intents` | array of enum strings | 1–3 values from the fixed vocabulary (§7) — real messages carry several at once ("I'm scared… do I really need to go?" = `emotional_support` + `asking_about_recommendation`). Required, non-empty. Unknown value or empty array → validation failure → existing corrective-retry path. |
| `requires_clinical_reassessment` | bool | the operational question the engine actually needs answered: should the clinical assessment be revisited because of this message? Distinct from "is this information new" — "I already saw my doctor" is new information that may not require reassessment. Required. |
| `change_type` | enum string | why reassessment is (or isn't) needed: `"new_symptom" \| "resolved_symptom" \| "worsening" \| "new_history" \| "treatment_update" \| "none"`. Single-valued; when one message carries several changes ("the pain moved to my chest but the fever's gone"), the model reports the most clinically escalatory one, precedence: `worsening > new_symptom > new_history > treatment_update > resolved_symptom > none` — worst-reasonable bias applied to classification. Required. |
| `reassessment_reason` | string \| null | must be non-null whenever the proposed urgency differs from the state block's `current_urgency`; null otherwise. NOT schema-validated (`_validate_payload` is stateless and has no `current_urgency`): enforced by the Safety Engine's clamp gate, where a missing reason simply rejects the de-escalation — never a retry. |
| `proposed_card_action` | `"new" \| "update" \| "keep" \| "clear"` | the model's suggestion; never authoritative. Server/model disagreement is logged (eval signal). |
| `findings` | array of short strings | assessment turns only: the FULL current symptom picture as plain nouns ("fever", "cough", "vomiting blood") — a snapshot, not a delta, so the latest assessment's list is always complete on its own. `[]` on all other turn types. Prompt scaffolding for future turns (§4 trust zones); never gate input. |

`crisis` turns: the new fields are still required (`intents` may hold any
values; gates ignore everything on crisis turns).

### Server → client envelope (built in `main.py`)

Alongside the turn payload and existing `metadata`:

```json
"card": { "action": "new | update | keep | clear",
          "reason": "first_assessment | urgency_raised | urgency_lowered |
                     new_red_flag | clinical_change | reset | none" },
"conversation_state": { "urgency": "seek_care_now" | null,
                        "assessment_active": true,
                        "phase": "guidance" }
```

Client rule (the whole client rule): render an AssessmentCard inline only
when `card.action` is `new` or `update`; drive the pinned strip from
`conversation_state`; render `conversation` turns as plain bubbles. No
urgency logic client-side (AGENTS.md AI/Backend rule 7). `card.reason`
exists for structured logs and evals only — no client behavior may key
off it.

Degraded/`error` turns carry `card: {action: "keep"}` and the
`conversation_state` derived from history, so an API failure mid-episode
never blanks the strip (§9).

## 6. Deterministic gates (order matters)

1. **Crisis** — unchanged, outranks everything. `force_crisis` from
   self-harm rules or crisis lock behaves exactly as today. A reset does
   NOT clear crisis mode — only a new conversation does. *(Deliberate
   deviation from the raw spec's "reset clears everything"; flagged for
   mental-health review alongside the existing crisis-flow items.)*
2. **Urgency clamp** — for assessment turns:
   `final_urgency = max(proposed, min_safe_urgency)`. A decrease relative
   to `current_urgency` is accepted only when ALL hold:
   - `requires_clinical_reassessment == true`,
   - `change_type == "resolved_symptom"` — the one change type that is the
     person's own objective report of improvement. `treatment_update`
     ("the doctor already saw me") is deliberately NOT de-escalation-
     eligible this pass: it is second-hand clinical judgment Pulse cannot
     verify, and §12.3 defers verified post-evaluation outcomes to a
     future version. It still updates the card via the matrix below.
   - `reassessment_reason` is non-null (logged verbatim),
   - result ≥ `min_safe_urgency`.
   Otherwise the decrease is rejected and `final = max(current, floor)`.
   Subjective reassurance can never lower urgency at the floor because the
   latch is regex over the user's own words — no model judgment involved.
   Above the floor, de-escalation discipline is prompt- and eval-enforced,
   with the machine-readable justification required before the server
   accepts it (honest limitation: the server cannot verify the *truth* of
   the model's classification; it verifies presence, logs, and evals
   police it — and the `change_type` precedence rule biases mixed
   messages away from de-escalation by construction).
3. **Floor-newly-raised guard** — replaces today's question→assessment
   merge row, generalized: if this message's red flags push
   `min_safe_urgency` above `current_urgency` and the model's turn is not
   an assessment at ≥ that floor, substitute the existing owner-approved
   static seek-care fallback (EN/TL picked by the existing heuristic). A
   conversational message that contains a new emergency ("is it really
   necessary? also my arm just went numb") always yields an updated card,
   whatever the model classified.
4. **Reset gate** — a `clear` is accepted only when the model proposes it
   (`proposed_card_action == "clear"` with `intents` containing
   `testing_system`, `correction`, or `start_new_assessment`) AND
   `red_flags.check_red_flags(current_message)` matches nothing AND the
   episode is not crisis-locked. Accepted resets are logged with rule-id
   context for audit. The reply payload carries `assessment_cleared: true`
   for the history echo. `start_new_assessment` is an accepted trigger by
   owner decision (§12.3: an explicit reset is the one way to clear a
   latch) — it covers the person who deliberately starts over in the same
   thread, distinct from `reporting_new_symptom`, which never resets (the
   old latch keeps protecting a still-open complaint). Runs before the
   card matrix because the matrix's first row consumes its outcome.
5. **Card directive matrix** — pure function of (EpisodeState, final
   turn). Rows are evaluated top-down; the first matching row wins:

   | Situation | `card.action` |
   |---|---|
   | reset accepted (gate 4) | `clear` |
   | no active card + assessment turn | `new` |
   | assessment turn, final urgency ≠ `current_urgency` | `update` |
   | assessment turn, new latched rule IDs at the same tier | `update` (fresh watch-fors) |
   | assessment turn at same tier, `requires_clinical_reassessment` true AND `change_type` ≠ `none` | `update` (reason `clinical_change`) |
   | assessment turn at same tier, otherwise | **demote to `conversation`** (strip card fields, keep message text), `keep` |
   | conversation / question turn | `keep` |

   The `clinical_change` row exists for a genuinely changed picture mid-
   episode at the same tier ("that's sorted — now about this rash"): the
   fresh assessment deserves a fresh card with its own watch-fors even
   though the tier didn't move. This is the one place model proposals
   feed a card decision, and the failure directions are bounded: over-
   reporting shows an occasionally redundant card (today's status quo);
   under-reporting answers in text with a stale card. Neither touches
   urgency. Evals police both directions, and `change_type` gives the
   logs the *why* for free.

   The demotion row makes "never regenerate an identical card" a
   structural guarantee for contentless re-assessments — the fire-alarm
   loop's reassurance turns require no clinical reassessment by
   definition. Demotion rate is logged and becomes an eval metric — a
   climbing rate means the prompt regressed.

Logging additions to `_log_request`: `intents`, `change_type`,
`requires_clinical_reassessment`, `card_action`, `demoted` (bool),
`reset_accepted` (bool), `deescalation_accepted` (bool),
`proposed_vs_final_urgency`. Structured fields only — never message text.

## 7. Prompt restructure (PROMPT_VERSION 2.0.0)

Same cache-conscious skeleton: static prefix byte-identical across
requests; all request-specific content stays in the final section.

- **New static section "TWO KINDS OF TURNS"** placed after HARD_RULES:
  - Assessment turns vs conversation turns, and the golden rule: *respond
    to the person's intent first, their symptoms second — every reply
    begins by answering their actual message.*
  - The do-NOT-reassess list: thanking, greeting, goodbyes, jokes,
    testing, asking why, asking if it's really necessary, fear/anxiety,
    frustration, emotional support, logistics, what-to-expect,
    what-happens-next.
  - Anti-repetition: the guidance card is already on the person's screen;
    never restate its contents unless asked; never explain the same thing
    twice unless asked again.
  - Style variation: ban formulaic openers ("The combination of…", "Based
    on your symptoms…", "The symptoms you've described…"); vary
    acknowledgments naturally.
- **Intent vocabulary** defined compactly with one-line disambiguations
  ("'but sometimes I feel fine' = reassurance_seeking, NOT
  reporting_improvement"). `intents` is an array (1–3): the model reports
  every intent genuinely present — "I'm scared… do I really need to go?"
  is `emotional_support` + `asking_about_recommendation`, and the reply
  should answer both. The prompt also teaches the `change_type`
  precedence rule (most escalatory wins) with one mixed-message example.
  Vocabulary (grouped): reporting_new_symptom,
  reporting_worsening, reporting_improvement, answering_question,
  medication_question, exposure_history / asking_why, reassurance_seeking,
  emotional_support, asking_next_steps, asking_about_recommendation,
  asking_about_causes, clarification / greeting, thanking, joke,
  testing_system, correction, casual_chat, off_topic /
  start_new_assessment, change_language, feedback.
- **Dynamic CONVERSATION STATE block** in the final section (beside the
  1.5.5 language directive, which is untouched), composed from
  EpisodeState:
  - CURRENT FINDINGS: bullet list from `active_findings` — the compact
    current picture, so Gemini doesn't re-infer it from raw transcript
    every request.
  - LAST ASSESSMENT: findings / explanation / recommendation / tier from
    `last_assessment` — the compact "what you already told them"
    reminder (e.g. "Concern: blood in vomit. Why: can indicate serious
    internal problems. Recommendation: seek emergency care today.") that
    replaces re-deriving the last explanation from history.
  - Latch presence, questions used, and the directive: "A guidance card
    showing [tier] is already visible to this person. Do not restate it.
    Propose an assessment only if this message changes the clinical
    picture."
- **Few-shot deck additions** (three multi-turn examples):
  1. English reassurance-seeking after a seek_care_now card ("but I feel
     okay sometimes" → warm `conversation` turn, no card, urgency stands).
  2. Taglish asking_why / anxious turn after an assessment.
  3. Testing reset ("I was just kidding, testing lang") → `conversation`
     turn + `proposed_card_action: clear`.
  Balance EN/TL deliberately — the 1.5.4 lesson is that flash-lite
  template-matches by symptom shape and inherits the template's language.
  Existing examples gain the new schema fields so every example
  demonstrates the full contract.
- PROMPT_VERSION → 2.0.0. Model unchanged, so no MODEL_CHANGELOG entry,
  but a full eval re-baseline is required before deploy (quota-gated).
- New copy follows the existing review flow: Claude drafts EN/Taglish,
  owner read-aloud, clinician review for anything medical.

## 8. State machine

```
                 ┌────────── reset accepted ──────────┐
                 ▼                                     │
   idle ──clinical content──▶ assessing ──card──▶ guidance ──┐
    ▲                            ▲    (question turns,        │ discussion turns
    └── new conversation         │     budget 3)              │ (no card churn)
                                 └── clinical reassessment ◀──┘
                                     required (clamp applies)

   any state ──self-harm signal──▶ crisis   (absorbing; only a new
                                             conversation exits)
   any state ──red-flag floor─────▶ guidance with seek_care_now card
                                             (immediate, no intake)
```

The question budget (3) is per episode segment: it resets on a reset
marker or when a card lands, so a legitimate reassessment after new
symptoms may ask again. (Today's budget is prompt-only; `questions_used`
in the state block makes it visible to the model per-request.)

## 9. UX changes (Flutter)

- **New `UrgencyStrip` widget** pinned below the app bar, visible when
  `conversation_state.assessment_active` and not in crisis mode: tier
  color + label + one-line next step, tap scrolls to the most recent
  inline card. Colors via the `UrgencyColors` theme extension; label
  always paired with color (accessibility rule). Hidden in `idle` and
  crisis (crisis UI owns the screen).
- **`conversation` turns** render as ordinary `ChatBubble`s, with
  optional quick-reply chips.
- Cards render inline only on `card.action` `new`/`update`; `update`
  cards get a small "Updated" eyebrow; the strip animates tier changes.
- **`clear`** hides the strip; the reply bubble carries the
  acknowledgment ("No worries — thanks for letting me know…").
- The strip state is rebuilt from the latest assistant message **that
  carries a `conversation_state`** — survives scrollback, requires no
  client derivation. Client-locally fabricated turns
  (`ChatController._errorMessage()`, produced when the callable itself
  fails: offline, App Check rejection) carry no envelope and are skipped,
  so a transport failure never blanks the strip.
- **Degraded mode with an active card**: error bubble appears; strip and
  existing cards stay. The static seek-care fallback fires only when the
  floor is newly active this turn (current behavior, correctly scoped).

## 10. Edge cases

- **Mixed intent + new emergency** — gate 3 guarantees the card
  regardless of intent classification.
- **Reset then re-describe** — derivation counts only turns after the
  marker; rules re-arm immediately.
- **Reset attempt while red-flagged message** — gate 4 refuses the clear
  on any message that itself matches a rule.
- **Chip taps** — the 1.5.5 language directive is untouched; the state
  block additionally anchors context so a bare chip ("Mild fever") can't
  read as a fresh complaint.
- **Long conversations** — NEW work in this pass (no cap exists today:
  `_build_contents` sends every turn): `run_pipeline` caps the history
  passed to `gemini_client` at the last ~20 turns since the last reset.
  Server-side only — the client keeps sending full history, and both
  latch derivation and `_conversation_language` keep scanning all of it
  (cheap regex, no token cost). Truncation is safe for the model because
  the CONVERSATION STATE block carries the active card's tier and
  explanation forward regardless of which turns fell out of the window.
- **Stale/partial history fields** — unknown urgency derives to `None`;
  worst case one redundant card, never a missed floor.
- **Fabricated history** — unchanged v1 trust posture (documented in
  `main.py`); the episode model closes it later.
- **"Emergency becomes immediate"** (from the raw spec) — no tier exists
  above `seek_care_now`; the case collapses into the new-red-flag
  `update` row (fresh watch-fors/next-step at the same tier).
- **Model proposes `conversation` on a first-contact symptom report** —
  no card exists, no floor fired; the turn passes through as
  conversation. Acceptable (it reads as a clinician acknowledging before
  triaging); the prompt teaches assessment-or-question posture for
  clinical openers, and evals watch it.

## 11. Testing & evals

- **Unit tests** (`test_main.py` + new `test_episode_state.py` and
  `test_safety_engine.py`, mirroring the five-component split): state
  derivation (latch across turns, reset semantics, budget counting,
  urgency/findings/summary echo, trust-zone separation — no gate reads
  scaffolding fields), clamp arithmetic incl. rejected de-escalations and
  the change_type eligibility rule (`resolved_symptom` only), the card
  matrix row-by-row, demotion, reset gate refusals, degraded-with-active-
  card, floor-newly-raised substitution, schema validation for the new
  fields incl. `intents` array bounds and `change_type`/`findings`
  constraints (`test_gemini_client.py`).
- **New eval categories** (harness already supports per-turn checks and
  scripted chip replies):
  - `intent_no_recard` — the fire-alarm transcript verbatim; per-turn
    `card.action == "keep"` + `type == "conversation"` checks.
  - `deescalation_discipline` — subjective reassurance never lowers;
    objective improvement above the floor may.
  - `reset_flow` — testing/kidding clears; re-described symptoms re-arm.
  - `mixed_intent_escalation` — conversational wrapper around a new red
    flag still updates the card.
- **Metrics**: demotion rate, model-vs-server card-action disagreement
  rate, intent distribution — all from structured logs.
- **Rollout**: sequence the plan server/contract-first (episode state +
  gates + schema + prompt, all unit-testable offline), Flutter client
  second (strip, card gating, history echo — both sides ship together on
  the contract change), with the quota-gated full eval sweep as the
  explicit final gate before deploy. Debug builds first (existing
  wiring); re-baseline results in `evals/results/` per the established
  discipline.

## 12. Decision log (owner, 2026-07-13; items 6–10 from owner spec
review, 2026-07-14)

1. **State home:** derived server-side from client-echoed history (no
   Firestore this pass); episode model later swaps the derivation input.
2. **Pipeline:** single LLM call; all structured model outputs are
   proposals; the backend owns clinical state, urgency, latches, and card
   behavior deterministically.
3. **De-escalation:** only with new objective clinical information, never
   below the episode's `min_safe_urgency` from the red-flag latch;
   subjective reassurance never lowers urgency; latch clears only via
   explicit reset; verified post-evaluation outcomes are a future source.
4. **Sticky card UX:** pinned compact strip below the app bar + inline
   cards only on change.
5. **Crisis + reset:** reset does not clear crisis mode (deviation from
   raw spec; flagged for mental-health review).
6. **Proposal fields:** `new_clinical_info` replaced by the operational
   pair `requires_clinical_reassessment` (should the assessment be
   revisited?) + `change_type` (why) — separates card updates,
   reassessment, and de-escalation eligibility, which the single bool
   conflated.
7. **`intents` is an array (1–3)** — real messages carry several intents
   at once; the reply should answer all of them.
8. **Prompt scaffolding state:** `active_findings` + `last_assessment`
   added to EpisodeState — model-proposed via history echo, prompt-only,
   never gate input (the trust-zone boundary in §4).
9. **Five-component pipeline naming:** State Builder → Prompt Builder →
   LLM → Safety Engine → Response Builder; each independently testable.
10. **De-escalation eligibility (calibration call, revisable):** only
    `change_type == "resolved_symptom"` may lower urgency this pass;
    `treatment_update` is second-hand clinical judgment and stays
    card-update-only until verified post-evaluation outcomes exist
    (consistent with decision 3).

## 13. Out-of-scope follow-ups recorded

- Firestore episode model (removes client-trusted history).
- Verified post-evaluation outcomes as a de-escalation source.
- Proactive follow-up touchpoint tied to a reported symptom (existing
  vision doc item; the strip's CTA copy already anticipates it).

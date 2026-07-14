# Pulse Domain Boundary Gate — Design

**Date:** 2026-07-15
**Status:** Approved by owner (this document); implementation plan pending
**Owner decisions incorporated:** `health_education` as a new intent,
generalized intent-policy gate (not a one-off `off_topic` check), permissive
union across multi-intent turns, offline-vs-live test split, explicit
floor/gate-interaction proof (see §7)

## 1. Problem

The conversation engine (v2, merged 2026-07-14) answers any message the
user sends, regardless of subject. Two live examples: "Explain peak input
tokens per minute in Google AI Studio" and "Explain this Firebase Cloud
Functions bug" both get competent, on-topic answers. Technically correct;
off-mission. Pulse exists to help with health, not to be a general-purpose
assistant, and answering non-health requests trains users toward the wrong
mental model of the product, spends output tokens on content with no
product value, and dilutes the healthcare identity of every conversation
it happens in.

The intent vocabulary (`wire_contract.VALID_INTENTS`) already has an
`off_topic` label, grouped under "general conversation" — but nothing
reads it. It carries no behavioral consequence today: the model can
report `off_topic` and still answer the question in full.

## 2. Goals

1. Off-topic requests (programming, software debugging, cloud/AI
   infrastructure, finance, math unrelated to health, legal advice,
   politics, history, entertainment, trivia, unrelated homework or
   productivity questions) get a brief, warm redirect — never the
   substantive answer.
2. Health topics — symptoms, conditions, medications, anatomy,
   physiology, nutrition, exercise, mental wellness, first aid,
   preventive care, vaccinations, lab tests, procedures, and general
   health education — are answered exactly as well as today, including
   cold-open knowledge questions with no ongoing symptom context
   ("What is diabetes?").
3. A message that mixes a genuine health concern with something unrelated
   still gets the health part answered — an off-topic aside never
   suppresses a real symptom report.
4. No new Gemini call. Classification rides in the existing single call's
   structured output.
5. The enforcement — not the classification — is deterministic: the model
   proposes intents, the Safety Engine deterministically guarantees an
   off-topic-only turn can never open or update a guidance card, exactly
   as it already guarantees for crisis-force and the reset gate.
6. The deterministic red-flag floor is untouched and provably cannot be
   suppressed by this gate (see §7's explicit test).

### Non-goals (this pass)

- A deterministic pre-Gemini keyword filter. The out-of-scope topic space
  (programming/finance/law/politics/entertainment/trivia/…) is too open
  for a maintainable keyword list, unlike the bounded, safety-critical
  vocabulary in `red_flags.py`; false positives here (blocking a real
  health question) cost more than the false negatives they'd prevent.
  Classification stays with the model.
- A `{may_assess, may_show_card}` two-key policy dict (see §4 for why
  they're one fact today, not two).
- Live eval coverage for the programming/debugging/finance categories
  (see §7 — a manual spot-check is enough; the formal harness is reserved
  for the two categories with real calibration stakes).

## 3. Architecture: unchanged

Still State Builder → Prompt Builder → Gemini (one call) → Safety Engine
→ Response Builder. No new component, no new stage in `run_pipeline`. The
change is: one new intent (`health_education`), one new deterministic
gate in `safety_engine.apply_gates`, and prompt copy teaching the model
the boundary.

## 4. Vocabulary changes (`wire_contract.py`)

- Add `"health_education"` to `VALID_INTENTS` — for genuine, unprompted
  health-knowledge questions with no ongoing symptom context ("What is
  diabetes?", "How do antibiotics work?"). Distinct from
  `asking_about_causes` / `clarification`, which react to *this*
  conversation's own symptoms.
- Recomment the groupings (documentation only — `VALID_INTENTS` stays a
  flat frozenset):
  - `# medical assessment` — unchanged (6 intents).
  - `# health conversation` — the old "medical conversation" intents +
    `health_education` + the social intents (`greeting`, `thanking`,
    `joke`, `testing_system`, `correction`, `casual_chat`).
  - `# out-of-scope conversation` — `off_topic` alone.
  - `# administrative` — unchanged.
- New: `ASSESSMENT_ELIGIBLE_INTENTS = frozenset({"reporting_new_symptom",
  "reporting_worsening", "reporting_improvement", "answering_question",
  "medication_question", "exposure_history"})` — literally the existing
  "medical assessment" group, now enforced rather than only commented.

**Why not a `{may_assess, may_show_card}` dict:** in this codebase
`may_show_card` is always identical to `may_assess` — card creation
already requires `type == "assessment"` (safety_engine's card matrix,
gate 6 below), so a card-eligibility key would just be a second name for
the same fact `ASSESSMENT_ELIGIBLE_INTENTS` already encodes. The escape
hatch, if that fact ever stops being true (e.g. a future intent that may
show a card without being assessment-eligible): split
`ASSESSMENT_ELIGIBLE_INTENTS` into two sets at that point — one line of
code, not a rewrite.

## 5. The domain gate (`safety_engine.py`)

New gate, inserted immediately after the crisis gate and before the
urgency clamp. Updated gate order: **crisis → domain → clamp →
floor-newly-raised guard → reset gate → card matrix**.

```python
# Gate 2: domain/intent-eligibility gate. A turn can only be "assessment"
# or "question" if at least one reported intent is clinically eligible
# (union across all reported intents — a genuine symptom riding alongside
# an off-topic aside still gets assessed). Anything else is demoted to
# "conversation" via the existing _demote() helper, before any
# urgency/card logic sees it.
if payload.get("type") in ("assessment", "question"):
    intents = set(payload.get("intents") or [])
    if not (intents & ASSESSMENT_ELIGIBLE_INTENTS):
        payload = _demote(payload)
```

Consequences of gate placement:

- Runs **before** the urgency clamp (gate 3), so a demoted payload has
  `type == "conversation"` by the time the clamp checks
  `payload.get("type") == "assessment"` — the clamp naturally no-ops,
  no special-casing needed.
- Runs **before** the floor-newly-raised guard (gate 4). The floor guard
  is keyed on `current_match_rule_ids` — red_flags.py keyword matches on
  the raw message text — never on model-reported intents, so it is
  structurally blind to what the domain gate just did. If a real red flag
  matched this turn, the floor guard replaces whatever payload it sees
  (demoted or not) with the static fallback assessment the moment that
  payload doesn't already meet the floor — and a demoted-to-conversation
  payload never meets the floor (`turn_meets_floor` requires
  `type == "assessment"`). This is why the floor cannot be suppressed by
  the domain gate; §7 pins it with a test rather than leaving it to this
  paragraph.
- Verified against all 9 existing few-shot examples in `system_prompt.py`
  and every scripted payload in `test_golden_conversations.py`: none
  would be demoted by this gate (each assessment/question-type example
  already reports an assessment-eligible intent).

## 6. Prompt changes (`system_prompt.py`, PROMPT_VERSION → 2.1.0)

- **IDENTITY**: one added paragraph stating Pulse's health-only identity
  — a companion for health, symptoms, and knowing when to get care, not a
  general-purpose assistant, even when it technically could answer.
- **HARD_RULES**: new rule 9, "Stay in your lane" — lists the in-scope
  and out-of-scope category examples from the product ask, specifies
  `type: "conversation"`, no card, no urgency, warm one-or-two-sentence
  redirect (DO/DON'T pair in the style of rule 2), and the explicit
  carve-out that a mixed message still gets its health part answered.
- **TWO_KINDS_OF_TURNS**: intent label list gains `health_education`; new
  disambiguation bullet — `casual_chat` (small talk is fine, not
  off-topic) vs. `off_topic` (substantive non-health requests) vs.
  `health_education` (cold-open knowledge question, no ongoing symptom
  context).
- **FEW_SHOT_EXAMPLES**: two new single-turn examples, appended in the
  existing AGENT-DRAFTED PENDING OWNER READ-ALOUD convention (still owed
  your read-aloud, same as the six 2.0.0 examples):
  - Out-of-scope redirect — software debugging request, `type:
    "conversation"`, `intents: ["off_topic"]`, `proposed_card_action:
    "keep"`.
  - Health education — "What is diabetes?", `type: "conversation"`,
    `intents: ["health_education"]`, same null/empty field shape.
- **WHAT_YOU_ARE_NOT**: one added bullet reinforcing the boundary
  ("a general-purpose assistant for non-health topics").

## 7. Schema conformance (confirmed, not assumed)

`type: "conversation"` already fully conforms to the flat schema the same
way `crisis` does — verified against `gemini_client._validate_payload`,
not inferred:

- `urgency` must be `None` (explicit check, raises otherwise).
- `explanation` must be `None` (explicit check).
- `next_step` must be `None` (explicit check).
- `self_care` and `monitoring` must be `[]` (shared branch with
  `question`/`crisis`).
- `encouragement` must be `None` (shared branch).
- `findings` must be `[]` (`if response_type != "assessment" and
  findings: raise`).
- `quick_replies` capped at ≤4 (conversation-specific check; up to 4 is
  allowed — e.g. "Start a new assessment" — unlike `question`'s
  2-4-required rule).

One pre-existing gap noted in passing, not part of this design: `watch_for`
is not validated for emptiness on `question`/`crisis`/`conversation`
types (only `self_care`/`monitoring`/`encouragement`/`findings` are). Every
few-shot example sets it to `[]` by convention and the prompt text says
it should be, but nothing in `_validate_payload` enforces it. Pre-existing,
affects all three non-assessment types uniformly, unrelated to the domain
gate — flagging for awareness, not fixing here.

## 8. Tests

**Offline (`test_golden_conversations.py`) — free, gates every merge:**

The 5 requested product-scenario cases (scripted payloads matching the
*intended* correct model output for each category — these prove pipeline
wiring, not classification accuracy):

1. Programming question → `conversation_payload(intents=("off_topic",))`
   → no card, response passes through unchanged.
2. Software debugging question → same shape.
3. Finance question → same shape.
4. Health education question →
   `conversation_payload(intents=("health_education",))` → no card.
5. Medical symptom question → `assessment_payload(...)` → card created
   normally (regression guard: proves the new gate doesn't touch a
   genuine assessment).

Plus 3 gate-mechanism tests — the correct place for "does the gate demote
correctly," since that's exhaustively, cheaply provable offline forever,
unlike "does Gemini pick the right intents," which is inherently a live,
sampled question (§9):

6. **Wrong-model demotion**: scripted `assessment_payload(urgency,
   intents=("off_topic",))` with no red-flag content in the message →
   response comes back `type == "conversation"`, no card. Proves the gate
   fires on a contrived intent set.
7. **Floor cannot be suppressed by demotion** (the interaction explicitly
   flagged for a test, not an inference): scripted
   `assessment_payload("monitor_at_home", intents=("off_topic",))` for
   `RED_FLAG_OPENER` ("I have chest pain and I'm having trouble
   breathing") → asserts the final response is still `type ==
   "assessment"`, `urgency == "seek_care_now"`, message equals
   `STATIC_SEEK_CARE_FALLBACK_EN`, `card.action == "new"`. Proves gate
   ordering (domain gate runs before, and cannot disarm, the
   floor-newly-raised guard) structurally, not just by argument.
8. **Mixed-intent union still assesses**: scripted `assessment_payload(
   urgency, intents=("reporting_new_symptom", "off_topic"))` → card
   created normally. Proves the permissive-union rule (§5, §2 goal 3).

**Live (`evals/cases.py`) — quota-gated, scoped deliberately narrow:**

Two new `EvalCase` entries only, under a new `domain_boundary` category:
`medical_symptom` and `health_education` — the two categories where
miscalibration has real product weight (wrongly redirecting a real
symptom, or answering a health-knowledge question badly). Programming,
debugging, and finance are deliberately left off the formal harness — a
single manual spot-check conversation covers something this low-stakes;
adding three more low-value cases to a harness that already can't clear
its existing backlog at 20 requests/day would make the backlog worse, not
the coverage better.

**Mechanical, not called out further:** `test_system_prompt.py` and
`test_wire_contract.py` need small structural updates (hard rule count,
intent vocabulary, example count) to match §4 and §6.

## 9. Why classification accuracy can't be proven offline

Worth stating explicitly since it shapes §8's split: "does the
deterministic gate demote correctly given a contrived intent set" is a
mechanism question, answerable exhaustively and permanently with scripted
inputs. "Does Gemini actually produce `intents: ["off_topic"]` for a real
Firebase debugging question" is a model-behavior question — no scripted
test proves it, only a live call against the real model can, and even
then only as a sample. The two `domain_boundary` live cases in §8 exist
for that second question; the offline gate-mechanism tests exist for the
first. Conflating them (testing the gate's own logic with a live call, or
trying to "prove" classification accuracy with a scripted test) would
waste quota on a question scripting already answers, or claim confidence
scripting can't provide.

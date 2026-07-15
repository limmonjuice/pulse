# Domain Boundary Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Pulse decline off-topic (non-health) requests with a warm
redirect instead of answering them, while leaving every health topic —
including cold-open health-education questions — working exactly as
today, with no second Gemini call and no new pipeline stage.

**Architecture:** Domain classification rides in the model's existing
single-call `intents` output (a new `health_education` intent joins the
vocabulary; `off_topic` already exists but currently has no behavioral
consequence). Enforcement is deterministic: a new gate in
`safety_engine.apply_gates` demotes any `"assessment"` turn that reports
no clinically-eligible intent to a plain `"conversation"` turn before any
urgency/card logic runs. Prompt copy (a new hard rule, two new few-shot
examples, updated intent-label text) teaches the model the boundary and
the redirect voice.

**Tech Stack:** Python (Cloud Functions backend), pytest. No Flutter/client
changes — the client already renders `type: "conversation"` generically.

**Spec:** `docs/superpowers/specs/2026-07-15-domain-boundary-gate-design.md`
(read this first — it has the full reasoning; this plan only restates what's
needed to execute it).

---

## Before you start: two things this plan does that the spec doesn't spell out

The spec was written and reviewed at the design level; writing this plan
required tracing the actual gate change against every existing test in
`test_safety_engine.py` line by line. Two things came out of that trace
that are not in the spec, both handled in Task 2 below:

1. **A required test-fixture fix, not optional.** `test_safety_engine.py`'s
   `model()` helper defaults `intents` to `("reassurance_seeking",)` —
   not in the new `ASSESSMENT_ELIGIBLE_INTENTS` set. Five existing tests
   call `model("assessment", ...)` without overriding `intents`, relying
   on that default. Left unchanged, the new gate would silently intercept
   all five *before* they ever reach the code path they're actually
   testing (the clamp, the floor guard, the card matrix's redundant-collapse
   row) — two of them would hard-fail, three would keep passing but for
   the wrong reason (testing the new gate by accident instead of the gate
   they name). Task 2 fixes the default to an eligible intent first, as
   its own commit, before the new gate exists — so it's provably a
   no-op fixture correction, not a behavior change riding along with the
   feature.
2. **A scope decision on `GateResult.demoted` beyond the spec's text.**
   The existing `demoted` field means one specific thing today: gate 6
   collapsed a redundant same-tier reassessment. The new gate produces a
   superficially similar outcome (assessment → conversation) for an
   unrelated reason (off-topic content). Task 2 deliberately does **not**
   reuse `demoted` for the new gate — it keeps that field's existing
   narrow meaning intact rather than conflating two different events
   `main.py`'s logging can no longer tell apart. This is called out
   explicitly with a pinned test rather than left as an implicit choice.

Flagging both up front because they're judgment calls made during planning,
not items the spec review already blessed — worth a second look before
you proceed if anything here seems off.

---

### Task 1: `wire_contract.py` — `health_education` intent + `ASSESSMENT_ELIGIBLE_INTENTS`

**Files:**
- Modify: `functions/wire_contract.py`
- Test: `functions/test_wire_contract.py`

- [ ] **Step 1: Write the failing tests**

Append to `functions/test_wire_contract.py`:

```python
def test_health_education_intent_and_off_topic_grouping():
    assert "health_education" in wc.VALID_INTENTS
    assert "off_topic" in wc.VALID_INTENTS


def test_assessment_eligible_intents_matches_medical_assessment_group():
    # Deliberately the exact "medical assessment" group from VALID_INTENTS
    # — the domain gate (safety_engine.py) enforces this set, so it must
    # never silently drift from the vocabulary's own grouping.
    assert wc.ASSESSMENT_ELIGIBLE_INTENTS == frozenset({
        "reporting_new_symptom", "reporting_worsening", "reporting_improvement",
        "answering_question", "medication_question", "exposure_history",
    })
    assert wc.ASSESSMENT_ELIGIBLE_INTENTS <= wc.VALID_INTENTS
    # health_education and off_topic are deliberately NOT eligible — a
    # turn tagged only with one of these can never open/update a card.
    assert "health_education" not in wc.ASSESSMENT_ELIGIBLE_INTENTS
    assert "off_topic" not in wc.ASSESSMENT_ELIGIBLE_INTENTS
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `functions/`): `pytest test_wire_contract.py -v`
Expected: `test_health_education_intent_and_off_topic_grouping` FAILS
(`"health_education" in wc.VALID_INTENTS` is False); the other new test
fails with `AttributeError: module 'wire_contract' has no attribute
'ASSESSMENT_ELIGIBLE_INTENTS'`.

- [ ] **Step 3: Implement**

In `functions/wire_contract.py`, replace the `VALID_INTENTS` block:

```python
# Spec §7 vocabulary, grouped for readability only — the model sees the
# same grouping in the prompt, the validator sees the flat set.
VALID_INTENTS = frozenset({
    # medical assessment
    "reporting_new_symptom", "reporting_worsening", "reporting_improvement",
    "answering_question", "medication_question", "exposure_history",
    # health conversation
    "asking_why", "reassurance_seeking", "emotional_support",
    "asking_next_steps", "asking_about_recommendation",
    "asking_about_causes", "clarification", "health_education",
    "greeting", "thanking", "joke", "testing_system", "correction",
    "casual_chat",
    # out-of-scope conversation
    "off_topic",
    # administrative
    "start_new_assessment", "change_language", "feedback",
})

# Intents eligible to open or update a clinical assessment (domain
# boundary gate — safety_engine.py, spec 2026-07-15). Exactly the
# "medical assessment" group above; kept as its own frozenset (not just
# the comment) so it's enforced, not merely documented. safety_engine's
# domain gate demotes any "assessment"-type turn whose reported intents
# don't intersect this set — union across all reported intents, so a
# genuine symptom riding alongside e.g. off_topic still gets assessed.
ASSESSMENT_ELIGIBLE_INTENTS = frozenset({
    "reporting_new_symptom", "reporting_worsening", "reporting_improvement",
    "answering_question", "medication_question", "exposure_history",
})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_wire_contract.py -v`
Expected: PASS (all tests, including the two new ones).

- [ ] **Step 5: Commit**

```bash
git add functions/wire_contract.py functions/test_wire_contract.py
git commit -m "feat(wire_contract): add health_education intent and ASSESSMENT_ELIGIBLE_INTENTS"
```

---

### Task 2: `safety_engine.py` — the domain gate

**Files:**
- Modify: `functions/safety_engine.py`
- Test: `functions/test_safety_engine.py`

#### Step A — fixture prep commit (no behavior change yet)

- [ ] **Step 1: Change the test fixture default**

In `functions/test_safety_engine.py`, change the `model()` helper's
default `intents` parameter:

```python
def model(type_="conversation", urgency=None, intents=("reporting_new_symptom",),
          requires=False, change="none", reason=None, card="keep", **over):
```

(was `intents=("reassurance_seeking",)`). No other line in this file
changes in this step.

- [ ] **Step 2: Run the full existing suite to prove this is a no-op today**

Run: `pytest test_safety_engine.py -v`
Expected: PASS — all 13 existing tests green, unchanged behavior (this
step exists to prove the fixture edit alone changes nothing before the
gate exists — the next step is where behavior actually changes).

- [ ] **Step 3: Commit**

```bash
git add functions/test_safety_engine.py
git commit -m "test(safety_engine): use an assessment-eligible default intent in test fixtures

Prep for the domain gate (next commit) — model()'s old default,
reassurance_seeking, isn't assessment-eligible under the new
ASSESSMENT_ELIGIBLE_INTENTS set, and five existing tests rely on the
default without overriding intents. Verified as a pure no-op: full
suite green before the gate exists."
```

#### Step B — the gate itself (TDD)

- [ ] **Step 1: Write the failing tests**

Append to `functions/test_safety_engine.py`:

```python
# --- domain gate (2026-07-15 design) ---

def test_domain_gate_demotes_assessment_without_eligible_intent():
    r = gates(IDLE, model("assessment", "monitor_at_home",
                          intents=("off_topic",), requires=True,
                          change="new_symptom", card="new"))
    assert r.payload["type"] == "conversation"
    assert r.card_action == "keep"
    assert r.payload["urgency"] is None
    # This is a distinct event from gate 6's redundant-collapse — demoted
    # deliberately keeps its original narrow meaning (see plan Task 2
    # preamble), so it stays False here.
    assert r.demoted is False


def test_domain_gate_union_lets_mixed_intents_through():
    r = gates(IDLE, model("assessment", "monitor_at_home",
                          intents=("reporting_new_symptom", "off_topic"),
                          requires=True, change="new_symptom", card="new"))
    assert r.payload["type"] == "assessment"
    assert r.card_action == "new"


def test_domain_gate_leaves_question_type_alone():
    # Scoped to "assessment" only — a "question" turn already can't
    # open/update a card regardless of intents (gate 6 routes every
    # non-assessment type to keep/none), so gating it would add no
    # safety value while risking wrongful demotion of a genuine
    # health_education/medical-conversation clarifying follow-up.
    r = gates(IDLE, model("question", intents=("off_topic",),
                          quick_replies=["A", "B"]))
    assert r.payload["type"] == "question"
    assert r.card_action == "keep"


def test_domain_gate_demotion_clears_stale_quick_replies():
    r = gates(IDLE, model("assessment", "monitor_at_home",
                          intents=("off_topic",), quick_replies=["A", "B"]))
    assert r.payload["quick_replies"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_safety_engine.py -v`
Expected: the four new tests FAIL — `test_domain_gate_demotes_...` and
`test_domain_gate_demotion_clears_stale_quick_replies` fail because
`payload["type"]` is still `"assessment"` (no gate exists yet);
`test_domain_gate_union_lets_mixed_intents_through` and
`test_domain_gate_leaves_question_type_alone` currently pass by
coincidence (nothing demotes them yet either) — note that in the run
output but don't worry about it; step 4 re-confirms all four for the
right reason once the gate exists.

- [ ] **Step 3: Implement the gate**

In `functions/safety_engine.py`:

1. Update the module docstring's gate-order line:

```python
"""
Safety Engine (spec §6): the deterministic gates between the model's
proposals and what the client renders. Pure functions — no I/O, no SDK.
Gate order matters and is load-bearing: crisis → domain → clamp →
floor-newly-raised guard → reset gate → card matrix (the matrix's first
row consumes the reset outcome).

Scaffolding fields (EpisodeState.active_findings / last_assessment) are
deliberately never read here — see the trust-zone note in episode_state.py.
"""
```

2. Update the import line:

```python
from wire_contract import (
    ASSESSMENT_ELIGIBLE_INTENTS, DEESCALATION_CHANGE_TYPES, RESET_INTENTS,
    URGENCY_TIERS, max_urgency, urgency_lt,
)
```

3. Update `_demote()` to also clear `quick_replies`:

```python
def _demote(payload: dict) -> dict:
    return {
        **payload, "type": "conversation", "urgency": None,
        "explanation": None, "watch_for": [], "next_step": None,
        "self_care": [], "monitoring": [], "encouragement": None,
        "findings": [], "quick_replies": [],
    }
```

4. Insert the new gate into `apply_gates`, immediately after
   `final_urgency = state.current_urgency` and before the
   `# Gate 2: urgency clamp` comment — then renumber every gate comment
   from there on (2→3, 3→4, 4→5, 5→6). The full function body after this
   change:

```python
def apply_gates(*, state: EpisodeState, message: str,
                current_match_rule_ids: list[str], force_crisis: bool,
                model_result: dict) -> GateResult:
    # Gate 1: crisis outranks everything (unchanged semantics).
    if force_crisis or model_result.get("type") == "crisis":
        return GateResult(
            payload=_force_crisis(model_result), card_action="keep",
            card_reason="none", final_urgency=None,
        )

    non_self_harm_now = [r for r in current_match_rule_ids if r != "self_harm_risk"]
    floor = state.min_safe_urgency
    if non_self_harm_now:
        floor = max_urgency(floor, "seek_care_now")
    new_rule_ids = [
        r for r in non_self_harm_now if r not in state.latched_rule_ids
    ]

    payload = model_result
    deescalation_accepted = False
    final_urgency = state.current_urgency

    # Gate 2: domain/intent-eligibility gate (domain-boundary-gate design,
    # 2026-07-15). An "assessment" is only valid if at least one reported
    # intent is clinically eligible — union across all reported intents,
    # so a genuine symptom riding alongside e.g. off_topic still gets
    # assessed. Anything else is demoted to "conversation" before any
    # urgency/card logic sees it. Deliberately scoped to "assessment"
    # only, not "question": a "question" turn already can't open/update a
    # card regardless of intents (gate 6 below routes every
    # non-assessment type to keep/none), so gating it would add no
    # safety value while risking wrongful demotion of a genuine
    # health_education or medical-conversation clarifying follow-up.
    if payload.get("type") == "assessment":
        intents = set(payload.get("intents") or [])
        if not (intents & ASSESSMENT_ELIGIBLE_INTENTS):
            payload = _demote(payload)

    # Gate 3: urgency clamp (assessment turns only).
    if payload.get("type") == "assessment":
        proposed = payload.get("urgency")
        final_urgency = max_urgency(proposed, floor) if floor else proposed
        current = state.current_urgency
        if (current in URGENCY_TIERS and proposed in URGENCY_TIERS
                and urgency_lt(proposed, current)):
            eligible = (
                payload.get("requires_clinical_reassessment") is True
                and payload.get("change_type") in DEESCALATION_CHANGE_TYPES
                and isinstance(payload.get("reassessment_reason"), str)
                and (floor is None or not urgency_lt(proposed, floor))
            )
            if eligible:
                deescalation_accepted = True
                final_urgency = proposed
            else:
                final_urgency = max_urgency(current, floor) if floor else current
        payload = {**payload, "urgency": final_urgency}

    # Gate 4: floor newly raised above the active card — the model's turn
    # must be an assessment at >= floor, or the owner-approved static
    # fallback replaces it (generalizes the old question->assessment row).
    if floor is not None:
        floor_above_current = (
            state.current_urgency not in URGENCY_TIERS
            or urgency_lt(state.current_urgency, floor)
        )
        turn_meets_floor = (
            payload.get("type") == "assessment"
            and payload.get("urgency") in URGENCY_TIERS
            and not urgency_lt(payload["urgency"], floor)
        )
        if floor_above_current and not turn_meets_floor:
            payload = fallbacks.static_fallback_assessment(message)
            final_urgency = payload["urgency"]

    # Gate 5: reset gate.
    reset_accepted = (
        payload.get("type") == "conversation"
        and payload.get("proposed_card_action") == "clear"
        and bool(RESET_INTENTS.intersection(payload.get("intents") or []))
        and not current_match_rule_ids
        and state.phase != "crisis"
    )

    # Gate 6: card directive matrix (first matching row wins — spec §6).
    demoted = False
    if reset_accepted:
        action, reason = "clear", "reset"
    elif payload.get("type") != "assessment":
        action, reason = "keep", "none"
    elif state.current_urgency is None:
        action, reason = "new", "first_assessment"
    elif payload["urgency"] != state.current_urgency:
        action = "update"
        reason = ("urgency_lowered"
                  if urgency_lt(payload["urgency"], state.current_urgency)
                  else "urgency_raised")
    elif new_rule_ids:
        action, reason = "update", "new_red_flag"
    elif (payload.get("requires_clinical_reassessment") is True
          and payload.get("change_type") != "none"):
        action, reason = "update", "clinical_change"
    else:
        payload = _demote(payload)
        demoted = True
        action, reason = "keep", "none"
        final_urgency = state.current_urgency

    return GateResult(
        payload=payload, card_action=action, card_reason=reason,
        assessment_cleared=reset_accepted, demoted=demoted,
        reset_accepted=reset_accepted,
        deescalation_accepted=deescalation_accepted,
        final_urgency=final_urgency if payload.get("type") == "assessment"
        else state.current_urgency if not reset_accepted else None,
    )
```

(Everything below `# Gate 3: urgency clamp` is unchanged from the
current file except the renumbered comments — this is the full function
for copy-paste accuracy, not a partial diff.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_safety_engine.py -v`
Expected: PASS — all 17 tests (13 existing + 4 new) green.

- [ ] **Step 5: Commit**

```bash
git add functions/safety_engine.py functions/test_safety_engine.py
git commit -m "feat(safety_engine): add domain/intent-eligibility gate

An 'assessment' turn is only valid if at least one reported intent is
clinically eligible (union across all reported intents). Anything else
demotes to 'conversation' before any urgency/card logic runs. Scoped to
assessment only, not question — a question turn already can't
open/update a card regardless of intents. _demote() now also clears
quick_replies."
```

---

### Task 3: `system_prompt.py` — identity, hard rule 9, two new examples (PROMPT_VERSION → 2.1.0)

**Files:**
- Modify: `functions/system_prompt.py`
- Test: `functions/test_system_prompt.py`

- [ ] **Step 1: Write/update the failing structural tests**

In `functions/test_system_prompt.py`:

Rename and update the version test (was `test_prompt_version_is_2_0_0`):

```python
def test_prompt_version_is_2_1_0():
    assert PROMPT_VERSION == "2.1.0"
```

Update the example count (was `== 9`):

```python
def test_exactly_eleven_examples():
    # 2.1.0 (domain boundary gate) added two: an out-of-scope redirect
    # (software debugging) and a health_education example (diabetes).
    assert len(FEW_SHOT_EXAMPLES) == 11
```

Update the tier-outcomes list to append the two new examples' expected
urgency (both `None` — conversation-type turns):

```python
def test_example_tier_outcomes():
    finals = [_final_payload(example) for example in FEW_SHOT_EXAMPLES]
    assert [payload["urgency"] for payload in finals] == [
        "monitor_at_home",   # mild sore throat — Pulse is not alarmist
        "monitor_at_home",   # Taglish caregiver child-fever case
        "seek_care_now",     # casual tone, red-thread symptoms
        None,                # crisis — no tier, no triage furniture
        "see_doctor_soon",   # English cat-scratch exposure (1.5.1 rebalance)
        "see_doctor_soon",   # English dengue-advisory case (sole dengue example since 1.5.4)
        None,                # EN reassurance — final turn is a conversation turn
        None,                # TL anxious asking-why — final turn is a conversation turn
        None,                # testing reset — final turn is a conversation turn
        None,                # 2.1.0: out-of-scope redirect (software debugging)
        None,                # 2.1.0: health_education (diabetes)
    ]
```

Add a new structural test for hard rule 9 and the WHAT_YOU_ARE_NOT bullet:

```python
def test_hard_rule_9_stays_in_scope():
    prompt = build()
    assert "Stay in your lane" in prompt
    assert '"conversation"' in prompt  # already true generally, kept for locality
    assert "off_topic" in prompt


def test_what_you_are_not_names_the_domain_boundary():
    prompt = build()
    assert "general-purpose assistant for topics unrelated to health" in prompt
```

Add a new test pinning the two new examples' shape:

```python
def test_new_domain_boundary_examples_present_and_correctly_typed():
    titles = " | ".join(e["title"] for e in FEW_SHOT_EXAMPLES)
    assert "debugging" in titles.lower()
    assert "health education" in titles.lower() or "diabetes" in titles.lower()

    debugging = FEW_SHOT_EXAMPLES[9]
    final = _final_payload(debugging)
    assert final["type"] == "conversation"
    assert final["intents"] == ["off_topic"]

    health_ed = FEW_SHOT_EXAMPLES[10]
    final = _final_payload(health_ed)
    assert final["type"] == "conversation"
    assert final["intents"] == ["health_education"]


def test_new_domain_boundary_examples_flagged_for_owner_read_aloud():
    source = (Path(__file__).parent / "system_prompt.py").read_text(encoding="utf-8")
    assert "AGENT-DRAFTED, PENDING OWNER READ-ALOUD (2.1.0)" in source
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_system_prompt.py -v`
Expected: the new/updated tests FAIL (`PROMPT_VERSION` still `"2.0.0"`,
example count still 9, `IndexError` on `FEW_SHOT_EXAMPLES[9]`/`[10]`,
"Stay in your lane" not found, etc.). Some old tests that reference
`FEW_SHOT_EXAMPLES` generically (e.g.
`test_every_example_payload_follows_the_flat_schema`) still pass — that's
expected, they don't pin a count.

- [ ] **Step 3: Implement**

3a. Bump the version:

```python
PROMPT_VERSION = "2.1.0"
```

3b. Append one paragraph to `IDENTITY` (after "Say what you can't do
once, plainly, and move to what you can."):

```python
IDENTITY = """\
## 1. WHO YOU ARE

... (unchanged existing paragraphs) ...

Be honest about your limits without making the conversation about them.
Say what you can't do once, plainly, and move to what you can.

Pulse exists to help with health — symptoms, conditions, medications,
anatomy, physiology, nutrition, exercise, mental wellness, first aid,
preventive care, vaccinations, lab tests, and medical procedures. You
are not a general-purpose assistant: even when you technically could
answer something outside that — programming, finance, legal advice,
trivia — that is not your job here. Hard rule 9 covers exactly how to
handle it when it comes up."""
```

3c. Append hard rule 9 to `HARD_RULES` (after rule 8's closing text):

```python
HARD_RULES = """\
## 2. HARD RULES

... (unchanged rules 1-8) ...

8. LANGUAGE: ... (unchanged) ... switch with them on that turn.
9. Stay in your lane. Pulse exists to help with health — symptoms,
   conditions, medications, anatomy, physiology, nutrition, exercise,
   mental wellness, first aid, preventive care, vaccinations, lab tests,
   and medical procedures. When a message is primarily about something
   else — programming, software debugging, cloud services or AI
   infrastructure, finance or investing, math unrelated to health, legal
   advice, politics, history, entertainment, or other trivia — do not
   answer the substantive request, even when you could. Reply with type
   "conversation": name what you focus on, warmly and in one or two
   sentences, and invite them back to a health question.
   DO: "That's outside what I'm built for, sorry — I focus on health
   questions, symptoms, and figuring out when to see a doctor. If you've
   got a health question though, I'm all ears."
   DON'T: "I cannot answer that." — a cold refusal with no warmth and no
   invitation back.
   A message that mixes a real health concern with something unrelated
   still gets the health part answered in full — never let an unrelated
   aside crowd out or shrink a genuine symptom report."""
```

3d. In `TWO_KINDS_OF_TURNS`, replace the closing "Intent labels" /
"Disambiguation" paragraph:

```python
Intent labels: reporting_new_symptom, reporting_worsening,
reporting_improvement, answering_question, medication_question,
exposure_history | asking_why, reassurance_seeking, emotional_support,
asking_next_steps, asking_about_recommendation, asking_about_causes,
clarification, health_education, greeting, thanking, joke,
testing_system, correction, casual_chat | off_topic |
start_new_assessment, change_language, feedback.
Disambiguation: "but sometimes I feel fine" = reassurance_seeking,
NOT reporting_improvement. A genuine improvement report names a
concrete change ("no fever for two days now"). Casual pleasantries
("how are you", "good morning", a joke about the wait) are casual_chat,
not off_topic — small talk is a normal part of a caring conversation.
off_topic is for substantive requests outside health (debugging code,
stock advice, homework, trivia, politics) — see hard rule 9.
health_education is a genuine, unprompted health-knowledge question with
no ongoing symptom context ("what is diabetes", "how do antibiotics
work") — distinct from asking_about_causes/clarification, which react
to THIS conversation's own symptoms."""
```

3e. Append one bullet to `WHAT_YOU_ARE_NOT`:

```python
WHAT_YOU_ARE_NOT = """\
## 9. WHAT YOU ARE NOT

Hold the edges of your role. You are not:

- a diagnostician — you never conclude what someone has
- a prescriber — no drug choices, no doses
- a replacement for actually seeing a doctor
- an emergency service — when it is urgent, your job is to say "go
  now", clearly and calmly, not to manage the emergency
- a medication-interaction checker
- a reader of lab results or medical images, beyond what a person
  describes seeing with their own eyes
- a general-purpose assistant for topics unrelated to health — coding
  help, financial or legal advice, trivia (hard rule 9)

When asked for one of these, say warmly what a doctor or pharmacist can
do that you can't, and stay with the person on the part that is yours:
how serious this seems, and what to do next."""
```

3f. Append two entries to `FEW_SHOT_EXAMPLES` (after the "Testing reset"
example, i.e. at the end of the list):

```python
    {
        # AGENT-DRAFTED, PENDING OWNER READ-ALOUD (2.1.0): new copy — the
        # deck's demo of hard rule 9. A substantive non-health request
        # gets a warm redirect, never the substantive answer, never a
        # card.
        "title": "Out-of-scope redirect — software debugging request",
        "setting": "Profile: adult. No regional advisories.",
        "turns": [
            {
                "user": (
                    "Can you help me debug this Firebase Cloud Function? "
                    "It keeps throwing a 500 error and I can't figure "
                    "out why."
                ),
                "assistant": {
                    "type": "conversation",
                    "message": (
                        "That's outside what I'm built for, sorry — I "
                        "focus on health questions, symptoms, and "
                        "figuring out when to see a doctor. I can't "
                        "really help with debugging code. If you've got "
                        "a health question though, I'm all ears."
                    ),
                    "quick_replies": [],
                    "urgency": None,
                    "explanation": None,
                    "watch_for": [],
                    "next_step": None,
                    "possibilities_mentioned": False,
                    "self_care": [],
                    "monitoring": [],
                    "encouragement": None,
                    "intents": ["off_topic"],
                    "requires_clinical_reassessment": False,
                    "change_type": "none",
                    "reassessment_reason": None,
                    "proposed_card_action": "keep",
                    "findings": [],
                },
            },
        ],
    },
    {
        # AGENT-DRAFTED, PENDING OWNER READ-ALOUD (2.1.0): new copy — the
        # deck's demo that health_education questions get answered in
        # full, exactly as before, with no card and no assessment
        # machinery.
        "title": "Health education — cold-open knowledge question, no assessment needed",
        "setting": "Profile: adult. No regional advisories.",
        "turns": [
            {
                "user": "What is diabetes, actually?",
                "assistant": {
                    "type": "conversation",
                    "message": (
                        "Diabetes is when the body has trouble keeping "
                        "blood sugar in a healthy range — either because "
                        "it doesn't make enough insulin, or because it "
                        "doesn't use insulin well. Over time, blood "
                        "sugar that stays high can affect the eyes, "
                        "kidneys, nerves, and heart, which is why it's "
                        "usually managed closely with a doctor.\nIs this "
                        "something you're wondering about for yourself, "
                        "or just curious?"
                    ),
                    "quick_replies": [],
                    "urgency": None,
                    "explanation": None,
                    "watch_for": [],
                    "next_step": None,
                    "possibilities_mentioned": False,
                    "self_care": [],
                    "monitoring": [],
                    "encouragement": None,
                    "intents": ["health_education"],
                    "requires_clinical_reassessment": False,
                    "change_type": "none",
                    "reassessment_reason": None,
                    "proposed_card_action": "keep",
                    "findings": [],
                },
            },
        ],
    },
]
```

(The closing `]` above is the existing `FEW_SHOT_EXAMPLES` list's own
closing bracket — these two dicts are new list entries appended before
it, not a new list.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_system_prompt.py -v`
Expected: PASS — every test green, including the pre-existing generic
ones (`test_every_example_payload_follows_the_flat_schema`,
`test_every_example_payload_passes_the_wire_validator`,
`test_every_example_turn_carries_the_v2_fields`,
`test_two_kinds_of_turns_teaches_golden_rule_and_every_intent` — this
last one now also requires `"health_education"` to appear in the built
prompt, satisfied by step 3d).

- [ ] **Step 5: Commit**

```bash
git add functions/system_prompt.py functions/test_system_prompt.py
git commit -m "feat(system_prompt): teach the health-only domain boundary (PROMPT_VERSION 2.1.0)

Adds hard rule 9 (stay in your lane), an IDENTITY paragraph, a
WHAT_YOU_ARE_NOT bullet, updated intent-label/disambiguation text for
health_education, and two new few-shot examples (software-debugging
redirect, health-education diabetes answer) — both AGENT-DRAFTED,
PENDING OWNER READ-ALOUD per the existing convention."
```

---

### Task 4: `test_golden_conversations.py` — pipeline-level coverage

**Files:**
- Test: `functions/test_golden_conversations.py`

Depends on Tasks 1 and 2 (the gate must exist). Does not depend on Task 3
— these tests use scripted payloads and never touch the real prompt.

- [ ] **Step 1: Write the tests**

Append to `functions/test_golden_conversations.py`:

```python
# ---------------------------------------------------------------------------
# Domain boundary gate (2026-07-15 design) — off-topic requests get a
# warm redirect, never a card; genuine health content is unaffected.
# ---------------------------------------------------------------------------

def test_domain_boundary_programming_question_no_card(monkeypatch):
    convo = Conversation(monkeypatch)
    r = convo.turn(
        "Can you explain peak input tokens per minute in Google AI Studio?",
        conversation_payload(
            message=(
                "That's outside what I'm built for, sorry — I focus on "
                "health questions, symptoms, and figuring out when to "
                "see a doctor. If you've got a health question though, "
                "I'm all ears."
            ),
            intents=("off_topic",),
        ),
    )
    assert r["type"] == "conversation"
    assert r["card"]["action"] == "keep"
    assert r["conversation_state"] == {
        "urgency": None, "assessment_active": False, "phase": "idle",
    }


def test_domain_boundary_debugging_question_no_card(monkeypatch):
    convo = Conversation(monkeypatch)
    r = convo.turn(
        "Can you help me debug this Firebase Cloud Function? It keeps "
        "throwing a 500 error.",
        conversation_payload(
            message=(
                "That's outside what I'm built for, sorry — I focus on "
                "health questions, symptoms, and figuring out when to "
                "see a doctor. I can't really help with debugging code."
            ),
            intents=("off_topic",),
        ),
    )
    assert r["type"] == "conversation"
    assert r["card"]["action"] == "keep"


def test_domain_boundary_finance_question_no_card(monkeypatch):
    convo = Conversation(monkeypatch)
    r = convo.turn(
        "Should I invest in index funds or individual stocks right now?",
        conversation_payload(
            message=(
                "That's outside what I focus on — I'm here for health "
                "questions and knowing when to get care. Happy to help "
                "if something's going on health-wise."
            ),
            intents=("off_topic",),
        ),
    )
    assert r["type"] == "conversation"
    assert r["card"]["action"] == "keep"


def test_domain_boundary_health_education_no_card(monkeypatch):
    convo = Conversation(monkeypatch)
    r = convo.turn(
        "How do antibiotics actually work?",
        conversation_payload(
            message=(
                "Antibiotics kill or stop the growth of bacteria — they "
                "don't do anything against viruses, which is why a "
                "doctor won't prescribe them for something like a cold."
            ),
            intents=("health_education",),
        ),
    )
    assert r["type"] == "conversation"
    assert r["card"]["action"] == "keep"
    assert r["conversation_state"] == {
        "urgency": None, "assessment_active": False, "phase": "idle",
    }


def test_domain_boundary_medical_symptom_still_assesses(monkeypatch):
    # Regression guard: the new gate must not touch a genuine assessment.
    convo = Conversation(monkeypatch)
    r = convo.turn(
        "I've had a fever and a bad cough for three days now.",
        assessment_payload("see_doctor_soon", findings=["fever 3 days", "cough"]),
    )
    assert r["type"] == "assessment"
    assert r["urgency"] == "see_doctor_soon"
    assert r["card"]["action"] == "new"


def test_g7_domain_gate_demotes_wrong_model_off_topic_assessment(monkeypatch):
    # Contrived: the model incorrectly assesses an off-topic-only
    # message. The domain gate must demote it before it ever reaches the
    # card matrix.
    convo = Conversation(monkeypatch)
    r = convo.turn(
        "Can you help me debug this Python script?",
        assessment_payload("monitor_at_home", intents=("off_topic",)),
    )
    assert r["type"] == "conversation"
    assert r["card"]["action"] == "keep"
    assert r["urgency"] is None


def test_g8_domain_gate_cannot_suppress_the_floor(monkeypatch):
    # The domain gate demotes an assessment turn lacking any
    # assessment-eligible intent to "conversation" BEFORE the floor
    # guard runs (gate order: crisis -> domain -> clamp -> floor ->
    # reset -> card matrix). Proves demotion can never suppress a
    # genuine red-flag floor: the floor guard doesn't care what type the
    # payload already carries, only whether it already meets the floor,
    # so a demoted-to-conversation payload always fails
    # "turn_meets_floor" and gets replaced by the static fallback
    # regardless.
    convo = Conversation(monkeypatch)
    r = convo.turn(
        RED_FLAG_OPENER,
        assessment_payload("monitor_at_home", intents=("off_topic",)),
    )
    assert r["type"] == "assessment"
    assert r["urgency"] == "seek_care_now"
    assert r["message"] == main.STATIC_SEEK_CARE_FALLBACK_EN
    assert r["card"]["action"] == "new"


def test_g9_domain_gate_mixed_intent_union_still_assesses(monkeypatch):
    convo = Conversation(monkeypatch)
    r = convo.turn(
        "My chest has been aching and also can you help with my code?",
        assessment_payload(
            "monitor_at_home",
            intents=("reporting_new_symptom", "off_topic"),
        ),
    )
    assert r["type"] == "assessment"
    assert r["card"]["action"] == "new"


def test_domain_gate_question_type_passes_through_untouched(monkeypatch):
    # Scoped to "assessment" only — a "question" turn already can't
    # open/update a card regardless of intents, so the gate deliberately
    # leaves it alone rather than risking a wrongful demotion of a
    # genuine health_education/medical-conversation clarifying
    # follow-up.
    convo = Conversation(monkeypatch)
    r = convo.turn(
        "How do antibiotics work?",
        {
            "type": "question",
            "message": "Are you asking generally, or about a specific type?",
            "quick_replies": ["Generally", "A specific type"],
            "urgency": None, "explanation": None, "watch_for": [],
            "next_step": None, "possibilities_mentioned": False,
            "self_care": [], "monitoring": [], "encouragement": None,
            "intents": ["off_topic"],
            "requires_clinical_reassessment": False, "change_type": "none",
            "reassessment_reason": None, "proposed_card_action": "keep",
            "findings": [],
        },
    )
    assert r["type"] == "question"
    assert r["card"]["action"] == "keep"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_golden_conversations.py -v`
Expected: with Tasks 1-2 already done, these should mostly PASS already
(the gate exists) — this task is really about locking in coverage, not
discovering new failures. If you're executing tasks strictly in order,
skip to step 4. If Task 2 hasn't landed yet, `test_g7`/`test_g8`/`test_g9`
FAIL (payload stays type "assessment" with no gate to demote it).

- [ ] **Step 3: N/A** (implementation already landed in Task 2 — this
  task only adds coverage of it at the pipeline level)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_golden_conversations.py -v`
Expected: PASS — all tests (7 pre-existing + 9 new) green.

- [ ] **Step 5: Commit**

```bash
git add functions/test_golden_conversations.py
git commit -m "test(golden): add domain-boundary pipeline coverage

5 product-scenario cases (programming/debugging/finance redirects,
health_education, medical-symptom regression guard) + 4 gate-mechanism
cases (wrong-model demotion, floor cannot be suppressed by demotion,
mixed-intent union, question-type passthrough)."
```

---

### Task 5: `evals/cases.py` — two live `domain_boundary` cases

**Files:**
- Modify: `functions/evals/cases.py`

Not test-driven in the usual sense — these run against the real Gemini
API and are quota-gated (see `LAUNCH_BLOCKERS.md`'s existing eval-sweep
backlog). This task adds the case definitions only; running them is
separately gated on quota, same as the rest of the eval backlog.

- [ ] **Step 1: Add the two cases**

Append to the `CASES +=` block at the end of `functions/evals/cases.py`
(after the `mixed_intent_escalation` category):

```python
    # -------------------------------------------------------------------
    # 12. domain_boundary (domain-boundary-gate design, 2026-07-15) —
    # only the two categories with real calibration stakes get live
    # coverage (a wrongly redirected symptom, or a badly answered
    # health-knowledge question); programming/debugging/finance are
    # deliberately left off the formal harness (design doc §8/§9) — a
    # single manual spot-check covers something this low-stakes, and
    # this harness already can't clear its existing backlog at 20
    # requests/day.
    # -------------------------------------------------------------------
    EvalCase(
        id="domain_boundary_medical_symptom_still_assesses",
        category="domain_boundary",
        message=(
            "My stomach has been hurting badly since this morning and "
            "I've thrown up twice."
        ),
        scripted_replies=["Since this morning", "Yes, twice so far"],
        checks=[("check_type", "assessment")],
        notes=(
            "Proves the domain-boundary prompt additions (hard rule 9, "
            "health_education intent, the two new few-shot examples) "
            "don't suppress a genuine symptom report — the case must "
            "still reach a real assessment, not get redirected as "
            "off-topic."
        ),
    ),
    EvalCase(
        id="domain_boundary_health_education_antibiotics",
        category="domain_boundary",
        message="How do antibiotics work?",
        checks=[("check_type", "conversation")],
        notes=(
            "check_type only rules out this being mistaken for a "
            "symptom assessment — it can't distinguish a substantive "
            "answer from a wrongful off-topic redirect (both are "
            "type=conversation). FLAGGED FOR MANUAL READ: a human must "
            "read the actual reply to confirm it answers the question "
            "rather than redirecting."
        ),
    ),
]
```

- [ ] **Step 2: Sanity-check the module still imports cleanly**

Run (from `functions/`): `python -c "import evals.cases; print(len(evals.cases.CASES))"`
Expected: prints a number (previous total + 2), no traceback.

- [ ] **Step 3: Commit**

```bash
git add functions/evals/cases.py
git commit -m "test(evals): add domain_boundary live cases (medical_symptom, health_education)

Authored, not yet run — joins the existing quota-gated backlog per
LAUNCH_BLOCKERS.md. Programming/debugging/finance deliberately excluded
from the formal harness (design doc §8/§9)."
```

---

### Task 6: Documentation touch-up — `LAUNCH_BLOCKERS.md`

**Files:**
- Modify: `LAUNCH_BLOCKERS.md`

- [ ] **Step 1: Update the existing eval-sweep entry**

Find the bullet starting `- [ ] Prompt 2.0.0 (conversation engine v2)
full eval sweep...` and replace it with:

```markdown
- [ ] Prompt 2.1.0 (conversation engine v2 + domain boundary gate) full
      eval sweep + re-baseline pending quota — THE deploy gate for both
      branches. The offline goldens (test_golden_conversations.py) gate
      merges; the live twins (evals categories intent_no_recard,
      deescalation_discipline, reset_flow, mixed_intent_escalation —
      authored 2026-07-14, never run — plus domain_boundary, authored
      2026-07-15, never run) plus a full re-run of every pre-existing
      category must be green on the deployed model before deploy. New
      prompt copy (three 2.0.0 few-shot examples + the TWO KINDS OF
      TURNS section, plus 2.1.0's hard rule 9 and two new few-shot
      examples — software-debugging redirect, health-education diabetes
      answer) is AGENT-DRAFTED, PENDING OWNER READ-ALOUD.
```

- [ ] **Step 2: Commit**

```bash
git add LAUNCH_BLOCKERS.md
git commit -m "docs: update eval-sweep blocker for prompt 2.1.0"
```

---

### Task 7: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire functions/ pytest suite**

Run (from `functions/`): `pytest -v`
Expected: PASS — every test in the suite green, no regressions anywhere
outside the files this plan touched.

- [ ] **Step 2: Spot-check the assembled prompt renders cleanly**

Run (from `functions/`): `python system_prompt.py > /dev/null` (or on
Windows: `python system_prompt.py | Out-Null`)
Expected: exits cleanly, stderr prints the char/token estimate line, no
traceback. (This is the module's existing `__main__` block — confirms
`build_system_prompt()` doesn't crash with the new content.)

- [ ] **Step 3: No commit needed** — this task is verification only. If
  anything fails here, stop and fix it before considering the plan done;
  do not commit around a failure.

---

## What's intentionally NOT in this plan

- **No `main.py`, `gemini_client.py`, or `episode_state.py` changes.**
  Traced during planning: none of the three reference `intents` in a way
  the domain gate affects — `main.py`'s logging/state-summary functions
  operate on `type`/`card_action` generically, `gemini_client.py`'s
  validator already treats `VALID_INTENTS` as an opaque set, and
  `episode_state.py` only ever sees the gate's already-final output via
  client-echoed history. Confirms the design doc's "Architecture:
  unchanged" claim held up under a full trace, not just at the design
  level.
- **No Flutter/client changes.** The client already renders `type:
  "conversation"` generically; nothing about an off-topic redirect is
  visually distinct from any other conversational reply.
- **Running the new live eval cases.** Blocked on the same quota
  constraint as the rest of the backlog (Task 6's `LAUNCH_BLOCKERS.md`
  update tracks this).
- **The owner read-aloud of the two new few-shot examples.** Not an
  implementation step — tracked via `LAUNCH_BLOCKERS.md` (Task 6),
  consistent with every prior AGENT-DRAFTED example in this file.

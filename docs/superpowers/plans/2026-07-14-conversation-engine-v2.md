# Conversation Engine v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the conversation engine v2 spec (`docs/superpowers/specs/2026-07-13-conversation-engine-design.md`): intent-aware conversation turns, server-derived episode state with a red-flag latch, deterministic card directives, prompt 2.0.0, and a pinned urgency strip — killing the fire-alarm UX while preserving every safety invariant.

**Architecture:** Five components composed in `run_pipeline`: State Builder (`episode_state.py`, new) → Prompt Builder (`system_prompt.py`, extended) → LLM (`gemini_client.py`, schema v2) → Safety Engine (`safety_engine.py`, new — gates + card matrix as pure functions) → Response Builder (`main.py`). The model proposes (`intents`, `requires_clinical_reassessment`, `change_type`, `proposed_card_action`, `findings`); the server disposes. Flutter renders `conversation` turns as bubbles, gates AssessmentCards on `card.action`, and pins an `UrgencyStrip` driven by `conversation_state`.

**Tech Stack:** Python 3.13 Cloud Functions (pytest, monkeypatch — no live Gemini in tests), Flutter/Dart (flutter_riverpod, flutter_test).

**Sequencing rule (from spec §11):** server/contract first (Tasks 1–9, all offline-testable), Flutter second (Tasks 10–13), eval scenarios last (Task 14). The offline golden conversations (Task 9) gate every later change; the live eval sweep is the deploy gate and is quota-blocked — it is a *recorded follow-up*, not part of this plan's definition of done.

**Read before starting:** the spec (all of it), `functions/main.py` module docstring, `AGENTS.md` "AI / Backend Rules". Safety invariants you must not break: red flags run on every request; the model never has final say on emergencies; crisis mode is sticky; no urgency logic client-side.

---

## File structure

| File | Status | Responsibility |
|---|---|---|
| `functions/wire_contract.py` | create | Shared vocabulary: urgency tiers + ordering, intents, change types, card actions. Stdlib-only (importable by `system_prompt.py`, which must stay pure). |
| `functions/fallbacks.py` | create | Owner-approved fallback copy + payload builders + EN/TL heuristic, moved verbatim from `main.py` so both `main.py` (degraded mode) and `safety_engine.py` (floor substitution) can import them without a cycle. |
| `functions/episode_state.py` | create | State Builder: `EpisodeState` dataclass + `derive_episode_state(history, profile)` — pure derivation, two trust zones. |
| `functions/safety_engine.py` | create | Safety Engine: `apply_gates(...)` — crisis force, urgency clamp, floor-newly-raised substitution, reset gate, card directive matrix. Pure functions. |
| `functions/gemini_client.py` | modify | Schema v2 validation (`conversation` type + 6 new fields). |
| `functions/system_prompt.py` | modify | PROMPT_VERSION 2.0.0: TWO KINDS OF TURNS section, intent vocabulary, extended OUTPUT_FORMAT, CONVERSATION STATE block renderer, few-shot deck updates. |
| `functions/main.py` | modify | Response Builder + plumbing: wire the five components, history cap, envelope (`card`, `conversation_state`, `assessment_cleared`), logging. |
| `functions/test_wire_contract.py` | create | Tier ordering, vocabulary integrity. |
| `functions/test_episode_state.py` | create | Derivation: latch, reset, budget, echo fields, trust zones. |
| `functions/test_safety_engine.py` | create | Gates + matrix row-by-row. |
| `functions/test_gemini_client.py` | modify | Schema v2 validation cases. |
| `functions/test_system_prompt.py` | modify | 2.0.0 sections, state block, example contract checks. |
| `functions/test_main.py` | modify | Envelope, history cap, logging, degraded modes. |
| `functions/test_golden_conversations.py` | create | The six offline goldens (spec §11) — merge gate. |
| `lib/features/chat/models/urgency_result.dart` | modify | `ChatTurnType.conversation`, `CardAction`, `ConversationState`, new payload fields. |
| `lib/features/chat/models/message.dart` | modify | History echo v2 (`conversation` whitelisted, `urgency`/`findings`/`explanation`/`next_step`/`assessment_cleared`). |
| `lib/features/chat/widgets/urgency_strip.dart` | create | Pinned strip widget. |
| `lib/features/chat/providers/chat_provider.dart` | modify | `activeConversationStateProvider` (latest non-null envelope walk-back). |
| `lib/features/chat/screens/chat_screen.dart` | modify | Strip placement, conversation-turn rendering, card gating on `card.action`. |
| `test/features/chat/models/*_test.dart`, `test/features/chat/widgets/urgency_strip_test.dart` | create | Dart-side contract + strip visibility tests. |
| `functions/evals/cases.py`, `functions/evals/checkers.py` | modify | Live golden scenarios + new checkers (authored now, run on quota). |

Run all Python commands from `functions/` (`pytest <file> -v`). Run Flutter commands from repo root. Before finishing: `flutter analyze`, `dart format --set-exit-if-changed .`, `flutter test`, `pytest` (all, from `functions/`).

---

### Task 1: `wire_contract.py` — shared vocabulary

**Files:** Create `functions/wire_contract.py`, `functions/test_wire_contract.py`

- [ ] **Step 1: Write the failing tests**

```python
# functions/test_wire_contract.py
"""Tests for wire_contract.py — the shared engine vocabulary."""
import wire_contract as wc


def test_tier_ordering():
    assert wc.max_urgency("monitor_at_home", "seek_care_now") == "seek_care_now"
    assert wc.max_urgency("seek_care_now", "monitor_at_home") == "seek_care_now"
    assert wc.max_urgency("see_doctor_soon", "see_doctor_soon") == "see_doctor_soon"


def test_max_urgency_unrecognized_first_arg_yields_second():
    assert wc.max_urgency(None, "see_doctor_soon") == "see_doctor_soon"
    assert wc.max_urgency("bogus", "monitor_at_home") == "monitor_at_home"


def test_urgency_lt():
    assert wc.urgency_lt("monitor_at_home", "see_doctor_soon")
    assert not wc.urgency_lt("seek_care_now", "see_doctor_soon")
    assert not wc.urgency_lt("see_doctor_soon", "see_doctor_soon")


def test_vocabularies_are_frozen_and_populated():
    assert "reassurance_seeking" in wc.VALID_INTENTS
    assert "start_new_assessment" in wc.VALID_INTENTS
    assert wc.VALID_CHANGE_TYPES == frozenset({
        "new_symptom", "resolved_symptom", "worsening",
        "new_history", "treatment_update", "none",
    })
    assert wc.VALID_CARD_ACTIONS == frozenset({"new", "update", "keep", "clear"})
    assert wc.RESET_INTENTS <= wc.VALID_INTENTS
```

- [ ] **Step 2: Run to verify failure** — `pytest test_wire_contract.py -v` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# functions/wire_contract.py
"""
Shared vocabulary for the conversation engine v2 wire contract
(spec: docs/superpowers/specs/2026-07-13-conversation-engine-design.md §5).

Stdlib-only ON PURPOSE: system_prompt.py (pure by charter) and
gemini_client.py both import this, so the intent/change-type vocabulary
has exactly one home — prompt text and schema validation can never
drift apart.
"""

from __future__ import annotations

URGENCY_TIERS = ("monitor_at_home", "see_doctor_soon", "seek_care_now")


def max_urgency(a: str | None, b: str) -> str:
    """Higher-tier-wins; `b` wins on a tie or when `a` isn't a tier.
    (Moved from main.py's _max_urgency — same semantics.)"""
    if a not in URGENCY_TIERS:
        return b
    return a if URGENCY_TIERS.index(a) >= URGENCY_TIERS.index(b) else b


def urgency_lt(a: str, b: str) -> bool:
    """True when `a` is a strictly lower tier than `b` (both must be tiers)."""
    return URGENCY_TIERS.index(a) < URGENCY_TIERS.index(b)


# Spec §7 vocabulary, grouped for readability only — the model sees the
# same grouping in the prompt, the validator sees the flat set.
VALID_INTENTS = frozenset({
    # medical assessment
    "reporting_new_symptom", "reporting_worsening", "reporting_improvement",
    "answering_question", "medication_question", "exposure_history",
    # medical conversation
    "asking_why", "reassurance_seeking", "emotional_support",
    "asking_next_steps", "asking_about_recommendation",
    "asking_about_causes", "clarification",
    # general conversation
    "greeting", "thanking", "joke", "testing_system", "correction",
    "casual_chat", "off_topic",
    # administrative
    "start_new_assessment", "change_language", "feedback",
})

VALID_CHANGE_TYPES = frozenset({
    "new_symptom", "resolved_symptom", "worsening",
    "new_history", "treatment_update", "none",
})

VALID_CARD_ACTIONS = frozenset({"new", "update", "keep", "clear"})

# The intents that may open the reset gate (spec §6 gate 4).
RESET_INTENTS = frozenset({"testing_system", "correction", "start_new_assessment"})

# The one change type eligible to lower urgency (spec §12 decision 10).
DEESCALATION_CHANGE_TYPES = frozenset({"resolved_symptom"})
```

- [ ] **Step 4: Run to verify pass** — `pytest test_wire_contract.py -v` → all PASS.
- [ ] **Step 5: Commit** — `git add functions/wire_contract.py functions/test_wire_contract.py && git commit -m "feat(functions): wire_contract module - shared v2 engine vocabulary"`

---

### Task 2: `fallbacks.py` — extract fallback copy from `main.py`

Pure move, no behavior change. `safety_engine.py` (Task 4) needs the static seek-care fallback; importing it from `main.py` would create a cycle.

**Files:** Create `functions/fallbacks.py`; Modify `functions/main.py`

- [ ] **Step 1:** Create `functions/fallbacks.py` and MOVE (cut, don't copy) from `main.py`, verbatim including comments: `STATIC_SEEK_CARE_FALLBACK_EN/TL`, `FRIENDLY_DEGRADED_ERROR_MESSAGE_EN/TL`, `CRISIS_DEGRADED_FALLBACK_EN/TL`, `_TAGALOG_MARKER_WORDS`, `_WORD_RE`, `_message_signals_tagalog`, `_pick_fallback_copy`, `_static_fallback_assessment`, `_crisis_fallback_payload`, `_degraded_error_payload`. Rename the three payload builders public (`static_fallback_assessment`, `crisis_fallback_payload`, `degraded_error_payload`). Module docstring: "Owner-approved degraded-mode/floor fallback copy and payload builders. Moved from main.py 2026-07-14 so safety_engine.py can import them without a circular import. Copy is owner-approved (2026-07-08) — do not edit wording here without the owner."
- [ ] **Step 2:** In `main.py`: `import fallbacks`, re-export for test compatibility (`STATIC_SEEK_CARE_FALLBACK_EN = fallbacks.STATIC_SEEK_CARE_FALLBACK_EN`, same for the other five copy constants), and replace internal uses: `_static_fallback_assessment(...)` → `fallbacks.static_fallback_assessment(...)`, etc. Replace `_max_urgency` with `wire_contract.max_urgency` and delete `_URGENCY_TIERS`/`_max_urgency` from `main.py`.
- [ ] **Step 3:** Update the three fallback payload builders in `fallbacks.py` to emit the six NEW schema fields with safe defaults, since every payload the client sees must carry the full v2 shape: `"intents": ["reporting_new_symptom"]` for the static assessment / `["off_topic"]` for error / `["emotional_support"]` for crisis, `"requires_clinical_reassessment": False`, `"change_type": "none"`, `"reassessment_reason": None`, `"proposed_card_action": "keep"`, `"findings": []`. (These are server-constructed payloads, not model output — the values are inert; gates never read them from fallbacks.)
- [ ] **Step 4:** `pytest test_main.py -v` → all existing tests PASS unchanged (the re-exports keep constant references working). If any test referenced a private `main._pick_fallback_copy`-style name, update that test's import to `fallbacks`.
- [ ] **Step 5: Commit** — `git commit -am "refactor(functions): extract fallback copy/builders to fallbacks.py; tiers to wire_contract"`

---

### Task 3: `episode_state.py` — the State Builder

**Files:** Create `functions/episode_state.py`, `functions/test_episode_state.py`

- [ ] **Step 1: Write the failing tests** (representative set — implement all of these):

```python
# functions/test_episode_state.py
"""Tests for episode_state.py — the State Builder (spec §4).

History shapes mirror Message.toHistoryJson() v2:
user turns {role, content}; assistant turns {role, content, type} plus,
on assessment turns, urgency/findings/explanation/next_step, and on
reset turns assessment_cleared: true.
"""
import episode_state
from episode_state import derive_episode_state

U = lambda text: {"role": "user", "content": text}


def A(type_, content="...", **extra):
    return {"role": "assistant", "content": content, "type": type_, **extra}


ASSESS = A(
    "assessment", urgency="see_doctor_soon",
    findings=["fever", "headache"],
    explanation="Worth a check within 1-2 days.",
    next_step="See a doctor within 1-2 days.",
)

RED_FLAG_TEXT = "I have chest pain and I'm having trouble breathing"


def test_empty_history_is_idle():
    s = derive_episode_state([], None)
    assert s.phase == "idle"
    assert s.current_urgency is None
    assert s.min_safe_urgency is None
    assert s.latched_rule_ids == []
    assert s.questions_used == 0
    assert s.active_findings == []
    assert s.last_assessment is None


def test_latch_from_earlier_user_turn_persists():
    history = [U(RED_FLAG_TEXT), A("assessment", urgency="seek_care_now"),
               U("But I feel okay sometimes.")]
    s = derive_episode_state(history, None)
    assert s.min_safe_urgency == "seek_care_now"
    assert s.latched_rule_ids  # the chest-pain rule id(s)


def test_current_urgency_and_scaffolding_from_last_assessment():
    s = derive_episode_state([U("fever po"), ASSESS], None)
    assert s.current_urgency == "see_doctor_soon"
    assert s.active_findings == ["fever", "headache"]
    assert s.last_assessment == {
        "findings": ["fever", "headache"],
        "explanation": "Worth a check within 1-2 days.",
        "next_step": "See a doctor within 1-2 days.",
        "urgency": "see_doctor_soon",
    }
    assert s.phase == "guidance"


def test_reset_marker_clears_everything_before_it():
    history = [U(RED_FLAG_TEXT), A("assessment", urgency="seek_care_now"),
               U("I was just testing"),
               A("conversation", assessment_cleared=True)]
    s = derive_episode_state(history, None)
    assert s.min_safe_urgency is None
    assert s.current_urgency is None
    assert s.phase == "idle"
    assert s.reset_index == 3


def test_rules_rearm_after_reset():
    history = [U("test lang"), A("conversation", assessment_cleared=True),
               U(RED_FLAG_TEXT)]
    s = derive_episode_state(history, None)
    assert s.min_safe_urgency == "seek_care_now"


def test_questions_used_counts_since_last_card_or_reset():
    history = [U("sore throat"), A("question"), U("no fever"), A("question"),
               U("mild"), ASSESS, U("ok"), A("question")]
    s = derive_episode_state(history, None)
    assert s.questions_used == 1  # only the question AFTER the card counts


def test_phase_assessing_when_last_assistant_turn_is_question():
    s = derive_episode_state([U("sore throat"), A("question")], None)
    assert s.phase == "assessing"


def test_crisis_lock_survives_reset_marker():
    history = [U("crisis text"), A("crisis"),
               U("just testing"), A("conversation", assessment_cleared=True)]
    s = derive_episode_state(history, None)
    assert s.phase == "crisis"


def test_history_scan_crash_fails_closed(monkeypatch):
    def boom(message, profile=None):
        raise RuntimeError("boom")
    monkeypatch.setattr(episode_state.red_flags, "check_red_flags", boom)
    s = derive_episode_state([U("anything"), ASSESS], None)
    assert s.min_safe_urgency == "seek_care_now"
    assert "history_scan_failed" in s.latched_rule_ids


def test_malformed_turns_are_tolerated():
    history = [None, "junk", {"role": "assistant"}, {"role": "user"},
               {"role": "assistant", "type": "assessment", "urgency": 7,
            "content": "x", "findings": "not-a-list"}]
    s = derive_episode_state(history, None)  # must not raise
    assert s.current_urgency is None          # 7 is not a tier
    assert s.active_findings == []            # non-list dropped
```

- [ ] **Step 2:** `pytest test_episode_state.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# functions/episode_state.py
"""
State Builder for the conversation engine v2 (spec §4): derives
EpisodeState from client-echoed history as a pure function — same trust
model as main.py's crisis lock, extended.

Two trust zones (see the dataclass): everything above the scaffolding
marker derives from the user's own words (red_flags re-run per user
turn) or deterministic turn-type counting — the Safety Engine may
consume it. active_findings/last_assessment originate from MODEL output
echoed through history: prompt scaffolding only, never gate input.

Fail-closed rule: if check_red_flags raises while scanning a history
turn, we cannot rule an emergency out for that turn, so the latch floor
engages ("history_scan_failed") — but unlike main.py's current-message
crash path, the model still runs; the clamp enforces the floor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import red_flags
from wire_contract import URGENCY_TIERS

logger = logging.getLogger("pulse.episode_state")

HISTORY_SCAN_FAILED_RULE_ID = "history_scan_failed"


@dataclass
class EpisodeState:
    phase: str = "idle"                 # idle | assessing | guidance | crisis
    current_urgency: str | None = None
    min_safe_urgency: str | None = None
    latched_rule_ids: list[str] = field(default_factory=list)
    questions_used: int = 0
    reset_index: int = -1
    # --- prompt scaffolding only; model-proposed; NEVER gate input ---
    active_findings: list[str] = field(default_factory=list)
    last_assessment: dict | None = None


def _is_assistant(turn: object) -> bool:
    return isinstance(turn, dict) and turn.get("role") in ("assistant", "model")


def _string_list(raw: object) -> list[str]:
    if isinstance(raw, list) and all(isinstance(i, str) for i in raw):
        return raw
    return []


def _str_or_none(raw: object) -> str | None:
    return raw if isinstance(raw, str) else None


def derive_episode_state(history: list | None, profile: dict | None) -> EpisodeState:
    history = history or []
    state = EpisodeState()

    # Crisis lock scans the FULL history — a reset never clears crisis
    # (spec §6 gate 1). Mirrors main._history_has_crisis_lock.
    crisis_locked = any(
        _is_assistant(t) and t.get("type") == "crisis" for t in history
    )

    for i, turn in enumerate(history):
        if _is_assistant(turn) and turn.get("assessment_cleared") is True:
            state.reset_index = i
    effective = history[state.reset_index + 1:]

    for turn in effective:
        if not isinstance(turn, dict) or turn.get("role") != "user":
            continue
        content = turn.get("content")
        if not isinstance(content, str):
            continue
        try:
            result = red_flags.check_red_flags(content, profile)
        except Exception:
            logger.exception(
                "episode_state: red-flag scan raised on a history turn — latching fail-closed"
            )
            if HISTORY_SCAN_FAILED_RULE_ID not in state.latched_rule_ids:
                state.latched_rule_ids.append(HISTORY_SCAN_FAILED_RULE_ID)
            continue
        if result.matched:
            for rule_id in result.rule_ids:
                if rule_id not in state.latched_rule_ids:
                    state.latched_rule_ids.append(rule_id)

    if "self_harm_risk" in state.latched_rule_ids:
        crisis_locked = True  # sticky, same rank as a crisis assistant turn

    non_self_harm = [r for r in state.latched_rule_ids if r != "self_harm_risk"]
    if non_self_harm:
        state.min_safe_urgency = "seek_care_now"

    last_assistant_type: str | None = None
    questions_since_anchor = 0
    for turn in effective:
        if not _is_assistant(turn):
            continue
        turn_type = turn.get("type")
        last_assistant_type = turn_type if isinstance(turn_type, str) else None
        if turn_type == "question":
            questions_since_anchor += 1
        elif turn_type == "assessment":
            questions_since_anchor = 0  # budget anchor: card landed (spec §8)
            urgency = turn.get("urgency")
            if urgency in URGENCY_TIERS:
                state.current_urgency = urgency
                state.active_findings = _string_list(turn.get("findings"))
                state.last_assessment = {
                    "findings": state.active_findings,
                    "explanation": _str_or_none(turn.get("explanation")),
                    "next_step": _str_or_none(turn.get("next_step")),
                    "urgency": urgency,
                }
    state.questions_used = questions_since_anchor

    if crisis_locked:
        state.phase = "crisis"
    elif state.current_urgency is not None:
        state.phase = "guidance"
    elif last_assistant_type == "question":
        state.phase = "assessing"
    else:
        state.phase = "idle"
    return state
```

- [ ] **Step 4:** `pytest test_episode_state.py -v` → all PASS. (If the chest-pain latch test fails, check the exact red-flag phrasing against `red_flags.py`'s rule keywords — reuse `test_main.py`'s `NON_SELF_HARM_RED_FLAG_MESSAGE`, which is known to match.)
- [ ] **Step 5: Commit** — `git commit -am "feat(functions): episode_state - State Builder with red-flag latch and reset markers"`

---

### Task 4: `safety_engine.py` — gates + card matrix

**Files:** Create `functions/safety_engine.py`, `functions/test_safety_engine.py`

- [ ] **Step 1: Write the failing tests.** Cover EVERY matrix row and gate (spec §6). Representative set — implement all:

```python
# functions/test_safety_engine.py
"""Row-by-row tests for the Safety Engine (spec §6)."""
import fallbacks
from episode_state import EpisodeState
from safety_engine import apply_gates


def model(type_="conversation", urgency=None, intents=("reassurance_seeking",),
          requires=False, change="none", reason=None, card="keep", **over):
    p = {
        "type": type_, "message": "hi", "quick_replies": [], "urgency": urgency,
        "explanation": "x" if type_ == "assessment" else None,
        "watch_for": [], "next_step": None, "possibilities_mentioned": False,
        "self_care": [], "monitoring": [],
        "encouragement": "here" if type_ == "assessment" else None,
        "intents": list(intents), "requires_clinical_reassessment": requires,
        "change_type": change, "reassessment_reason": reason,
        "proposed_card_action": card,
        "findings": ["fever"] if type_ == "assessment" else [],
    }
    p.update(over)
    return p


def guidance(urgency="seek_care_now", latched=()):
    return EpisodeState(
        phase="guidance", current_urgency=urgency,
        min_safe_urgency="seek_care_now" if latched else None,
        latched_rule_ids=list(latched),
    )


IDLE = EpisodeState()


def gates(state, payload, message="hello", rule_ids=(), force_crisis=False):
    return apply_gates(state=state, message=message,
                       current_match_rule_ids=list(rule_ids),
                       force_crisis=force_crisis, model_result=payload)


# --- matrix rows ---

def test_first_assessment_gets_new_card():
    r = gates(IDLE, model("assessment", "monitor_at_home",
                          intents=("reporting_new_symptom",), requires=True,
                          change="new_symptom", card="new"))
    assert (r.card_action, r.card_reason) == ("new", "first_assessment")


def test_conversation_turn_keeps_card():
    r = gates(guidance(), model())
    assert r.card_action == "keep"
    assert r.payload["type"] == "conversation"
    assert not r.demoted


def test_same_tier_no_change_demotes():
    r = gates(guidance("see_doctor_soon"),
              model("assessment", "see_doctor_soon"))
    assert r.demoted and r.card_action == "keep"
    assert r.payload["type"] == "conversation"
    assert r.payload["urgency"] is None and r.payload["watch_for"] == []
    assert r.payload["message"] == "hi"  # text survives demotion


def test_same_tier_with_clinical_change_updates():
    r = gates(guidance("see_doctor_soon"),
              model("assessment", "see_doctor_soon", requires=True,
                    change="new_symptom"))
    assert (r.card_action, r.card_reason) == ("update", "clinical_change")


def test_urgency_raise_updates():
    r = gates(guidance("monitor_at_home"),
              model("assessment", "seek_care_now", requires=True,
                    change="worsening"))
    assert (r.card_action, r.card_reason) == ("update", "urgency_raised")


def test_new_red_flag_at_same_tier_updates():
    r = gates(guidance("seek_care_now", latched=("rule_a",)),
              model("assessment", "seek_care_now"),
              rule_ids=("rule_b",))
    assert (r.card_action, r.card_reason) == ("update", "new_red_flag")


# --- clamp ---

def test_deescalation_accepted_only_for_resolved_symptom_with_reason():
    ok = gates(guidance("see_doctor_soon"),
               model("assessment", "monitor_at_home", requires=True,
                     change="resolved_symptom", reason="fever gone 2 days"))
    assert ok.deescalation_accepted and ok.final_urgency == "monitor_at_home"
    assert ok.card_reason == "urgency_lowered"

    for bad in [
        model("assessment", "monitor_at_home", requires=True,
              change="treatment_update", reason="saw doctor"),   # wrong type
        model("assessment", "monitor_at_home", requires=True,
              change="resolved_symptom", reason=None),            # no reason
        model("assessment", "monitor_at_home", requires=False,
              change="resolved_symptom", reason="better"),        # no reassess
    ]:
        r = gates(guidance("see_doctor_soon"), bad)
        assert not r.deescalation_accepted
        assert r.final_urgency == "see_doctor_soon"


def test_latch_floor_beats_everything():
    r = gates(guidance("seek_care_now", latched=("rule_a",)),
              model("assessment", "monitor_at_home", requires=True,
                    change="resolved_symptom", reason="all better"))
    assert r.final_urgency == "seek_care_now"
    assert not r.deescalation_accepted


# --- floor-newly-raised guard ---

def test_new_floor_substitutes_static_fallback_over_conversation():
    r = gates(guidance("monitor_at_home"), model(), rule_ids=("rule_a",))
    assert r.payload["urgency"] == "seek_care_now"
    assert r.payload["message"] == fallbacks.STATIC_SEEK_CARE_FALLBACK_EN
    # First-match-wins: the urgency-differs row sits ABOVE new_red_flag
    # (spec §6 matrix), so a floor raise reports urgency_raised.
    assert (r.card_action, r.card_reason) == ("update", "urgency_raised")


def test_new_floor_with_compliant_assessment_passes_through():
    r = gates(guidance("monitor_at_home"),
              model("assessment", "seek_care_now", requires=True,
                    change="worsening"),
              rule_ids=("rule_a",))
    assert r.payload["message"] == "hi"  # model's own words kept
    assert r.card_action == "update"


# --- reset gate ---

def test_reset_accepted():
    r = gates(guidance(), model(intents=("testing_system",), card="clear"))
    assert r.reset_accepted and r.card_action == "clear"
    assert r.assessment_cleared


def test_reset_refused_on_red_flag_message():
    r = gates(guidance(), model(intents=("testing_system",), card="clear"),
              rule_ids=("rule_a",))
    assert not r.reset_accepted


def test_reset_refused_without_reset_intent():
    r = gates(guidance(), model(intents=("casual_chat",), card="clear"))
    assert not r.reset_accepted


def test_reset_refused_when_crisis_locked():
    state = guidance()
    state.phase = "crisis"
    r = gates(state, model(intents=("testing_system",), card="clear"),
              force_crisis=True)
    assert not r.reset_accepted
    assert r.payload["type"] == "crisis"


# --- crisis ---

def test_force_crisis_outranks_everything():
    r = gates(guidance(), model("assessment", "monitor_at_home"),
              force_crisis=True)
    assert r.payload["type"] == "crisis" and r.payload["urgency"] is None
    assert r.card_action == "keep"
```

- [ ] **Step 2:** `pytest test_safety_engine.py -v` → FAIL.

- [ ] **Step 3: Implement**

```python
# functions/safety_engine.py
"""
Safety Engine (spec §6): the deterministic gates between the model's
proposals and what the client renders. Pure functions — no I/O, no SDK.
Gate order matters and is load-bearing: crisis → clamp →
floor-newly-raised guard → reset gate → card matrix (the matrix's first
row consumes the reset outcome).

Scaffolding fields (EpisodeState.active_findings / last_assessment) are
deliberately never read here — see the trust-zone note in episode_state.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import fallbacks
from episode_state import EpisodeState
from wire_contract import (
    DEESCALATION_CHANGE_TYPES, RESET_INTENTS, URGENCY_TIERS,
    max_urgency, urgency_lt,
)


@dataclass
class GateResult:
    payload: dict
    card_action: str
    card_reason: str
    assessment_cleared: bool = False
    demoted: bool = False
    reset_accepted: bool = False
    deescalation_accepted: bool = False
    final_urgency: str | None = None


def _force_crisis(payload: dict) -> dict:
    return {**payload, "type": "crisis", "urgency": None}


def _demote(payload: dict) -> dict:
    return {
        **payload, "type": "conversation", "urgency": None,
        "explanation": None, "watch_for": [], "next_step": None,
        "self_care": [], "monitoring": [], "encouragement": None,
        "findings": [],
    }


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

    # Gate 2: urgency clamp (assessment turns only).
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

    # Gate 3: floor newly raised above the active card — the model's turn
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

    # Gate 4: reset gate.
    reset_accepted = (
        payload.get("type") == "conversation"
        and payload.get("proposed_card_action") == "clear"
        and bool(RESET_INTENTS.intersection(payload.get("intents") or []))
        and not current_match_rule_ids
        and state.phase != "crisis"
    )

    # Gate 5: card directive matrix (first matching row wins — spec §6).
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

- [ ] **Step 4:** `pytest test_safety_engine.py -v` → all PASS. Pay attention to `test_new_floor_substitutes_static_fallback_over_conversation`: the substituted payload is an assessment, so it flows into the matrix and must land on `update`/`new_red_flag` (current card exists) — if it lands on `urgency_raised`, check row order.
- [ ] **Step 5: Commit** — `git commit -am "feat(functions): safety_engine - gates and card directive matrix"`

---

### Task 5: `gemini_client.py` schema v2

**Files:** Modify `functions/gemini_client.py`, `functions/test_gemini_client.py`

- [ ] **Step 1: Write failing tests** in `test_gemini_client.py` (add to the existing validation test section, reusing its valid-payload fixtures — extend those fixtures with the six new fields first so existing tests keep passing):
  - valid `conversation` payload passes (nulls/empties per spec §5, `quick_replies` 0–4 allowed, including `[]`),
  - `conversation` with non-null `urgency`/`encouragement` or non-empty `watch_for` fails,
  - missing any new field fails (`missing required fields`),
  - `intents: []`, `intents: ["bogus"]`, `intents: [4 valid values]` fail; 1–3 valid values pass,
  - `change_type: "bogus"` fails; each of the six valid values passes,
  - `requires_clinical_reassessment: "yes"` (non-bool) fails,
  - `proposed_card_action: "replace"` fails,
  - `findings: ["fever"]` on a `question` turn fails; on `assessment` passes; `findings: "fever"` (non-list) fails.
- [ ] **Step 2:** Run → new tests FAIL.
- [ ] **Step 3: Implement** in `gemini_client.py`:
  - `from wire_contract import VALID_CARD_ACTIONS, VALID_CHANGE_TYPES, VALID_INTENTS`
  - `VALID_TYPES = frozenset({"question", "assessment", "crisis", "conversation"})`
  - Add the six new field names to `REQUIRED_FIELDS`.
  - In `_validate_payload`, after the existing checks, add:

```python
    intents = payload["intents"]
    if (not isinstance(intents, list) or not (1 <= len(intents) <= 3)
            or not all(i in VALID_INTENTS for i in intents)):
        raise ValueError("intents must be 1-3 values from the intent vocabulary")
    if not isinstance(payload["requires_clinical_reassessment"], bool):
        raise ValueError("requires_clinical_reassessment must be a boolean")
    if payload["change_type"] not in VALID_CHANGE_TYPES:
        raise ValueError(f"invalid change_type: {payload['change_type']!r}")
    reason = payload["reassessment_reason"]
    if reason is not None and not isinstance(reason, str):
        raise ValueError("reassessment_reason must be a string or null")
    if payload["proposed_card_action"] not in VALID_CARD_ACTIONS:
        raise ValueError(
            f"invalid proposed_card_action: {payload['proposed_card_action']!r}"
        )
    findings = payload["findings"]
    if not isinstance(findings, list) or not all(isinstance(f, str) for f in findings):
        raise ValueError("findings must be an array of strings")
    if response_type != "assessment" and findings:
        raise ValueError(f"{response_type} responses require empty findings")
```

  - Extend the `question`/`crisis` empty-fields block to also cover `conversation` for `self_care`/`monitoring`/`encouragement`, and require `urgency is None`, `explanation is None`, `next_step is None` on conversation turns; `quick_replies` on conversation turns must be a list of ≤ 4.
- [ ] **Step 4:** `pytest test_gemini_client.py -v` → all PASS (existing tests updated only by fixture extension, not by weakened assertions).
- [ ] **Step 5: Commit** — `git commit -am "feat(functions): wire contract v2 schema validation - conversation type + proposal fields"`

---

### Task 6: `system_prompt.py` 2.0.0

**Files:** Modify `functions/system_prompt.py`, `functions/test_system_prompt.py`

- [ ] **Step 1: Write failing tests** (add to `test_system_prompt.py`):
  - `PROMPT_VERSION == "2.0.0"`,
  - assembled prompt contains "TWO KINDS OF TURNS", the golden rule sentence, and every intent from `wire_contract.VALID_INTENTS`,
  - `build_system_prompt(conversation_state=None)` omits "CONVERSATION STATE"; with a state dict it renders CURRENT FINDINGS bullets, the LAST ASSESSMENT lines, questions-used, and the "already visible" directive,
  - state block stays in the FINAL section (assert it appears after the `## 9. CONTEXT` heading — cache discipline),
  - every `FEW_SHOT_EXAMPLES` assistant payload passes `gemini_client._parse_and_validate`-style validation (there is an existing contract test for the deck — extend/keep it; it will force the new fields onto every example),
  - the three new examples exist by title.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement.** Changes, in order:
  1. `PROMPT_VERSION = "2.0.0"`.
  2. New static constant `TWO_KINDS_OF_TURNS` inserted in `build_system_prompt`'s section list right after `HARD_RULES` (renumber section headings accordingly). Content per spec §7 — draft:

```
## 3. TWO KINDS OF TURNS

Most replies are one of two kinds, and choosing correctly is the core
of your job:

- An ASSESSMENT turn changes the medical picture: a tier, watch-fors,
  next steps. Use it when the person gives you clinical information
  that genuinely changes what they should do.
- A CONVERSATION turn is everything else: answering their question,
  steadying their worry, acknowledging thanks, explaining why you said
  what you said. type "conversation", no tier, no lists.

The golden rule: respond to the person's INTENT first, their symptoms
second. Every reply begins by answering their actual message.

The app shows your current guidance on a card that stays on screen.
The CONVERSATION STATE section at the end tells you what it says. Do
NOT restate the card's contents, re-deliver the recommendation, or
re-assess, unless this message changes the clinical picture or the
person asks. Never explain the same thing twice unless asked again.

Do NOT re-assess when the person is: thanking you, greeting you,
saying goodbye, joking, saying they were testing, asking why, asking
whether it's really necessary, scared or anxious, frustrated, asking
for emotional support, asking logistics, asking what to expect or
what happens next. Answer them — the card stands on its own.

Vary your language naturally. Never open with formula: "The
combination of...", "Based on your symptoms...", "The symptoms you've
described..." are banned openers. Write like a person who was already
in the conversation.

With every reply, also report (in the JSON fields, never in the
message text):
- "intents": 1-3 of the intent labels listed below — every intent
  genuinely present. "I'm scared... do I really need to go?" is
  emotional_support AND asking_about_recommendation; answer both.
- "requires_clinical_reassessment": should the medical assessment be
  revisited because of this message? "I already saw my doctor" is new
  information but usually does NOT require reassessment; "I started
  coughing" does.
- "change_type": why — new_symptom, resolved_symptom, worsening,
  new_history, treatment_update, or none. One value: when a message
  carries several changes, report the most clinically serious one
  (worsening > new_symptom > new_history > treatment_update >
  resolved_symptom > none). "The pain moved to my chest but the fever
  is gone" reports worsening.
- "reassessment_reason": one plain sentence, ONLY when you propose a
  different tier than the current one; null otherwise.
- "proposed_card_action": what should happen to the guidance card —
  new, update, keep, or clear. When someone says they were testing or
  made the story up, propose "clear" with a warm acknowledgment; do
  not produce a monitor-at-home card for symptoms that never existed.
- "findings": on assessment turns only, the FULL current symptom
  picture as short plain nouns ("fever", "cough") — a complete
  snapshot, not just what changed this turn.

Intent labels: reporting_new_symptom, reporting_worsening,
reporting_improvement, answering_question, medication_question,
exposure_history | asking_why, reassurance_seeking, emotional_support,
asking_next_steps, asking_about_recommendation, asking_about_causes,
clarification | greeting, thanking, joke, testing_system, correction,
casual_chat, off_topic | start_new_assessment, change_language,
feedback.
Disambiguation: "but sometimes I feel fine" = reassurance_seeking,
NOT reporting_improvement. A genuine improvement report names a
concrete change ("no fever for two days now").
```

  3. `OUTPUT_FORMAT`: extend the schema listing with the six new fields (`"conversation"` added to `type`; field-by-field lines matching the validation rules exactly — copy the constraints from Task 5, phrased for the model).
  4. New renderer + `build_system_prompt` parameter:

```python
def _render_conversation_state_block(conversation_state: dict | None) -> str:
    if not conversation_state:
        return ""
    lines = ["", "", "CONVERSATION STATE (server-derived; internal, English):"]
    urgency = conversation_state.get("current_urgency")
    last = conversation_state.get("last_assessment") or {}
    findings = conversation_state.get("active_findings") or []
    if findings:
        lines.append("CURRENT FINDINGS: " + "; ".join(findings))
    if urgency:
        lines.append(
            f"ACTIVE GUIDANCE CARD: {urgency}. "
            f"Why: {last.get('explanation') or 'n/a'} "
            f"Next step: {last.get('next_step') or 'n/a'}"
        )
        lines.append(
            "This card is already visible to the person. Do not restate "
            "it. Propose an assessment only if this message changes the "
            "clinical picture."
        )
    if conversation_state.get("latch_active"):
        lines.append(
            "A deterministic red-flag floor is active for this "
            "conversation; urgency cannot go below seek_care_now."
        )
    lines.append(
        f"Clarifying questions used since the last card: "
        f"{conversation_state.get('questions_used', 0)} of 3."
    )
    return "\n".join(lines)
```

     `build_system_prompt(..., conversation_state: dict | None = None)` appends this inside `_render_context_section` (after the language block — it is request-specific and must stay in the final section).
  5. Few-shot deck: add the six new fields to EVERY existing example payload (values per each turn's nature: e.g. sore-throat question turn → `intents ["reporting_new_symptom"]`, `requires_clinical_reassessment true`, `change_type "new_symptom"`, `reassessment_reason null`, `proposed_card_action "keep"`, `findings []`; its assessment turn → `proposed_card_action "new"`, `findings ["sore throat", "pain when swallowing", "mild fever"]`; crisis example → `intents ["emotional_support"]`, `requires false`, `change "none"`, card `keep`, findings `[]`).
  6. Three NEW examples (mark each `# AGENT-DRAFTED, PENDING OWNER READ-ALOUD (2.0.0)`), 2 turns each:
     - **"English reassurance after seek_care_now — conversation turn, card stands"**: T1 user "I've been vomiting blood since this morning." → assessment `seek_care_now` (validated-escalation shape, `findings ["vomiting blood"]`, card `new`); T2 user "But I feel okay sometimes." → `conversation`, `intents ["reassurance_seeking"]`, `requires false`, `change "none"`, card `keep`, message ~"I'm glad there are moments you feel okay — that's real. With bleeding like this, though, feeling better for a while doesn't mean the cause is gone; serious problems can ease off and come back. The advice to get seen today still stands, and I'll stay with you until you do."
     - **"Taglish anxious asking-why — answer the fear and the question, no re-card"**: T1 setting places an active `see_doctor_soon` card via a first assessment turn (fever 3 days); T2 user "Kinakabahan ako… kailangan ko ba talaga pumunta sa doktor?" → `conversation`, `intents ["emotional_support", "asking_about_recommendation"]`, warm Taglish: validate the nerves first, then the plain why (hindi ito emergency, pero tatlong araw na ang lagnat — mas maigi nang matingnan habang maaga), card `keep`.
     - **"Testing reset — clear the assessment, no leftover card"**: T1 user reports a symptom → question turn; T2 user "Haha sorry, testing ko lang 'to — wala naman talaga akong sakit." → `conversation`, `intents ["testing_system"]`, `proposed_card_action "clear"`, message ~"Ah, okay! Salamat sa pagsabi — good to know gumagana. Kung may totoo kang itatanong tungkol sa sintomas, andito lang ako."
- [ ] **Step 4:** `pytest test_system_prompt.py test_gemini_client.py -v` → PASS.
- [ ] **Step 5:** Run `python system_prompt.py` and eyeball the assembled prompt + note the token estimate delta in the commit message.
- [ ] **Step 6: Commit** — `git commit -am "feat(functions): prompt 2.0.0 - two kinds of turns, intents, conversation state block"`

---

### Task 7: `main.py` rewiring — Response Builder

**Files:** Modify `functions/main.py`, `functions/test_main.py`

- [ ] **Step 1: Write failing tests** in `test_main.py` (extend the valid-payload fixtures with the six new fields first; add a `VALID_CONVERSATION` fixture):
  - benign message + mocked assessment → response carries `card {action: "new", reason: "first_assessment"}` and `conversation_state {urgency, assessment_active: true, phase: "guidance"}`,
  - mocked conversation turn with guidance history → `card.action "keep"`, payload `type "conversation"`,
  - guidance history + mocked same-tier assessment (no reassessment flags) → demotion: `type "conversation"`, `card.action "keep"`, `metadata`/log `demoted true`,
  - red-flag message mid-guidance (use `NON_SELF_HARM_RED_FLAG_MESSAGE`) with mocked conversation turn → static fallback assessment, `card.action "update"`, `reason "new_red_flag"`,
  - reset flow: mocked conversation with `proposed_card_action "clear"` + `intents ["testing_system"]` → `assessment_cleared true`, `card.action "clear"`, `conversation_state.assessment_active false`,
  - degraded mode (model raises) with guidance history and benign message → error payload, `card.action "keep"`, `conversation_state.urgency` preserved from history,
  - history cap: build 30-turn history, capture the `history` arg passed to the mocked `get_assessment` → length ≤ `MODEL_HISTORY_WINDOW`, while a red-flag user turn at position 0 STILL latches (derivation saw all of it),
  - crisis lock behavior unchanged (existing tests keep passing),
  - `_log_request` extras include `intents`, `change_type`, `requires_clinical_reassessment`, `card_action`, `demoted`, `reset_accepted`, `deescalation_accepted` (assert via `caplog` records like existing logging tests).
- [ ] **Step 2:** Run → new tests FAIL.
- [ ] **Step 3: Implement** in `run_pipeline`, keeping the existing crash/degraded skeleton:
  1. `MODEL_HISTORY_WINDOW = 20` module constant.
  2. After validation: `state = episode_state.derive_episode_state(history, profile)`; keep `_history_has_crisis_lock` usage replaced by `state.phase == "crisis"` for `crisis_lock` (delete the now-unused helper and its tests only if nothing else references it — otherwise leave a thin wrapper).
  3. Current-message red-flag check: unchanged, including the crash path.
  4. Prompt: build `conversation_state_summary` dict from `state` (`current_urgency`, `active_findings`, `last_assessment`, `latch_active = state.min_safe_urgency is not None`, `questions_used`) — pass to `build_system_prompt`; pass `history[-(MODEL_HISTORY_WINDOW):]` sliced from `history[state.reset_index + 1:]` to `get_assessment`.
  5. Non-degraded path: `gate = safety_engine.apply_gates(state=state, message=message, current_match_rule_ids=rule_ids_now, force_crisis=force_crisis, model_result=model_result)` — this REPLACES `_merge_with_red_flags` and `_force_crisis` (delete both from `main.py`; their tests move to `test_safety_engine.py`, already written in Task 4).
  6. Degraded path: existing `_select_degraded_payload` logic stays; wrap its result in a `GateResult`-equivalent envelope: `card.action = "update" if (floor newly above state.current_urgency) else "keep"`, reason `"new_red_flag"`/`"none"`.
  7. Response Builder: return `{**gate.payload, "assessment_cleared": gate.assessment_cleared, "card": {"action": gate.card_action, "reason": gate.card_reason}, "conversation_state": {"urgency": ..., "assessment_active": ..., "phase": ...}, "metadata": {...existing...}}`. `conversation_state` reflects the POST-turn state: after a `new`/`update` card → that card's urgency, phase `guidance`; after `clear` → `{None, false, "idle"}`; crisis → `{None, false, "crisis"}`; otherwise carry the pre-turn state through.
  8. Logging: add the new structured fields to `_log_request`.
- [ ] **Step 4:** `pytest -v` (whole `functions/` suite) → all PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(functions): wire five-component pipeline - envelope, history cap, v2 logging"`

---

### Task 8: prompt-contract sync check

The deck examples, OUTPUT_FORMAT text, and validator must agree forever.

**Files:** Modify `functions/test_system_prompt.py`

- [ ] **Step 1:** Add (if Task 6 didn't already) a test that runs EVERY `FEW_SHOT_EXAMPLES` assistant payload through `gemini_client._validate_payload` directly — the deck can never demonstrate a payload the validator would reject.
- [ ] **Step 2:** `pytest test_system_prompt.py -v` → PASS.
- [ ] **Step 3: Commit** — `git commit -am "test(functions): lock few-shot deck to the v2 validator"`

---

### Task 9: offline golden conversations (merge gate)

**Files:** Create `functions/test_golden_conversations.py`

- [ ] **Step 1: Write the harness + G1, watch it fail if anything upstream is miswired.** The harness drives `run_pipeline` turn-by-turn with scripted model payloads, simulating the client echo exactly as `Message.toHistoryJson()` v2 will:

```python
# functions/test_golden_conversations.py
"""
The six golden conversations (spec §11) — offline layer. Scripted model
outputs, REAL State Builder + Safety Engine + Response Builder. These
gate every merge: if they pass, the fire-alarm behavior is dead.
"""
import main


class Conversation:
    """Drives run_pipeline turn-by-turn, echoing history the way the
    Flutter client will (Message.toHistoryJson v2)."""

    def __init__(self, monkeypatch):
        self.history: list[dict] = []
        self._scripted: list[dict] = []
        monkeypatch.setattr(
            main.gemini_client, "get_assessment",
            lambda *a, **k: dict(self._scripted.pop(0)),
        )

    def turn(self, user_message: str, scripted_model_payload: dict) -> dict:
        self._scripted.append(scripted_model_payload)
        response = main.run_pipeline(message=user_message, history=list(self.history))
        self.history.append({"role": "user", "content": user_message})
        echo = {"role": "assistant", "content": response["message"],
                "type": response["type"]}
        if response["type"] == "assessment":
            echo["urgency"] = response["urgency"]
            echo["findings"] = response.get("findings", [])
            echo["explanation"] = response.get("explanation")
            echo["next_step"] = response.get("next_step")
        if response.get("assessment_cleared"):
            echo["assessment_cleared"] = True
        if response["type"] in ("question", "assessment", "crisis", "conversation"):
            self.history.append(echo)
        return response
```

  Plus payload factories (reuse Task 4's `model()` helper shape, but as full valid wire payloads). Then G1:

```python
def test_g1_red_flag_persistence(monkeypatch):
    convo = Conversation(monkeypatch)
    r1 = convo.turn(
        "I've been vomiting blood since this morning.",
        assessment_payload(urgency="seek_care_now",
                           findings=["vomiting blood"],
                           intents=["reporting_new_symptom"],
                           requires=True, change="new_symptom", card="new"),
    )
    assert r1["card"]["action"] == "new"
    assert r1["urgency"] == "seek_care_now"

    r2 = convo.turn(
        "But I feel okay sometimes.",
        conversation_payload(intents=["reassurance_seeking"]),
    )
    assert r2["type"] == "conversation"
    assert r2["card"]["action"] == "keep"
    assert r2["conversation_state"]["urgency"] == "seek_care_now"
```

  NOTE: G1 assumes "vomiting blood" matches a red-flag rule so the latch — not just the echoed urgency — holds the floor. **Verify against `red_flags.py`'s rule registry first**; if no rule covers vomiting blood, use `test_main.py`'s `NON_SELF_HARM_RED_FLAG_MESSAGE` ("chest pain and trouble breathing") as G1's opener instead, and file the missing rule as a clinician-review question — do NOT add clinical rules yourself (red_flags.py is clinician-review-gated).

- [ ] **Step 2:** Implement G2–G6 per the spec §11 table, same pattern:
  - **G2** (continue G1's conversation): "Is it really necessary?" → conversation, keep.
  - **G3**: benign symptom → assessment card; "I was just testing." with scripted clear-proposal → `card.action "clear"`, `assessment_cleared true`, `conversation_state.assessment_active false`; assert NO urgency in the reply payload.
  - **G4**: "Mild fever since yesterday" → `monitor_at_home` card; "Now my chest hurts and it's hard to breathe" with a scripted CONVERSATION payload (deliberately wrong model behavior) → the floor guard must still produce `seek_care_now`, `card.action "update"`, `reason "urgency_raised"` (urgency-differs row outranks new_red_flag, first-match-wins). (This is the strongest server guarantee — test it with the model being wrong on purpose.)
  - **G5**: fever picture → `see_doctor_soon`; "Fever's been gone two full days, feeling fine, nothing else" with scripted `resolved_symptom` de-escalation → `card.action "update"`, `reason "urgency_lowered"`, urgency `monitor_at_home`. **Negative twin:** the same closing turn appended to G1's latched conversation → urgency stays `seek_care_now`, no `urgency_lowered`.
  - **G6**: after any card: "Thanks!" then "How are you?" (scripted conversation payloads) → both `keep`, types `conversation`, `conversation_state` unchanged.
- [ ] **Step 3:** `pytest test_golden_conversations.py -v` → 6+ PASS.
- [ ] **Step 4: Commit** — `git commit -am "test(functions): six offline golden conversations - the merge gate"`

---

### Task 10: Flutter models — envelope + `conversation` type

**Files:** Modify `lib/features/chat/models/urgency_result.dart`; Create `test/features/chat/models/urgency_result_test.dart`

- [ ] **Step 1: Write failing Dart tests**: `fromJson` parses `type: "conversation"`; parses `card {action, reason}` into a `CardAction` enum (`newCard`, `update`, `keep`, `clear`; absent/unknown → `none`); parses `conversation_state` into `ConversationState {urgency, assessmentActive, phase}` (absent → null); parses `assessment_cleared` (absent → false) and `findings` (absent → const []); unknown `card.action` value does NOT make the payload unparseable (defensive, per AGENTS.md "unknown wire values must not crash").
- [ ] **Step 2:** `flutter test test/features/chat/models/urgency_result_test.dart` → FAIL.
- [ ] **Step 3: Implement** in `urgency_result.dart` (same file — matches the codebase's simple-model style):

```dart
enum ChatTurnType { question, assessment, crisis, conversation, error, unparseable }

/// What the server decided should happen to the guidance card this turn.
/// The client renders an AssessmentCard ONLY for [newCard] and [update] —
/// no urgency logic client-side (AGENTS.md AI/Backend rule 7).
enum CardAction { newCard, update, keep, clear, none }

class ConversationState {
  const ConversationState({this.urgency, required this.assessmentActive, this.phase});
  final UrgencyLevel? urgency;
  final bool assessmentActive;
  final String? phase;

  static ConversationState? fromJson(dynamic json) {
    if (json is! Map) return null;
    return ConversationState(
      urgency: UrgencyResult._parseUrgency(json['urgency']),
      assessmentActive: json['assessment_active'] == true,
      phase: json['phase'] is String ? json['phase'] as String : null,
    );
  }
}
```

  `UrgencyResult` gains `cardAction` (default `CardAction.none`), `conversationState`, `assessmentCleared` (default false), `findings` (default const []); parse `'conversation'` in `_parseType`/`_typeWire`; parse the envelope in `fromJson`. `toJson` additions only where the history echo needs them (Task 11 reads fields directly, so `toJson` can stay payload-only).
- [ ] **Step 4:** `flutter test test/features/chat/models/ -v` → PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(chat): parse v2 envelope - conversation type, card action, conversation state"`

---

### Task 11: history echo v2

**Files:** Modify `lib/features/chat/models/message.dart`; Create `test/features/chat/models/message_test.dart`

- [ ] **Step 1: Failing tests**: `toHistoryJson` on a `conversation` turn returns a map with `type: 'conversation'` (no longer null); assessment turns include `urgency`, `findings`, `explanation`, `next_step`; a turn whose payload has `assessmentCleared true` includes `assessment_cleared: true`; `error`/`unparseable` still return null; user turns unchanged.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** — extend the whitelist and the returned map:

```dart
    final type = payload?.type;
    if (type != ChatTurnType.question &&
        type != ChatTurnType.assessment &&
        type != ChatTurnType.crisis &&
        type != ChatTurnType.conversation) {
      return null;
    }
    final map = <String, dynamic>{
      'role': 'assistant',
      'content': text,
      'type': _historyTypeWire(type!),
    };
    if (type == ChatTurnType.assessment) {
      map['urgency'] = UrgencyResult._urgencyWire(payload!.urgency);
      map['findings'] = payload!.findings;
      map['explanation'] = payload!.explanation;
      map['next_step'] = payload!.nextStep;
    }
    if (payload!.assessmentCleared) map['assessment_cleared'] = true;
    return map;
```

  (Add a small `_historyTypeWire` switch covering the four types; make `_urgencyWire` accessible — either public or via a helper on `UrgencyResult`. Update the doc comment: the server's episode derivation depends on these fields — cite the spec.)
- [ ] **Step 4:** `flutter test test/features/chat/models/ -v` → PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(chat): history echo v2 - conversation turns, urgency/findings, reset markers"`

---

### Task 12: `UrgencyStrip` + provider

**Files:** Create `lib/features/chat/widgets/urgency_strip.dart`, `test/features/chat/widgets/urgency_strip_test.dart`; Modify `lib/features/chat/providers/chat_provider.dart`

- [ ] **Step 1: Failing widget tests**: strip renders tier label + next-step line with the tier's `UrgencyColors` palette; renders nothing (SizedBox.shrink) when given null state or `assessmentActive false`; tap invokes callback.
- [ ] **Step 2:** Provider addition in `chat_provider.dart`:

```dart
/// The latest server-provided conversation state — drives the pinned
/// UrgencyStrip. Walks messages newest-first for the latest assistant
/// payload that CARRIES a conversationState: client-locally fabricated
/// error turns (see _errorMessage) have no envelope and are skipped, so
/// a transport failure never blanks the strip (spec §9).
final activeConversationStateProvider = Provider<ConversationState?>((ref) {
  final messages = ref.watch(chatControllerProvider).value ?? const <Message>[];
  for (final m in messages.reversed) {
    final cs = m.payload?.conversationState;
    if (cs != null) return cs;
  }
  return null;
});
```

  Also expose the latest assessment's `nextStep` for the strip's one-liner (either walk for it in the same provider returning a small record, or a second provider — keep it one provider returning a tiny value class if both are needed).
- [ ] **Step 3: Implement the widget** — themed per `AppTheme` rules (no hardcoded hex; `UrgencyColors` extension; label ALWAYS paired with color):

```dart
class UrgencyStrip extends StatelessWidget {
  const UrgencyStrip({super.key, required this.urgency, this.nextStep, this.onTap});
  final UrgencyLevel urgency;
  final String? nextStep;
  final VoidCallback? onTap;
  // Row: small tier icon chip + "Seek care now" label (+ " · " + nextStep,
  // ellipsized, if present) + trailing chevron. Background: palette.solid
  // at low opacity with a palette.solid left border; text palette.text.
  // Height ~44, full width, InkWell onTap.
}
```

- [ ] **Step 4:** `flutter test test/features/chat/widgets/ -v` → PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(chat): UrgencyStrip widget + activeConversationState provider"`

---

### Task 13: chat screen wiring

**Files:** Modify `lib/features/chat/screens/chat_screen.dart`

- [ ] **Step 1:** Render changes in `_buildTurn`:
  - `case ChatTurnType.conversation:` → same shape as `question` (bubble + optional `QuickReplyRow`), no card ever.
  - `case ChatTurnType.assessment:` → `AssessmentCard` ONLY when `payload.cardAction == CardAction.newCard || payload.cardAction == CardAction.update`; otherwise plain `ChatBubble` (defensive — the server demotes, but an old/foreign payload must not resurrect the fire alarm). `update` cards: pass a new optional `isUpdate` flag to `AssessmentCard` for the small "Updated" eyebrow (one-line addition inside the card's header Column).
- [ ] **Step 2:** Strip placement: in `build`, above the `Expanded(ListView…)` inside the `Column`: watch `activeConversationStateProvider`; show `UrgencyStrip` when `state?.assessmentActive == true`, `state.urgency != null`, AND `firstCrisisIndex == -1` (crisis UI owns the screen — spec §9). `onTap`: scroll to the last assessment-card message (find last index with `cardAction` new/update; `_scrollController.animateTo` toward that offset — approximate by index/extent is fine for MVP; do not add a package).
- [ ] **Step 3:** Manual verification with fixtures: flip `_useFixturesInDebug = true`, extend `FixtureChatRepository` with a scripted v2 sequence (assessment+card new → conversation keep → conversation keep) so the strip + bubble flow is visible without quota; run the app, walk the G1/G2 script, screenshot. Flip the flag back to `false` before commit.
- [ ] **Step 4:** `flutter analyze` → 0 issues; `dart format --set-exit-if-changed .`; `flutter test` → all PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(chat): pin UrgencyStrip, gate cards on card.action, render conversation turns"`

---

### Task 14: live eval scenarios (authored now, run on quota)

**Files:** Modify `functions/evals/cases.py`, `functions/evals/checkers.py`

- [ ] **Step 1:** New checkers in `checkers.py` (follow existing checker signatures): `check_card_action` (response["card"]["action"] equals expected), `check_type`, `check_conversation_state_urgency`. Register in `CHECKERS`.
- [ ] **Step 2:** New cases in `cases.py` — the live twins of the goldens, categories per spec §11: `intent_no_recard` (the fire-alarm transcript verbatim as `scripted_replies`, `("check_card_action", "keep", "every_turn")` on the discussion turns), `deescalation_discipline`, `reset_flow`, `mixed_intent_escalation`. Notes field on each: "live twin of test_golden_conversations G<n>".
- [ ] **Step 3:** `pytest` full suite still green (cases.py imports cleanly): `pytest -q`.
- [ ] **Step 4:** Do NOT run `run_evals.py` (quota). Add to `LAUNCH_BLOCKERS.md`: "Prompt 2.0.0 full eval sweep + re-baseline pending quota — deploy gate; new prompt copy (3 examples + TWO KINDS OF TURNS) pending owner read-aloud; golden live twins authored, unrun."
- [ ] **Step 5: Commit** — `git commit -am "feat(evals): live golden twins + card-action checkers; record deploy gate"`

---

### Task 15: full verification + docs

- [ ] **Step 1:** From `functions/`: `pytest -v` → entire suite PASS. From root: `flutter analyze` (0 issues), `dart format --set-exit-if-changed .`, `flutter test` (all PASS).
- [ ] **Step 2:** REQUIRED SUB-SKILL: use the project `verify` skill flow — drive the app against the emulator (`ENFORCE_APP_CHECK=false` path) or fixtures and walk G1→G2→G3 by hand; confirm strip behavior, no duplicate cards, reset clears.
- [ ] **Step 3:** Update `functions/main.py` module docstring (pipeline description now five components) and `AGENTS.md` is NOT edited (its rules still hold verbatim).
- [ ] **Step 4:** Final commit — `git commit -am "docs: conversation engine v2 wiring notes"`; then REQUIRED SUB-SKILL superpowers:finishing-a-development-branch.

---

## Deferred (recorded, not in this plan)

- Live eval sweep + `evals/results/` re-baseline on next quota window — the deploy gate (LAUNCH_BLOCKERS.md).
- Owner read-aloud of all new EN/Taglish copy; clinician review items unchanged (red_flags.py REVIEWED_BY still None).
- Mental-health review: reset-does-not-clear-crisis behavior (spec §6 gate 1).
- Firestore episode model; verified post-evaluation outcomes as a de-escalation source.
